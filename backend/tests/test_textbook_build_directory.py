"""The textbook directory reads a small derived row, never the stored review record.

Runs on the real PostgreSQL test database: the memory failure this guards
against (one catalogue request decompressing a 100-200 MB review record once
per extracted field) cannot happen in the SQLite fixtures the other textbook
tests use.
"""
import json
import unittest

from core.database import Database
from repositories.textbook_repository import TextbookRepository
from tests.support import fresh_test_config

EDITION, REVISION = 'test-edition', 'test-revision'

# The inline query directory reads used before migration 104, applied to one
# document. The projection function must keep returning exactly these values.
FORMER_INLINE_QUERY = """
SELECT
  CASE WHEN JSON_VALID(doc)
      AND OCTET_LENGTH(CAST(JSON_REMOVE(doc, '$.release') AS TEXT)) <= 1048576
    THEN JSON_REMOVE(doc, '$.release') ELSE NULL END AS evidence,
  CASE WHEN JSON_VALID(doc) THEN jsonb_build_object(
      'schemaVersion', JSON_EXTRACT(doc, '$.release.schemaVersion'),
      'sha256', JSON_EXTRACT(doc, '$.release.sha256'),
      'contentKey', JSON_EXTRACT(doc, '$.release.contentKey'),
      'classroomId', JSON_EXTRACT(doc, '$.release.classroomId'),
      'classroomSha256', JSON_EXTRACT(doc, '$.release.classroomSha256'),
      'assessmentMode', JSON_EXTRACT(doc, '$.release.assessmentMode'),
      'activityScope', JSON_EXTRACT(doc, '$.release.activityScope'),
      'activityScopeType', JSON_TYPE(JSON_EXTRACT(doc, '$.release.activityScope')),
      'audioAudit', jsonb_build_object(
        'sha256', JSON_EXTRACT(doc, '$.release.audioAudit.sha256'),
        'passed', JSON_EXTRACT(doc, '$.release.audioAudit.passed'),
        'passedType', JSON_TYPE(JSON_EXTRACT(doc, '$.release.audioAudit.passed')),
        'segments', JSON_EXTRACT(doc, '$.release.audioAudit.segments'),
        'segmentsType', JSON_TYPE(JSON_EXTRACT(doc, '$.release.audioAudit.segments')),
        'minSimilarityBps', JSON_EXTRACT(doc, '$.release.audioAudit.minSimilarityBps')
      ),
      'mediaCount', JSON_LENGTH(JSON_EXTRACT(doc, '$.release.media')),
      'mediaType', JSON_TYPE(JSON_EXTRACT(doc, '$.release.media')),
      'sceneCount', JSON_LENGTH(JSON_EXTRACT(doc, '$.release.classroom.scenes')),
      'scenesType', JSON_TYPE(JSON_EXTRACT(doc, '$.release.classroom.scenes')),
      'classroomObjectId', JSON_EXTRACT(doc, '$.release.classroom.id'),
      'stageId', JSON_EXTRACT(doc, '$.release.classroom.stage.id')
  ) ELSE NULL END AS summary
FROM (SELECT CAST(? AS jsonb) AS doc) AS source
"""

PROJECTION = """
SELECT evidence_json AS evidence, summary_json AS summary
FROM textbook_build_directory_projection(CAST(? AS jsonb))
"""


def release(**changes):
    value = {
        'schemaVersion': 'mira.textbook.release.v1',
        'sha256': 'a' * 64,
        'contentKey': 'b' * 64,
        'classroomId': 'tbpub_' + 'b' * 24,
        'classroomSha256': 'c' * 64,
        'assessmentMode': 'graded',
        'activityScope': {'kind': 'unit', 'lessons': [1, 2]},
        'audioAudit': {'sha256': 'd' * 64, 'passed': True, 'segments': 3,
                       'minSimilarityBps': 9100, 'raw': 'x' * 5000},
        'media': [{'id': 'm1'}, {'id': 'm2'}],
        'classroom': {'id': 'tbpub_' + 'b' * 24, 'stage': {'id': 'tbpub_' + 'b' * 24},
                      'scenes': [{'id': 's1'}, {'id': 's2'}, {'id': 's3'}]},
    }
    value.update(changes)
    return value


def parsed(value):
    return None if value is None else json.loads(value)


class Recording:
    """Connection wrapper that remembers every statement it runs."""
    dialect = 'postgresql'

    def __init__(self, connection):
        self.connection = connection
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return self.connection.execute(sql, params)


class TextbookBuildDirectoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = fresh_test_config()
        cls.db = Database(cls.config['DATABASE_URL'])
        cls.repo = TextbookRepository(cls.db)

    def setUp(self):
        with self.db.transaction() as conn:
            for table in ('learning_textbook_course_builds', 'learning_courses',
                          'learning_textbook_revisions', 'learning_textbook_editions'):
                conn.execute(f'DELETE FROM {table}')
            conn.execute("INSERT INTO learning_textbook_editions (edition_id,identity_sha256,identity_json,imported_at) "
                         "VALUES (?,?,'{}',1)", (EDITION, 'e' * 64))
            conn.execute("INSERT INTO learning_textbook_revisions (edition_id,revision_id,grade_code,subject,manifest_sha256,manifest_json,imported_at) "
                         "VALUES (?,?,'primary_1','chinese',?,'{}',1)", (EDITION, REVISION, 'f' * 64))

    def insert_course(self, conn, key):
        conn.execute("INSERT INTO learning_courses (id,version,grade_code,subject,node_code,title,objective,status,"
                     "quality_status,content_origin,content_json,created_at,updated_at) "
                     "VALUES (?,'v1','primary_1','chinese','n1','Title','Objective','published','released',"
                     "'openmaic_generated','{}',1,1)", ('course-' + key,))

    def insert_build(self, conn, key, *, status='published', review=None, input_json='{}'):
        if status == 'published':
            self.insert_course(conn, key)
        conn.execute(
            "INSERT INTO learning_textbook_course_builds (content_key,edition_id,revision_id,node_id,part_index,"
            "teaching_revision,input_json,status,course_id,course_version,course_content_sha256,review_json,"
            "created_at,updated_at) VALUES (?,?,?,?,1,?,?,?,?,?,?,?,1,1)",
            (key, EDITION, REVISION, 'node-' + key, 'rev-' + key, input_json, status,
             'course-' + key if status == 'published' else None, 'v1' if status == 'published' else None,
             'a' * 64 if status == 'published' else None,
             None if review is None else json.dumps(review)))

    def directory_row(self, conn, key):
        return conn.execute('SELECT review_evidence_json, release_summary_json '
                            'FROM learning_textbook_build_directory WHERE content_key=?', (key,)).fetchone()

    def test_projection_matches_the_former_inline_query(self):
        documents = {
            'complete review': {'reviewer': 'r', 'basis': 'b', 'alignmentConfirmed': True, 'release': release()},
            'no release': {'reviewer': 'r'},
            'empty object': {},
            'release is a string': {'release': 'broken'},
            'release is null': {'release': None},
            'release is an array': {'release': [1, 2]},
            'media is an object': {'release': release(media={'a': 1, 'b': 2})},
            'media is missing': {'release': {k: v for k, v in release().items() if k != 'media'}},
            'scenes missing': {'release': release(classroom={'id': 'only-id'})},
            'audio audit failed': {'release': release(audioAudit={'passed': False, 'segments': 'many'})},
            'audio audit is a number': {'release': release(audioAudit=7)},
            'activity scope is a list': {'release': release(activityScope=[1])},
            'evidence over one MiB': {'padding': 'x' * 1_100_000, 'release': release()},
        }
        with self.db.transaction() as conn:
            for name, document in documents.items():
                with self.subTest(name):
                    text = json.dumps(document)
                    former = conn.execute(FORMER_INLINE_QUERY, (text,)).fetchone()
                    current = conn.execute(PROJECTION, (text,)).fetchone()
                    self.assertEqual(parsed(current['evidence']), parsed(former['evidence']))
                    self.assertEqual(parsed(current['summary']), parsed(former['summary']))
        with self.db.transaction() as conn:
            oversized = conn.execute(PROJECTION, (json.dumps(documents['evidence over one MiB']),)).fetchone()
            complete = conn.execute(PROJECTION, (json.dumps(documents['complete review']),)).fetchone()
        self.assertIsNone(oversized['evidence'])  # over the 1 MiB bound
        self.assertEqual(parsed(oversized['summary'])['mediaCount'], 2)
        self.assertEqual(parsed(complete['evidence']),
                         {'reviewer': 'r', 'basis': 'b', 'alignmentConfirmed': True})
        self.assertEqual(parsed(complete['summary'])['sceneCount'], 3)

    def test_projection_gives_nothing_for_a_record_that_is_not_an_object(self):
        # The former query raised on these and failed the whole catalogue.
        with self.db.transaction() as conn:
            for text in ('["damaged"]', '5', 'null', '"text"'):
                with self.subTest(text):
                    row = conn.execute(PROJECTION, (text,)).fetchone()
                    self.assertEqual((row['evidence'], row['summary']), (None, None))

    def test_directory_row_follows_every_write_of_review_json(self):
        with self.db.transaction() as conn:
            self.insert_build(conn, 'k1', status='prepared')
            self.assertIsNone(self.directory_row(conn, 'k1'))

            self.insert_course(conn, 'k1')
            first = {'reviewer': 'first', 'release': release()}
            conn.execute("UPDATE learning_textbook_course_builds SET status='published',course_id='course-k1',"
                         "course_version='v1',course_content_sha256=?,review_json=? WHERE content_key='k1'",
                         ('a' * 64, json.dumps(first)))
            row = self.directory_row(conn, 'k1')
            self.assertEqual(parsed(row['review_evidence_json']), {'reviewer': 'first'})
            self.assertEqual(parsed(row['release_summary_json'])['sceneCount'], 3)

            second = {'reviewer': 'second', 'release': release(media=[{'id': 'only'}])}
            conn.execute("UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key='k1'",
                         (json.dumps(second),))
            row = self.directory_row(conn, 'k1')
            self.assertEqual(parsed(row['review_evidence_json']), {'reviewer': 'second'})
            self.assertEqual(parsed(row['release_summary_json'])['mediaCount'], 1)

            before = self.directory_row(conn, 'k1')
            conn.execute("UPDATE learning_textbook_course_builds SET updated_at=99 WHERE content_key='k1'")
            self.assertEqual(self.directory_row(conn, 'k1'), before)

            conn.execute("DELETE FROM learning_textbook_course_builds WHERE content_key='k1'")
            self.assertIsNone(self.directory_row(conn, 'k1'))

    def test_directory_row_is_removed_when_the_record_is_cleared(self):
        with self.db.transaction() as conn:
            self.insert_build(conn, 'k2', status='retired', review={'release': release()})
            self.assertIsNotNone(self.directory_row(conn, 'k2'))
            conn.execute("UPDATE learning_textbook_course_builds SET review_json=NULL WHERE content_key='k2'")
            self.assertIsNone(self.directory_row(conn, 'k2'))

    def test_directory_read_uses_the_summary_row_and_never_the_review_record(self):
        review = {'reviewer': 'r', 'release': release()}
        with self.db.transaction() as conn:
            self.insert_build(conn, 'k3', review=review, input_json=json.dumps({'frozen': True}))
        with self.db.transaction() as raw:
            conn = Recording(raw)
            rows = self.repo.directory_builds(conn, EDITION, REVISION)
        self.assertEqual(len(rows), 1)
        self.assertNotIn('review_json', ' '.join(conn.statements))
        row = rows[0]
        self.assertNotIn('review_json', row)
        self.assertEqual(parsed(row['directory_review_evidence_json']), {'reviewer': 'r'})
        summary = parsed(row['directory_release_summary_json'])
        self.assertEqual(summary['classroomObjectId'], 'tbpub_' + 'b' * 24)
        self.assertEqual((summary['mediaType'], summary['mediaCount']), ('ARRAY', 2))
        self.assertEqual((summary['scenesType'], summary['sceneCount']), ('ARRAY', 3))
        self.assertIs(summary['audioAudit']['passed'], True)
        self.assertEqual(summary['audioAudit']['passedType'], 'BOOLEAN')
        self.assertEqual(summary['audioAudit']['segmentsType'], 'INTEGER')
        self.assertEqual(parsed(row['input_json']), {'frozen': True})
        self.assertEqual(row['directory_course_id'], 'course-k3')

    def test_a_build_without_a_summary_row_is_still_listed_without_evidence(self):
        with self.db.transaction() as conn:
            self.insert_build(conn, 'k4', review={'release': release()})
            conn.execute('DELETE FROM learning_textbook_build_directory')
        with self.db.transaction() as conn:
            row = self.repo.directory_builds(conn, EDITION, REVISION)[0]
        self.assertIsNone(row['directory_review_evidence_json'])
        self.assertIsNone(row['directory_release_summary_json'])


if __name__ == '__main__':
    unittest.main()
