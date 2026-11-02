"""Read and publish a light lesson directory without generation or remote calls.

Layout: identity.json (editionId, revisionId, nodeId, teachingRevision, title,
objective, teacherCode, authorModels, estimatedMinutes; optional confirmation), body.json, media/<sha256>.<ext>,
official-notes.json, brief.json, audit-receipt.json, verification.json, roster.json.
Identity authorModels lists every model that wrote pages, lines or questions;
verification.verifier.model must differ from each, case-insensitively.
estimatedMinutes is a required integer from 5 to 120. Confirmation contains
userQuote, confirmedAt (with timezone), confirmedBy='owner', authorAttestation.
An optional identity.manifest permits offline checks; otherwise the repository
supplies the registered alignment manifest. No check or dry run writes files.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from content.courseware_release import build_release, require, validate_light_release
from content.textbook_catalog import digest
from content.textbook_release import validate_release


def _checker():
    # Backend-only test invocations do not put the repository root on sys.path.
    path = Path(__file__).resolve().parents[2] / 'courseware/tools/check.py'
    spec = importlib.util.spec_from_file_location('mira_courseware_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_classroom


class CoursewarePublishService:
    def __init__(self, repository, *, classroom_directory, manifest=None, checker=None, clock=None):
        self.repository = repository
        self.classroom_directory = Path(classroom_directory)
        self.manifest = manifest
        self.checker = checker or _checker()
        self.clock = clock or (lambda: int(time.time() * 1000))

    def _inputs(self, lesson_dir, confirmation):
        root = Path(lesson_dir).resolve()

        def read(name):
            path = root / name
            require(not path.is_symlink(), 'lesson_symlink')
            return json.loads(path.read_text(encoding='utf-8'))
        identity = read('identity.json')
        manifest = self.manifest or identity.get('manifest')
        if manifest is None:
            require(self.repository is not None, 'manifest_missing')
            with self.repository.transaction() as conn:
                revision = self.repository.get_revision(conn, identity['editionId'], identity['revisionId'])
                require(revision is not None, 'manifest_missing')
                manifest = self.repository.manifest(revision)
                require(digest(manifest) == revision['manifest_sha256'], 'manifest_mismatch')
        inputs = {'identity': identity, 'manifest': manifest, 'body': read('body.json'),
            'notes': read('official-notes.json'), 'brief': read('brief.json'),
            'receipt': read('audit-receipt.json'), 'verification': read('verification.json'),
            'roster': read('roster.json'), 'confirmation': confirmation if confirmation is not None else identity.get('confirmation')}
        media_dir = root / 'media'
        require(media_dir.is_dir() and not media_dir.is_symlink(), 'media_missing')
        media = {}
        for path in sorted(media_dir.iterdir()):
            require(path.is_file() and not path.is_symlink(), 'media_invalid')
            media[path.name] = path.read_bytes()
        inputs['media'] = media
        grade = manifest.get('gradeCode', '')
        grade = int(grade.split('_')[1]) if grade.startswith('primary_') and grade.split('_')[1].isdigit() else None
        inputs['gateIssues'] = self.checker(inputs['body'], media_dir, notes=inputs['notes'],
            roster=inputs['roster'], receipt=inputs['receipt'], verification=inputs['verification'], grade=grade)
        return inputs

    def check(self, lesson_dir, *, confirmation=None):
        inputs = None
        try:
            inputs = self._inputs(lesson_dir, confirmation)
            prepared = build_release(inputs)
            errors = validate_light_release(prepared, inputs['manifest'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'ok': False, 'errors': [str(exc)], 'issues': inputs['gateIssues'] if inputs else []}
        return {'ok': not errors, 'errors': errors, 'issues': inputs['gateIssues'], 'prepared': prepared,
            'gates': {**prepared['frozen']['coursewareLight']['gates'], 'G8': {'passed': not errors}}}

    def _materialize(self, prepared, media):
        root = self.classroom_directory.resolve()
        classroom_id = prepared['release']['classroomId']
        for entry in prepared['frozen']['media']:
            raw = media[entry['sourceName']]
            require(hashlib.sha256(raw).hexdigest() == entry['sha256'], 'media_hash_mismatch')
            target = root / classroom_id / entry['relative']
            require(not any(p.is_symlink() for p in (target, target.parent, target.parent.parent)), 'media_conflict')
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with target.open('xb') as stream:
                    stream.write(raw)
            except FileExistsError:
                require(target.is_file() and target.read_bytes() == raw, 'media_conflict')

    def _predecessors(self, conn, frozen):
        b = frozen['textbookBinding']
        return conn.execute("SELECT * FROM learning_textbook_course_builds WHERE edition_id=? AND revision_id=? "
            "AND node_id=? AND part_index=? AND status='published' AND content_key<>? FOR UPDATE",
            (b['editionId'], b['alignmentRevisionId'], b['nodeId'], b['partIndex'], frozen['contentKey'])).fetchall()

    @staticmethod
    def _open_sessions(conn, predecessors):
        return sum(conn.execute("SELECT COUNT(*) AS count FROM learning_sessions WHERE course_id=? "
            "AND course_version=? AND status='in_progress'", (row['course_id'], row['course_version'])).fetchone()['count']
            for row in predecessors)

    def publish(self, lesson_dir, *, confirmation=None, apply=False):
        inputs = self._inputs(lesson_dir, confirmation)
        prepared = build_release(inputs)
        frozen, course, review = (prepared[key] for key in ('frozen', 'course', 'review'))
        result = {'ok': True, 'applied': False, 'created': False, 'contentKey': frozen['contentKey'],
            'classroomId': prepared['release']['classroomId'], 'courseId': course['id'],
            'courseVersion': course['version'], 'releaseSha256': prepared['release']['sha256'],
            'status': 'plan', 'archiveStatus': 'archive pending', 'retiredBuilds': 0, 'openSessionsOnRetiredBuilds': 0}
        require(self.repository is not None, 'repository_missing')
        if not apply:
            with self.repository.transaction() as conn:
                # Dry runs need no row locks or immutable file writes.
                b = frozen['textbookBinding']
                rows = conn.execute("SELECT * FROM learning_textbook_course_builds WHERE edition_id=? AND revision_id=? "
                    "AND node_id=? AND part_index=? AND status='published' AND content_key<>?",
                    (b['editionId'], b['alignmentRevisionId'], b['nodeId'], b['partIndex'], frozen['contentKey'])).fetchall()
                current = self.repository.get_build(conn, frozen['contentKey'])
                if current is not None:
                    require(current['status'] != 'retired', 'build_retired')
                    if current['status'] == 'published':
                        require(self.repository.parse(current['review_json']) == review, 'review_conflict')
                result.update(retiredBuilds=len(rows), openSessionsOnRetiredBuilds=self._open_sessions(conn, rows))
            return result
        self._materialize(prepared, inputs['media'])
        with self.repository.transaction() as conn:
            b = frozen['textbookBinding']
            revision = conn.execute('SELECT * FROM learning_textbook_revisions WHERE edition_id=? '
                'AND revision_id=? AND retired_at IS NULL FOR UPDATE', (b['editionId'], b['alignmentRevisionId'])).fetchone()
            require(revision is not None and revision['manifest_sha256'] == digest(inputs['manifest'])
                    and self.repository.manifest(revision) == inputs['manifest'], 'manifest_mismatch')
            timestamp = self.clock()
            build, _ = self.repository.reserve_build(conn, frozen, timestamp)
            require(build['status'] != 'retired', 'build_retired')
            require(build['status'] in ('prepared', 'published'), 'build_status_invalid')
            if build['status'] == 'published':
                require(self.repository.parse(build['review_json']) == review, 'review_conflict')
            old = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=? FOR UPDATE',
                (course['id'], course['version'])).fetchone()
            if old is not None:
                require(self.repository.parse(old['content_json']) == prepared['content_json']
                        and old['status'] == 'published' and old['quality_status'] == 'released'
                        and old.get('retired_at') is None and old['content_origin'] == course['content_origin'], 'course_conflict')
            else:
                require(build['status'] == 'prepared', 'course_conflict')
                conn.execute("INSERT INTO learning_courses (id,version,grade_code,subject,node_code,title,objective,status,"
                    "content_json,content_origin,quality_status,published_at,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,'published',?,?,'released',?,?,?)",
                    (course['id'], course['version'], course['grade_code'], course['subject'], course['node_code'],
                     course['title'], course['objective'], course['content_json'], course['content_origin'], timestamp, timestamp, timestamp))
            created = self.repository.bind_published(conn, build, course, review, timestamp)
            saved = self.repository.get_build(conn, frozen['contentKey'])
            stored_course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                (course['id'], course['version'])).fetchone()
            require(validate_release(saved, inputs['manifest'], stored_course) == prepared['release'], 'release_invalid')
            predecessors = self._predecessors(conn, frozen) if created else []
            sessions = self._open_sessions(conn, predecessors)
            if predecessors:
                conn.execute("UPDATE learning_textbook_course_builds SET status='retired', updated_at=? "
                    "WHERE edition_id=? AND revision_id=? AND node_id=? AND part_index=? AND status='published' AND content_key<>?",
                    (timestamp, b['editionId'], b['alignmentRevisionId'], b['nodeId'], b['partIndex'], frozen['contentKey']))
                # The archive catalog treats a published course without a published build as a formal release.
                for row in predecessors:
                    conn.execute("UPDATE learning_courses SET status='retired', quality_status='superseded', "
                        "retired_at=COALESCE(retired_at, ?), updated_at=? WHERE id=? AND version=?",
                        (timestamp, timestamp, row['course_id'], row['course_version']))
            result.update(applied=True, created=created, status='published', retiredBuilds=len(predecessors),
                openSessionsOnRetiredBuilds=sessions)
            scopes = conn.execute('SELECT content_key FROM course_storage_scopes WHERE classroom_id=?',
                (prepared['release']['classroomId'],)).fetchall()
            result['registered'] = any(row['content_key'] == frozen['contentKey'] for row in scopes)
            result['archiveStatus'] = 'registered' if result['registered'] else 'archive pending'
        return result

    def status(self, content_key=None, *, classroom_id=None):
        require(bool(content_key) != bool(classroom_id), 'status_identity_invalid')
        if content_key:
            require(len(content_key) == 64 and all(c in '0123456789abcdef' for c in content_key), 'status_identity_invalid')
        else:
            require(classroom_id.startswith('tbpub_') and len(classroom_id) == 30
                    and all(c in '0123456789abcdef' for c in classroom_id[6:]), 'status_identity_invalid')
        with self.repository.transaction() as conn:
            if content_key:
                build = self.repository.get_build(conn, content_key)
                classroom_id = 'tbpub_' + content_key[:24]
            else:
                candidates = conn.execute('SELECT * FROM learning_textbook_course_builds WHERE content_key LIKE ?',
                    (classroom_id[6:] + '%',)).fetchall()
                require(len(candidates) <= 1, 'classroom_ambiguous')
                build = candidates[0] if candidates else None
            scopes = conn.execute('SELECT storage_id,scope_key,content_key FROM course_storage_scopes WHERE classroom_id=?',
                (classroom_id,)).fetchall()
        registered = build is not None and any(s['content_key'] == build['content_key'] for s in scopes)
        return {'classroomId': classroom_id, 'contentKey': build['content_key'] if build else content_key,
            'status': build['status'] if build else 'not_found', 'registered': registered,
            'archiveStatus': 'registered' if registered else 'archive pending'}
