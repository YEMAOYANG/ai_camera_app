"""Real fixed-classroom grading across releases, using only in-memory SQLite."""
import json
import re
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

from content.textbook_catalog import canonical, digest
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from repositories.textbook_repository import TextbookRepository
from services.textbook_classroom_service import TextbookClassroomService
from services.textbook_directory_access import published_node_releases
from tests.test_textbook_learning import IsolatedDatabase, sample
from tests.test_textbook_publication import fixture


class ClassroomDatabase(IsolatedDatabase):
    def execute(self, sql, params=()):
        # The existing isolated adapter already handles compact MySQL upserts.
        return super().execute(re.sub(r'ON DUPLICATE KEY UPDATE id\s*=\s*id',
                                      'ON DUPLICATE KEY UPDATE id=id', sql), params)


class QuizRevisionIsolationTests(unittest.TestCase):
    def setUp(self):
        self.db = ClassroomDatabase()
        self.addCleanup(self.db.raw.close)
        self.assertEqual(self.db.raw.execute('PRAGMA database_list').fetchone()[2], '')
        for column in ('title', 'objective'):
            self.db.execute(f'ALTER TABLE learning_courses ADD COLUMN {column} TEXT')
        for column in ('task_id', 'answers_json', 'runtime_state_json'):
            self.db.execute(f'ALTER TABLE learning_sessions ADD COLUMN {column} TEXT')
        for column in ('current_question_index', 'correct_count', 'attempted_count',
                       'started_at', 'completed_at', 'classroom_completed_at', 'created_at', 'updated_at'):
            self.db.execute(f'ALTER TABLE learning_sessions ADD COLUMN {column} INTEGER')
        self.db.execute('CREATE UNIQUE INDEX session_task ON learning_sessions(family_id,task_id)')
        self.db.execute('CREATE UNIQUE INDEX session_id ON learning_sessions(id)')
        task_columns = ('id,family_id,child_id,title,description,type,status,scheduled_date,scheduled_start,'
                        'scheduled_end,schedule_type,start_at,due_at,repeat_rule,priority,reward_points,'
                        'requires_parent_confirmation,created_by,reminder_minutes_before,reminder_status,'
                        'timezone,learning_course_id,learning_course_version,learning_assignment_key,'
                        'learning_slot,created_at,updated_at,started_at,camera_observation_status,'
                        'next_reminder_at,completion_source,evidence_summary,completed_at,ended_at')
        self.db.execute('CREATE TABLE tasks (' + ','.join(
            c + (' TEXT UNIQUE' if c in ('id', 'learning_assignment_key') else ' TEXT')
            for c in task_columns.split(',')) + ')')
        report_columns = ('id,family_id,child_id,task_id,session_id,course_id,course_version,learning_date,'
                          'grade_code,subject,score,correct_count,independent_correct_count,hint_count,'
                          'total_questions,mastery_level,summary,strengths_json,next_step,created_at')
        self.db.execute('CREATE TABLE learning_reports (' + ','.join(
            c + ' TEXT' for c in report_columns.split(',')) + ', UNIQUE(family_id,session_id))')
        self.repo = TextbookRepository(self.db)
        self.child = {'id': 'child', 'family_id': 'family', 'grade_code': 'primary_1',
                      'grade_selection_revision': 1}
        self.db.execute('INSERT INTO children VALUES (?,?,?,?)', tuple(self.child.values()))
        self.manifest = sample(reviewed=True)
        self.repo.import_revision(self.db, self.manifest, 1)
        principal = {'id': 'student', 'family_id': 'family', 'child_id': 'child'}
        auth = Mock()
        auth.authenticate.return_value = {'principal': principal, 'session': {'id': 'login'}}
        auth.repository.get_session.return_value = {'id': 'login', 'revoked_at': None,
                                                    'refresh_expires_at': now_ms() + 60000}
        auth._active_principal_and_device.return_value = (principal, {})
        self.service = TextbookClassroomService(self.repo, student_auth=auth,
            signing_key='isolated-quiz-revision-test', public_url='https://runtime.test')
        self.db.raw.commit()

    def publish_fixture(self, version, answer):
        """Two valid immutable releases deliberately share the question ID q1."""
        _, template, release = fixture()
        frozen = json.loads(template['input_json'])
        frozen['knowledgeBrief'] = self.manifest['units'][0]['lessons'][0]['brief']
        frozen['textbookBinding'].update(editionId=self.manifest['editionId'],
            alignmentRevisionId=self.manifest['revisionId'], alignmentManifestSha256=digest(self.manifest),
            teachingRevision=version)
        frozen.pop('contentKey')
        key = digest(frozen)
        frozen['contentKey'] = key
        cid = 'tbpub_' + key[:24]
        release.update(contentKey=key, classroomId=cid)
        classroom = release['classroom']
        classroom['id'] = classroom['stage']['id'] = cid
        question = classroom['scenes'][0]['content']['questions'][0]
        question.update(answer=[answer], questionAudioUrl=f'/api/classroom-media/{cid}/audio/one.wav')
        if answer == 'B':
            question.update(question='大地是哪一个字？', analysis='地，大地的地。')
        release['classroomSha256'] = digest(classroom)
        release['sha256'] = digest({k: v for k, v in release.items() if k != 'sha256'})
        review = {**json.loads(template['review_json']), 'release': release}
        course = {'id': 'textbook_' + key[:40], 'version': version, 'grade_code': 'primary_1',
                  'subject': 'chinese', 'title': '天地人', 'objective': '听声音看图选择',
                  'content_json': canonical({'title': '天地人', 'questions': [question],
                                             'releaseSha256': release['sha256']})}
        self.db.execute('INSERT INTO learning_courses (id,version,grade_code,subject,content_json,status,'
                        'quality_status,content_origin,title,objective) VALUES (?,?,?,?,?,\'published\','
                        '\'released\',\'openmaic_generated\',?,?)',
                        tuple(course[k] for k in ('id', 'version', 'grade_code', 'subject',
                                                 'content_json', 'title', 'objective')))
        build, _ = self.repo.reserve_build(self.db, frozen, int(version))
        self.repo.bind_published(self.db, build, course, review, int(version))
        self.db.raw.commit()
        build = self.repo.get_build(self.db, key)
        stored = self.db.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                                 (course['id'], version)).fetchone()
        self.assertEqual(validate_release(build, self.manifest, stored), release)
        return key, release

    def launch(self, key):
        launch = self.service.launch('student-token', key)
        ticket = parse_qs(urlparse(launch['launchUrl']).query)['ticket'][0]
        return self.service.exchange(ticket)

    def snapshot(self, key, session_id):
        return canonical({
            'build': self.repo.get_build(self.db, key),
            'session': self.db.execute('SELECT * FROM learning_sessions WHERE id=?', (session_id,)).fetchone(),
            'report': self.db.execute('SELECT * FROM learning_reports WHERE session_id=?', (session_id,)).fetchone(),
        })

    def test_new_release_starts_clean_and_old_answers_report_and_token_stay_bound(self):
        old_key, old_release = self.publish_fixture('3', 'A')
        old = self.launch(old_key)
        token = old['runtimeToken']
        result = self.service.quiz(token, {'q1': 'A'})
        self.assertEqual(result['result']['correctCount'], 1)
        before = self.snapshot(old_key, old['learningSessionId'])

        new_key, new_release = self.publish_fixture('4', 'B')
        new = self.launch(new_key)
        self.assertNotEqual(old['learningSessionId'], new['learningSessionId'])
        self.assertEqual(self.service.quiz(new['runtimeToken']), {'ok': True, 'result': None, 'partial': None})
        fresh = self.db.execute('SELECT * FROM learning_sessions WHERE id=?', (new['learningSessionId'],)).fetchone()
        self.assertEqual(fresh['answers_json'], '[]')
        self.assertEqual(fresh['attempted_count'], 0)
        self.assertNotEqual(fresh['course_id'], json.loads(before)['session']['course_id'])
        self.assertEqual(fresh['course_version'], '4')
        self.assertEqual(self.service.quiz(new['runtimeToken'], {'q1': 'A'})['result']['correctCount'], 0)
        self.assertEqual(self.snapshot(old_key, old['learningSessionId']), before)
        self.assertEqual(self.service.quiz(token), result)
        self.assertEqual(self.service.validate(token)['classroomId'], old_release['classroomId'])
        self.assertEqual(self.service.validate(new['runtimeToken'])['classroomId'], new_release['classroomId'])
        self.assertEqual(self.launch(new_key)['learningSessionId'], new['learningSessionId'])
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM learning_reports').fetchone()['n'], 2)

        current = published_node_releases(self.repo, self.db, self.child,
            self.repo.builds(self.db, self.manifest['editionId'], self.manifest['revisionId']))
        self.assertEqual(current['u1-l1'][0]['content_key'], new_key)
        self.assertEqual(self.snapshot(old_key, old['learningSessionId']), before)

    def test_even_signed_mixed_old_new_authorities_cannot_rebind_a_session(self):
        old_key, _ = self.publish_fixture('3', 'A')
        old = self.launch(old_key)
        self.service.quiz(old['runtimeToken'], {'q1': 'A'})
        before = self.snapshot(old_key, old['learningSessionId'])
        new_key, new_release = self.publish_fixture('4', 'B')
        new = self.launch(new_key)
        authority = self.service.signer.loads(old['runtimeToken'][5:])
        # Signing models a server-side mix-up; the immutable authority checks
        # must reject it even when cryptographic verification alone succeeds.
        for mutation in ({'key': new_key}, {'release': new_release['sha256']},
                         {'learningSession': new['learningSessionId']},
                         {'key': new_key, 'release': new_release['sha256']},
                         {'key': new_key, 'learningSession': new['learningSessionId']}):
            with self.subTest(mutation=mutation):
                token = 'tbpr_' + self.service.signer.dumps({**authority, **mutation})
                with self.assertRaises(ApiError) as caught:
                    self.service.quiz(token, {'q1': 'B'})
                self.assertEqual(caught.exception.code, 'textbook_release_unavailable')
        self.assertEqual(self.snapshot(old_key, old['learningSessionId']), before)
        self.assertIsNone(self.service.quiz(new['runtimeToken'])['result'])


if __name__ == '__main__':
    unittest.main()
