"""Durable textbook identities; read methods never import or generate content."""
from __future__ import annotations

import json

from content.textbook_catalog import canonical, digest
from core.errors import ApiError


class TextbookRepository:
    def __init__(self, database):
        self.database = database

    def transaction(self):
        return self.database.transaction()

    @staticmethod
    def manifest(row):
        return json.loads(row["manifest_json"]) if isinstance(row["manifest_json"], str) else row["manifest_json"]

    def get_revision(self, conn, edition_id, revision_id):
        return conn.execute("SELECT * FROM learning_textbook_revisions WHERE edition_id=? AND revision_id=? AND retired_at IS NULL",
                            (edition_id, revision_id)).fetchone()

    def list_revisions(self, conn, grade_code):
        return conn.execute("SELECT * FROM learning_textbook_revisions WHERE grade_code=? AND retired_at IS NULL ORDER BY subject,edition_id,revision_id",
                            (grade_code,)).fetchall()

    def import_revision(self, conn, manifest, now):
        key = manifest["editionId"], manifest["revisionId"]
        identity = {k: manifest[k] for k in ("editionId", "publisher", "gradeCode", "subject", "volume", "schoolSystem")}
        identity["resourceId"] = manifest["source"]["resourceId"]
        conn.execute("INSERT INTO learning_textbook_editions (edition_id,identity_sha256,identity_json,imported_at) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE edition_id=edition_id",
                     (key[0], digest(identity), canonical(identity), now))
        edition = conn.execute("SELECT * FROM learning_textbook_editions WHERE edition_id=? FOR UPDATE", (key[0],)).fetchone()
        if edition["identity_sha256"] != digest(identity):
            raise ApiError("textbook_edition_conflict", "出版社、年级、学科、学制、册次或资源已变化，请建立新的教材版本", 409)
        # Unique key serializes concurrent imports; immutable hashes prevent replacement.
        cursor = conn.execute("INSERT INTO learning_textbook_revisions (edition_id,revision_id,grade_code,subject,manifest_sha256,manifest_json,imported_at) "
                              "VALUES (?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE edition_id=edition_id",
                              (*key, manifest["gradeCode"], manifest["subject"], digest(manifest), canonical(manifest), now))
        row = conn.execute("SELECT * FROM learning_textbook_revisions WHERE edition_id=? AND revision_id=? FOR UPDATE", key).fetchone()
        if row is None or row["manifest_sha256"] != digest(manifest):
            raise ApiError("textbook_revision_conflict", "这个教材修订已存在，请使用新的修订编号", 409)
        return row, cursor.rowcount == 1

    def child(self, conn, family_id, child_id, *, lock=False):
        return conn.execute("SELECT * FROM children WHERE family_id=? AND id=?" + (" FOR UPDATE" if lock else ""),
                            (family_id, child_id)).fetchone()

    def selections(self, conn, child, year, semester):
        choices = conn.execute("SELECT * FROM learning_textbook_selections WHERE family_id=? AND child_id=? "
                            "AND school_year_start=? AND semester=? AND grade_revision=? ORDER BY subject",
                            (child["family_id"], child["id"], year, semester, child["grade_selection_revision"])).fetchall()
        # A parent selected a book, not the absence of its directory. Enrich only
        # an empty index with an explicitly linked revision of that SAME resource.
        # Keep their selection/event/CAS history intact, and never move an existing
        # directory, current lesson or course build to another revision.
        result = []
        for choice in choices:
            row = self.get_revision(conn, choice["edition_id"], choice["revision_id"])
            manifest = self.manifest(row) if row else None
            if (not manifest or manifest["units"] or manifest["coverage"]["status"] != "index_only"
                    or digest(manifest) != row["manifest_sha256"] or choice["current_node_id"]):
                result.append(choice)
                continue
            has_build = conn.execute("SELECT content_key FROM learning_textbook_course_builds WHERE edition_id=? AND revision_id=? LIMIT 1",
                                     (choice["edition_id"], choice["revision_id"])).fetchone()
            if has_build:
                result.append(choice)
                continue
            candidates = conn.execute("SELECT * FROM learning_textbook_revisions WHERE edition_id=? AND retired_at IS NULL ORDER BY imported_at,revision_id",
                                      (choice["edition_id"],)).fetchall()
            enriched = choice
            for candidate in candidates:
                value = self.manifest(candidate)
                provenance = value.get("directorySource", {})
                if (provenance.get("baseRevisionId") == choice["revision_id"] and value["units"]
                        and provenance.get("resourceId") == manifest["source"]["resourceId"]
                        and value["source"]["resourceId"] == manifest["source"]["resourceId"]
                        and digest(value) == candidate["manifest_sha256"]):
                    enriched = {**choice, "revision_id": candidate["revision_id"]}
                    break  # Stable first enrichment; subsequent revisions require a parent choice.
            result.append(enriched)
        return result

    def learning_context(self, conn, child):
        row = conn.execute("SELECT value FROM app_settings WHERE family_id=? AND setting_key=?",
                           (child["family_id"], "textbook_context." + child["id"])).fetchone()
        return self.parse(row["value"]) if row else {}

    def save_learning_context(self, conn, child, value, now):
        # The caller holds the family and child locks, including first insert.
        key = (child["family_id"], "textbook_context." + child["id"])
        exists = conn.execute("SELECT value FROM app_settings WHERE family_id=? AND setting_key=?", key).fetchone()
        if exists:
            conn.execute("UPDATE app_settings SET value=?,updated_at=? WHERE family_id=? AND setting_key=?",
                         (canonical(value), now, *key))
        else:
            conn.execute("INSERT INTO app_settings(family_id,setting_key,value,updated_at) VALUES (?,?,?,?)",
                         (*key, canonical(value), now))

    def completed_courses(self, conn, child):
        return {(r["course_id"], r["course_version"]) for r in conn.execute(
            "SELECT DISTINCT course_id,course_version FROM learning_sessions "
            "WHERE family_id=? AND child_id=? AND status='completed'",
            (child["family_id"], child["id"])).fetchall()}

    def select(self, conn, *, child, manifest, year, semester, expected_revision, current_node, confirmed_by, now):
        key = (child["family_id"], child["id"], year, semester, manifest["subject"])
        old = conn.execute("SELECT * FROM learning_textbook_selections WHERE family_id=? AND child_id=? "
                           "AND school_year_start=? AND semester=? AND subject=? FOR UPDATE", key).fetchone()
        revision = int(old["selection_revision"]) if old else 0
        visible_revision = revision if old and int(old["grade_revision"]) == int(child["grade_selection_revision"]) else 0
        if visible_revision != expected_revision:
            raise ApiError("textbook_selection_changed", "教材选择已更新，请刷新后重新确认", 409)
        values = (manifest["editionId"], manifest["revisionId"], child["grade_selection_revision"], revision + 1,
                  current_node, confirmed_by, now)
        if old:
            conn.execute("UPDATE learning_textbook_selections SET edition_id=?,revision_id=?,grade_revision=?,selection_revision=?,current_node_id=?,confirmed_by=?,updated_at=? "
                         "WHERE family_id=? AND child_id=? AND school_year_start=? AND semester=? AND subject=?", (*values, *key))
        else:
            conn.execute("INSERT INTO learning_textbook_selections (family_id,child_id,school_year_start,semester,subject,edition_id,revision_id,grade_revision,selection_revision,current_node_id,confirmed_by,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (*key, *values))
        conn.execute("INSERT INTO learning_textbook_selection_events (family_id,child_id,school_year_start,semester,subject,selection_revision,selection_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (*key, revision + 1, canonical({"editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"],
                                                    "gradeRevision": child["grade_selection_revision"], "currentNodeId": current_node,
                                                    "confirmedBy": confirmed_by}), now))
        return revision + 1

    def reserve_build(self, conn, brief, now):
        b = brief["textbookBinding"]
        cursor = conn.execute("INSERT INTO learning_textbook_course_builds (content_key,edition_id,revision_id,node_id,part_index,teaching_revision,input_json,status,created_at,updated_at) "
                              "VALUES (?,?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE content_key=content_key",
                              (brief["contentKey"], b["editionId"], b["alignmentRevisionId"], b["nodeId"], b["partIndex"], b["teachingRevision"], canonical(brief), "prepared", now, now))
        # A current read is essential: under MySQL REPEATABLE READ a concurrent
        # no-op upsert can find a row newer than this transaction's snapshot.
        row = conn.execute("SELECT * FROM learning_textbook_course_builds WHERE content_key=? FOR UPDATE", (brief["contentKey"],)).fetchone()
        if row is None or self.parse(row["input_json"]) != brief:
            raise ApiError("textbook_build_conflict", "课程制作身份冲突，不能重复创建", 409)
        return row, cursor.rowcount == 1

    @staticmethod
    def parse(value):
        return json.loads(value) if isinstance(value, str) else value

    def builds(self, conn, edition_id, revision_id):
        # MySQL filesort carries the large classroom JSON and can exhaust its
        # sort buffer even for one 3D release. Sort this one book's rows without
        # changing global database settings or the latest-revision ordering.
        rows = conn.execute("SELECT * FROM learning_textbook_course_builds WHERE edition_id=? AND revision_id=? AND status='published'",
                            (edition_id, revision_id)).fetchall()
        return sorted(rows, key=lambda row: (row['node_id'], row['part_index'], -int(row['created_at']), row['content_key']))

    def directory_builds(self, conn, edition_id, revision_id):
        """Read directory authority without returning the full saved classroom.

        ``review_json.release`` contains the classroom, media inventory and raw
        audio audit. Those immutable artifacts are needed when a child actually
        enters a course, but moving every release through Python just to render
        a directory makes a catalogue request proportional to all published
        courseware. Keep the complete frozen input and small review evidence so
        the directory can still check identities and publication authority.
        The strict launch path continues to use ``get_build`` and
        ``validate_release`` over the complete row.
        """
        mysql = getattr(conn, "dialect", None) == "mysql"
        array_length = "JSON_LENGTH" if mysql else "json_array_length"
        def json_type(path):
            return (f"JSON_TYPE(JSON_EXTRACT(b.review_json, '{path}'))" if mysql
                    else f"json_type(b.review_json, '{path}')")
        review_evidence = "JSON_REMOVE(b.review_json, '$.release')"
        review_evidence_bytes = (f"OCTET_LENGTH({review_evidence})" if mysql
                                 else f"LENGTH(CAST({review_evidence} AS BLOB))")
        course_title = "c.title"
        if not mysql:
            # The isolated SQLite contract fixture predates the production title
            # column. Keep the production projection fixed while allowing empty
            # test catalogues to exercise the same read path.
            columns = conn.execute("PRAGMA table_info(learning_courses)").fetchall()
            if not any(row.get("name") == "title" for row in columns):
                course_title = "NULL"
        # Keep the exact top-level evidence because its frozen digest includes
        # versioned review fields beyond the common contract. Bound it at 1 MiB
        # so an unrelated top-level payload can never recreate the transfer
        # problem. CASE also isolates a malformed SQLite fixture row so one
        # damaged release cannot fail the complete catalogue query.
        rows = conn.execute(f"""
            SELECT b.content_key,b.edition_id,b.revision_id,b.node_id,b.part_index,
              b.teaching_revision,b.input_json,b.status,b.course_id,b.course_version,
              b.course_content_sha256,b.created_at,b.updated_at,
              CASE WHEN JSON_VALID(b.review_json)
                  AND {review_evidence_bytes} <= 1048576
                THEN {review_evidence} ELSE NULL END AS directory_review_evidence_json,
              CASE WHEN JSON_VALID(b.review_json) THEN JSON_OBJECT(
                  'schemaVersion', JSON_EXTRACT(b.review_json, '$.release.schemaVersion'),
                  'sha256', JSON_EXTRACT(b.review_json, '$.release.sha256'),
                  'contentKey', JSON_EXTRACT(b.review_json, '$.release.contentKey'),
                  'classroomId', JSON_EXTRACT(b.review_json, '$.release.classroomId'),
                  'classroomSha256', JSON_EXTRACT(b.review_json, '$.release.classroomSha256'),
                  'assessmentMode', JSON_EXTRACT(b.review_json, '$.release.assessmentMode'),
                  'activityScope', JSON_EXTRACT(b.review_json, '$.release.activityScope'),
                  'activityScopeType', {json_type('$.release.activityScope')},
                  'audioAudit', JSON_OBJECT(
                    'sha256', JSON_EXTRACT(b.review_json, '$.release.audioAudit.sha256'),
                    'passed', JSON_EXTRACT(b.review_json, '$.release.audioAudit.passed'),
                    'passedType', {json_type('$.release.audioAudit.passed')},
                    'segments', JSON_EXTRACT(b.review_json, '$.release.audioAudit.segments'),
                    'segmentsType', {json_type('$.release.audioAudit.segments')},
                    'minSimilarityBps', JSON_EXTRACT(b.review_json, '$.release.audioAudit.minSimilarityBps')
                  ),
                  'mediaCount', {array_length}(JSON_EXTRACT(b.review_json, '$.release.media')),
                  'mediaType', {json_type('$.release.media')},
                  'sceneCount', {array_length}(JSON_EXTRACT(b.review_json, '$.release.classroom.scenes')),
                  'scenesType', {json_type('$.release.classroom.scenes')},
                  'classroomObjectId', JSON_EXTRACT(b.review_json, '$.release.classroom.id'),
                  'stageId', JSON_EXTRACT(b.review_json, '$.release.classroom.stage.id')
                ) ELSE NULL END AS directory_release_summary_json,
              c.id AS directory_course_id,c.version AS directory_course_version,
              {course_title} AS directory_course_title,c.grade_code AS directory_course_grade_code,
              c.subject AS directory_course_subject,c.content_json AS directory_course_content_json,
              c.status AS directory_course_status,c.quality_status AS directory_course_quality_status,
              c.content_origin AS directory_course_content_origin,
              c.retired_at AS directory_course_retired_at
            FROM learning_textbook_course_builds b
            JOIN learning_courses c ON c.id=b.course_id AND c.version=b.course_version
            WHERE b.edition_id=? AND b.revision_id=? AND b.status='published'
            """, (edition_id, revision_id)).fetchall()
        return sorted(rows, key=lambda row: (row['node_id'], row['part_index'], -int(row['created_at']), row['content_key']))

    def get_build(self, conn, content_key, *, lock=False):
        return conn.execute("SELECT * FROM learning_textbook_course_builds WHERE content_key=?" + (" FOR UPDATE" if lock else ""),
                            (content_key,)).fetchone()

    def runtime_release_identity(self, conn, content_key):
        """Read current publication bytes' hashes without transferring the audit.

        The production database hashes the original JSON text, not a claimed
        SHA stored inside it. Shared locking reads also avoid an older MVCC
        snapshot created by the authentication reads in this transaction.
        """
        mysql = getattr(conn, 'dialect', None) == 'mysql'
        fields = ('content_key', 'edition_id', 'revision_id', 'node_id',
                  'part_index', 'teaching_revision', 'course_id', 'course_version',
                  'course_content_sha256', 'status', 'created_at', 'updated_at')
        hashes = ('SHA2(input_json,256) AS input_sha256, '
                  'SHA2(review_json,256) AS review_sha256') if mysql else 'input_json, review_json'
        shared = ' FOR SHARE' if mysql else ''
        build = conn.execute('SELECT ' + ','.join(fields) + ',' + hashes
                             + ' FROM learning_textbook_course_builds WHERE content_key=?' + shared,
                             (content_key,)).fetchone()
        if build is None:
            return None
        if not mysql:
            # Isolated SQLite tests; production never transfers these bytes.
            from services.textbook_directory_access import _value_sha256
            build['input_sha256'] = _value_sha256(build.pop('input_json'))
            build['review_sha256'] = _value_sha256(build.pop('review_json'))
        revision = conn.execute('SELECT * FROM learning_textbook_revisions '
            'WHERE edition_id=? AND revision_id=?' + shared,
            (build['edition_id'], build['revision_id'])).fetchone()
        course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?' + shared,
            (build['course_id'], build['course_version'])).fetchone()
        return {'build': build, 'revision': revision, 'course': course}

    def course_build(self, conn, course_id, version):
        return conn.execute("SELECT * FROM learning_textbook_course_builds WHERE course_id=? AND course_version=? AND status='published'",
                            (course_id, version)).fetchone()

    def bind_published(self, conn, build, course, review, now):
        values = (course["id"], course["version"], digest(self.parse(course["content_json"])), canonical(review))
        if build["status"] == "published":
            if (build["course_id"], build["course_version"], build["course_content_sha256"]) != values[:3]:
                raise ApiError("textbook_build_conflict", "固定课程已绑定，更新内容须使用新的讲解版本", 409)
            return False
        if build["status"] != "prepared":
            raise ApiError("textbook_build_conflict", "这份任务书已停止使用", 409)
        conn.execute("UPDATE learning_textbook_course_builds SET course_id=?,course_version=?,course_content_sha256=?,review_json=?,status='published',updated_at=? WHERE content_key=? AND status='prepared'",
                     (*values, now, build["content_key"]))
        return True
