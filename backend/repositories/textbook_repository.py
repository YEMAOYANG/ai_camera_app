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
        return conn.execute("SELECT * FROM learning_textbook_selections WHERE family_id=? AND child_id=? "
                            "AND school_year_start=? AND semester=? AND grade_revision=? ORDER BY subject",
                            (child["family_id"], child["id"], year, semester, child["grade_selection_revision"])).fetchall()

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
        return conn.execute("SELECT * FROM learning_textbook_course_builds WHERE edition_id=? AND revision_id=? AND status='published' ORDER BY node_id,part_index,created_at DESC",
                            (edition_id, revision_id)).fetchall()

    def get_build(self, conn, content_key, *, lock=False):
        return conn.execute("SELECT * FROM learning_textbook_course_builds WHERE content_key=?" + (" FOR UPDATE" if lock else ""),
                            (content_key,)).fetchone()

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
