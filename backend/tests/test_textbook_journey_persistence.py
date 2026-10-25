"""Execute the real classroom/repository/task/report SQL against isolated SQLite."""
from contextlib import contextmanager, ExitStack
import json
import re
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from content import textbook_journey as journey
from content.textbook_catalog import canonical
from repositories.learning_repository import LearningRepository
from services.textbook_classroom_service import TextbookClassroomService
from test_textbook_activity import release_fixture


class Connection:
    def __init__(self):
        self.raw = sqlite3.connect(':memory:')
        self.raw.row_factory = sqlite3.Row
    def execute(self, sql, params=()):
        sql = re.sub(r'\s+FOR UPDATE\b(?: OF [\w, ]+)?', '', sql)
        sql = re.sub(r'ON DUPLICATE KEY UPDATE id\s*=\s*id', 'ON CONFLICT DO NOTHING', sql)
        cursor = self.raw.execute(sql, tuple(params))
        row = lambda x: dict(x) if x is not None else None
        return SimpleNamespace(fetchone=lambda: row(cursor.fetchone()), fetchall=lambda: [row(r) for r in cursor.fetchall()], rowcount=cursor.rowcount)
    @contextmanager
    def transaction(self):
        with self.raw: yield self


class JourneyPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.db = Connection()
        task_columns = 'id,family_id,child_id,title,description,type,status,scheduled_date,scheduled_start,scheduled_end,schedule_type,start_at,due_at,repeat_rule,priority,reward_points,requires_parent_confirmation,created_by,reminder_minutes_before,reminder_status,timezone,learning_course_id,learning_course_version,learning_assignment_key,learning_slot,created_at,updated_at,started_at,camera_observation_status,next_reminder_at,completion_source,evidence_summary,completed_at,ended_at'
        self.db.execute('CREATE TABLE tasks (' + ','.join(c + (' TEXT UNIQUE' if c in ('id','learning_assignment_key') else ' TEXT') for c in task_columns.split(',')) + ')')
        session_columns = 'id,family_id,child_id,task_id,course_id,course_version,status,current_question_index,correct_count,attempted_count,answers_json,started_at,completed_at,classroom_completed_at,created_at,updated_at,runtime_state_json'
        self.db.execute('CREATE TABLE learning_sessions (' + ','.join(c + ' TEXT' for c in session_columns.split(',')) + ')')
        report_columns = 'id,family_id,child_id,task_id,session_id,course_id,course_version,learning_date,grade_code,subject,score,correct_count,independent_correct_count,hint_count,total_questions,mastery_level,summary,strengths_json,next_step,created_at'
        self.db.execute('CREATE TABLE learning_reports (' + ','.join(c + ' TEXT' for c in report_columns.split(',')) + ', UNIQUE(family_id,session_id))')
        self.db.execute("INSERT INTO tasks (id,family_id,child_id,created_by,status) VALUES ('task','family','child','student','in_progress')")
        self.db.execute("INSERT INTO learning_sessions (id,family_id,child_id,task_id,course_id,course_version,status) VALUES ('session','family','child','task','course','1','in_progress')")
        self.release = release_fixture()
        self.child = {'family_id': 'family', 'id': 'child'}
        self.course = {'id': 'course', 'version': '1', 'title': '天地人', 'grade_code': 'primary_1', 'subject': 'chinese', 'objective':'认字'}
        self.service = object.__new__(TextbookClassroomService)
        self.service.repository = SimpleNamespace(transaction=self.db.transaction)
        self.service.learning = LearningRepository(self.db)
        self.service._authority = Mock(return_value=({}, self.child, {}, self.release, self.course, {'id':'session'}))
        self.service._playback_release = Mock(side_effect=lambda value: value)
        self.time = 1800000000000
        self.stack = ExitStack()
        for name in ('content.textbook_journey.now_ms', 'services.textbook_classroom_service.now_ms', 'services.textbook_journey_service.now_ms'):
            self.stack.enter_context(patch(name, side_effect=lambda:self.time))
    def tearDown(self):
        self.stack.close(); self.db.raw.close()
    def state(self):
        row = self.db.execute('SELECT * FROM learning_sessions').fetchone()
        progress = json.loads(row['runtime_state_json']) if row['runtime_state_json'] else {}
        return journey.initial(progress, self.release)
    def act(self, section, action, choice=None):
        data={'section':section,'version':self.state()['version'],'action':action}
        if choice is not None:data['choice']=choice
        return self.service.play('test',data)
    def finish(self, section):
        for _ in range(100):
            state = self.state()
            if state[section]['phase']=='done': return
            item=journey.item(state[section],self.release,state)
            self.act(section,'answer',item['targets'][0]); self.act(section,'next')
        self.fail('unfinished')
    def test_teacher_help_is_bound_to_the_current_question_and_saved_as_assistance(self):
        from copy import deepcopy
        self.service.repository.parse = json.loads
        self.service.budget_service = Mock()
        self.service.budget_service.issue_course_authorization.return_value = {'authorized': True}
        self.service._authority.return_value = ({}, self.child, {'input_json': canonical({'gradeCode': 'primary_1', 'subject': 'chinese'})}, self.release, self.course, {'id': 'session'})
        request = {'storeState': {'currentSceneId': journey.PLAN['sceneIds']['games'], 'scenes': deepcopy(self.release['classroom']['scenes'])}}
        with patch('services.textbook_classroom_service.discussion_request', return_value=request):
            result = self.service.admit_interaction('test', {'path': '/api/chat', 'request': {}})
        self.assertEqual(self.state()['games']['hintLevel'], 1)
        current = next(s for s in result['request']['storeState']['scenes'] if s['id'] == journey.PLAN['sceneIds']['games'])
        question = current['content']['questions'][0]
        self.assertNotIn('answer', question)
        self.assertIn(journey.FLOW['teachingGuidance'], question['question'])
        self.assertEqual(current['content']['type'], 'quiz')

    def test_catalog_query_is_safe_for_driver_parameter_interpolation(self):
        from core.database import DatabaseConnection
        captured = Mock()
        captured.execute.return_value.fetchone.return_value = {'id': 'task', 'status': 'in_progress'}
        self.service.learning.assign_catalog_task(captured, family_id='family', child_id='child', course=self.course, created_by='student', now=self.time)
        sql, args = captured.execute.call_args.args
        adapted = DatabaseConnection(None, dialect='postgresql')._adapt_sql(sql)
        # psycopg reads %s and %% exactly as Python's % operator does.
        literals = tuple("'" + str(value).replace("'", "''") + "'" for value in args)
        self.assertIn("NOT LIKE 'tbr_%'", adapted % literals)

    def test_complete_lesson_and_two_due_reviews_persist_three_tasks_one_immutable_baseline(self):
        self.finish('games'); self.finish('challenge')
        self.assertTrue(self.state()['reportDays'])
        first = self.db.execute('SELECT * FROM learning_reports').fetchone()
        source = self.db.execute('SELECT * FROM learning_sessions').fetchone()
        self.assertEqual(source['status'],'completed')
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM tasks').fetchone()['n'],2)
        self.assertEqual(first['mastery_level'],'developing')
        baseline=source['answers_json']
        for _ in range(2):
            state=self.state(); self.time=state['reviewDueAt']
            self.act('challenge','review'); self.finish('challenge')
        last=self.db.execute('SELECT * FROM learning_reports').fetchone()
        self.assertEqual(last['mastery_level'],'mastered')
        self.assertEqual((last['score'],last['independent_correct_count']),(first['score'],first['independent_correct_count']))
        self.assertEqual(self.db.execute('SELECT answers_json FROM learning_sessions').fetchone()['answers_json'],baseline)
        self.assertEqual(self.db.execute("SELECT count(*) AS n FROM tasks WHERE status='completed'").fetchone()['n'],3)
        self.assertEqual(self.db.execute('SELECT count(*) AS n FROM learning_reports').fetchone()['n'],1)
        self.assertIsNone(self.state()['reviewDueAt'])
        # Catalog launch must keep selecting the source lesson, never a review task.
        self.db.execute("UPDATE tasks SET type='learning',learning_course_id='course',learning_course_version='1' WHERE id='task'")
        task,created=self.service.learning.assign_catalog_task(self.db,family_id='family',child_id='child',course=self.course,created_by='student',now=self.time)
        self.assertEqual(task['id'],'task'); self.assertFalse(created)

if __name__ == '__main__': unittest.main()
