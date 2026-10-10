"""Stable shared authoring identities. Callers hold the edition row lock.

Locking the already imported edition serializes first reservations too, including
legacy previews created before these slots existed. Provider calls never run in
this transaction. The table intentionally cannot carry learner identities.
"""
import json

from content.textbook_catalog import canonical, digest
from core.errors import ApiError


class CourseReuseRepository:
    @staticmethod
    def lock_edition(conn, edition):
        row = conn.execute('SELECT * FROM learning_textbook_editions WHERE edition_id=? FOR UPDATE',
                           (edition,)).fetchone()
        if row is None:
            raise ApiError('textbook_revision_not_found', '请先导入并核对教材', 404)
        return row

    @staticmethod
    def slots(conn, course_key):
        try:
            return conn.execute('SELECT * FROM learning_course_reuse_slots WHERE course_key=? '
                                'ORDER BY created_at DESC,identity_key DESC FOR UPDATE', (course_key,)).fetchall()
        except Exception as exc:
            # Only a missing table is converted; other database failures retain
            # their original error and cannot open a fallback paid path.
            if (getattr(exc, 'args', (None,))[0] == 1146
                    or 'no such table: learning_course_reuse_slots' in str(exc)):
                raise ApiError('course_reuse_schema_required', '课件复用登记尚未升级，已停止新生成', 503) from exc
            raise

    @staticmethod
    def previews(conn, edition, node):
        return conn.execute('SELECT * FROM learning_textbook_course_previews WHERE edition_id=? AND node_id=? '
                            'ORDER BY created_at DESC,preview_key DESC FOR UPDATE', (edition, node)).fetchall()

    @staticmethod
    def publications(conn, edition, node):
        return conn.execute("SELECT * FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=? "
                            "AND part_index=1 AND status='published' ORDER BY created_at DESC,content_key DESC FOR UPDATE",
                            (edition, node)).fetchall()

    @staticmethod
    def reserve(conn, identity, scope_hash, now, *, preview_key=None, publication_key=None, regeneration=None):
        key = digest(identity)
        conn.execute('INSERT INTO learning_course_reuse_slots '
                     '(identity_key,course_key,edition_id,node_id,part_index,teaching_revision,identity_json,'
                     'lesson_scope_sha256,preview_key,published_content_key,regeneration_json,created_at,updated_at) '
                     'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE identity_key=identity_key',
                     (key, digest({k: v for k, v in identity.items() if k != 'teachingRevision'}),
                      identity['editionId'], identity['nodeId'], identity['partIndex'], identity['teachingRevision'],
                      canonical(identity), scope_hash, preview_key, publication_key,
                      canonical(regeneration) if regeneration else None, now, now))
        row = conn.execute('SELECT * FROM learning_course_reuse_slots WHERE identity_key=? FOR UPDATE', (key,)).fetchone()
        saved_identity = (json.loads(row['identity_json']) if row and isinstance(row['identity_json'], str)
                          else row['identity_json'] if row else None)
        if (row is None or saved_identity != identity
                or row['lesson_scope_sha256'] != scope_hash):
            raise ApiError('course_reuse_identity_conflict', '课次身份已存在不同教学范围，请核对教学版本', 409)
        return row

    @staticmethod
    def bind_preview(conn, slot, key, now):
        if slot['preview_key'] not in (None, key):
            raise ApiError('course_reuse_identity_conflict', '课次已绑定其他制作任务，不能再次生成', 409)
        conn.execute('UPDATE learning_course_reuse_slots SET preview_key=?,updated_at=? WHERE identity_key=?',
                     (key, now, slot['identity_key']))

    @staticmethod
    def bind_publication(conn, slot, key, now):
        if slot['published_content_key'] not in (None, key):
            raise ApiError('course_reuse_identity_conflict', '同一教学版本有多个发布内容，请核对后使用', 409)
        conn.execute('UPDATE learning_course_reuse_slots SET published_content_key=?,updated_at=? WHERE identity_key=?',
                     (key, now, slot['identity_key']))
