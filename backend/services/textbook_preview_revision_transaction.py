"""Short preview transactions around provider/runtime work under operator.lock.

Never keep a preview row locked across a runtime request: registered runtime
writes acquire their own registry head and preview locks on another connection.
"""
from copy import deepcopy


def _registered_source(path):
    from services.course_file_store import CourseFileStore
    return CourseFileStore().resolve(path) is not None


class PreviewRevisionTransaction:
    def __init__(self, repository, preview_key, fail, source_path):
        self.repository, self.key, self.fail = repository, preview_key, fail
        self._context = self._conn = self._source = None
        # Local saves do not participate in the registry's preview lock guard.
        # Retain their original lock protocol; registered saves use head CAS.
        self._two_phase = _registered_source(source_path)

    def __enter__(self):
        self._open()
        return self

    def _open(self):
        self._context = self.repository.transaction()
        self._conn = self._context.__enter__()

    def execute(self, sql, params=()):
        if self._conn is None:
            raise RuntimeError('preview revision SQL requires a short transaction')
        return self._conn.execute(sql, params)

    def release(self, row):
        """Freeze the preflight row, then release it before any external work."""
        self._source = deepcopy(dict(row))
        if self._two_phase:
            context, self._context, self._conn = self._context, None, None
            context.__exit__(None, None, None)

    def commit_phase(self):
        """Recheck the complete source and publication state in a fresh lock."""
        if self._source is None or (self._conn is not None and self._two_phase):
            raise RuntimeError('invalid preview revision transaction phase')
        if self._two_phase:
            self._open()
        current = self.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE',
                               (self.key,)).fetchone()
        if current is None or dict(current) != self._source:
            self.fail('数据库已被其他任务修改，保留修订断点，不能覆盖')
        builds = self.execute("SELECT input_json FROM learning_textbook_course_builds "
            "WHERE edition_id=? AND node_id=? AND status='published'",
            (current['edition_id'], current['node_id'])).fetchall()
        if any(self.repository.parse(build['input_json']).get('previewKey') == self.key for build in builds):
            self.fail('已发布课件不能原地修订，保留修订断点')

    def __exit__(self, kind, value, traceback):
        if self._context is not None:
            context, self._context, self._conn = self._context, None, None
            return context.__exit__(kind, value, traceback)
        return False
