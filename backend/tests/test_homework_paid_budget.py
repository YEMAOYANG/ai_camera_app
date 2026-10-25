"""Private audio uses the real budget ledger; providers are never called here."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from content.learning_budget_policy import LearningBudgetPolicy, UNITS, digest
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService
from tests.test_learning_budget import IsolatedDatabase, test_policy


class HomeworkBudgetDatabase(IsolatedDatabase):
    def __init__(self, path):
        self.path = str(path)
        # SQLite cannot DROP CHECK. Start with the final 076 + 088 constraint.
        sql = (Path(__file__).parents[1] / 'migrations/mysql/076_learning_paid_budget.sql').read_text()
        sql = sql.replace("'optional_interaction'))", "'optional_interaction', 'homework'))")
        sql = sql.replace('BIGINT AUTO_INCREMENT PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT').replace(' ENGINE=InnoDB', '')
        with sqlite3.connect(self.path) as conn:
            conn.executescript(sql)
            conn.executescript('''CREATE TABLE homework_submissions (
                id TEXT PRIMARY KEY, family_id TEXT, child_id TEXT, grade_code TEXT,
                subject TEXT, consent_at INTEGER, deleted_at INTEGER);
                CREATE TABLE homework_items (id TEXT PRIMARY KEY, submission_id TEXT,
                revision INTEGER, result_json TEXT);''')
            conn.execute('INSERT INTO homework_submissions VALUES (?,?,?,?,?,?,?)',
                         ('hw_test','family-a','child-a','primary_1','math',1,None))
            conn.execute('INSERT INTO homework_items VALUES (?,?,?,?)',
                         ('hwi_test','hw_test',1,json.dumps({'status':'incorrect','answerMode':'picture_choice'})))


class HomeworkPaidBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.db=HomeworkBudgetDatabase(Path(self.directory.name)/'budget.db')
        self.raw=test_policy()
        maximum=dict.fromkeys(UNITS,1000000)
        self.raw['limits']['purposes']['homework']={'day':maximum,'month':maximum}
        self.raw['authorizationTemplates']['homework']={'maxUnits':maximum,'priceKeys':['fake-text-v1'],'ttlMs':86400000}
        self.service=LearningBudgetService(self.db,policy=LearningBudgetPolicy(self.raw),clock=lambda:1000)

    def auth(self):
        return self.service.issue_homework_authorization(submission_id='hw_test',item_id='hwi_test',revision=1)['authorizationId']

    def reserve(self, auth, key='audio'):
        return self.service.reserve(authorization_id=auth,dispatch_id=key,request_sha256=digest(key),
            price_key='fake-text-v1',max_units={'calls':1,'input_tokens':10,'output_tokens':10})

    def test_legacy_policy_digest_is_unchanged_and_grants_no_homework(self):
        raw=test_policy()
        self.assertEqual(LearningBudgetPolicy(raw).sha256,digest(raw))
        service=LearningBudgetService(self.db,policy=LearningBudgetPolicy(raw))
        self.assertIsNone(service.issue_homework_authorization(submission_id='absent',item_id='absent',revision=1))

    def test_private_scope_can_dispatch_without_course_or_session(self):
        auth=self.auth(); row=self.reserve(auth)
        self.service.dispatch(reservation_id=row['reservationId'],authorization_id=auth,request_sha256=row['requestSha256'])
        with self.db.transaction() as conn:
            scope=json.loads(conn.execute('SELECT scope_json FROM learning_budget_authorizations WHERE id=?',(auth,)).fetchone()['scope_json'])
        self.assertEqual(scope['purpose'],'homework'); self.assertEqual(scope['childId'],'child-a')
        self.assertNotIn('courseId',scope); self.assertNotIn('sessionId',scope)

    def test_deleted_or_corrected_item_cannot_dispatch_reserved_request(self):
        auth=self.auth(); row=self.reserve(auth)
        with self.db.transaction() as conn:
            conn.execute('UPDATE homework_items SET revision=2')
        with self.assertRaises(ApiError) as error:
            self.service.dispatch(reservation_id=row['reservationId'],authorization_id=auth,request_sha256=row['requestSha256'])
        self.assertEqual(error.exception.code,'learning_budget_homework_scope_changed')

    def test_forged_family_scope_cannot_mint_authorization(self):
        with self.db.transaction() as conn:
            scope=self.service._homework_scope(conn,'hw_test','hwi_test',1)
        scope['familyId']='family-b'
        with self.assertRaises(ApiError) as error:
            self.service.issue_course_authorization(authorization_id=digest('forged'),scope=scope)
        self.assertEqual(error.exception.code,'learning_budget_homework_scope_changed')

    def test_edit_does_not_reset_submission_budget(self):
        self.raw['limits']['course']['lifetime']['calls']=1
        self.service=LearningBudgetService(self.db,policy=LearningBudgetPolicy(self.raw),clock=lambda:1000)
        self.reserve(self.auth())
        with self.db.transaction() as conn:
            conn.execute('UPDATE homework_items SET revision=2')
        auth=self.service.issue_homework_authorization(submission_id='hw_test',item_id='hwi_test',revision=2)['authorizationId']
        with self.assertRaises(ApiError):
            self.reserve(auth,'second-audio')

    def test_deleted_submission_cannot_issue(self):
        with self.db.transaction() as conn:
            conn.execute('UPDATE homework_submissions SET deleted_at=1')
        with self.assertRaises(ApiError): self.auth()
