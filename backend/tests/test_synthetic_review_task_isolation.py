"""Ordinary task projections must not consume explicitly authorized demo reviews."""
from datetime import date, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from repositories.learning_review_repository import LearningReviewRepository
from repositories.task_repository import TaskRepository
from services.conversation_policy_service import ConversationPolicyService
from services.task_runtime_service import TaskRuntimeService
from services.task_service import TaskService
from test_textbook_learning import IsolatedDatabase


class SyntheticReviewTaskIsolationTest(unittest.TestCase):
    def setUp(self):
        self.db = IsolatedDatabase(("085_learning_reviews.sql",))
        self.addCleanup(self.db.raw.close)
        self.db.allow_runtime_schema_creation = True
        self.db.executescript = self.db.raw.executescript
        self.repo = TaskRepository(self.db)
        self.db.execute("ALTER TABLE tasks ADD learning_slot TEXT")
        self.db.execute("CREATE TABLE learning_task_carryovers (source_task_id TEXT,target_date TEXT)")
        self.db.execute("INSERT INTO children VALUES ('child-a','family-a','primary_1',1)")
        self.today = date.today().isoformat()
        self.service = object.__new__(TaskService)
        self.service.repository = self.repo
        self.service.auth_service = SimpleNamespace(authenticate=lambda _: {
            "family": {"id": "family-a"}, "user": {"id": "parent-a"}})

    def task(self, task_id, *, status="in_progress", family="family-a", child="child-a", slot=None):
        self.db.execute("""INSERT INTO tasks
            (id,family_id,child_id,title,type,status,scheduled_date,scheduled_start,
             reward_points,requires_parent_confirmation,created_at,updated_at,learning_slot)
            VALUES (?,?,?,?,'learning',?,?,'09:00',0,0,1,1,?)""",
            (task_id, family, child, "测试体验 · 同名不代表测试数据", status, self.today, slot))
        self.db.raw.commit()
        return task_id

    def review(self, task_id, *, kind="synthetic_review", family="family-a", child="child-a"):
        # Use the real 085 schema. Test runs have no question/media/provider work.
        self.db.execute("""INSERT INTO learning_review_runs
            (id,family_id,child_id,week_start,task_type,task_id,grade_code,grade_revision,
             status,reminder_status,total_questions,estimated_seconds,coverage_json,policy_json,
             created_at,updated_at)
            VALUES (?,?,?,?,?,?,'primary_1',1,'scheduled','silent_demo',0,0,'{}','{}',1,1)""",
            ("review-" + task_id, family, child, task_id, kind, task_id))
        self.db.raw.commit()

    @staticmethod
    def ids(rows):
        return [row["id"] for row in rows]

    def test_today_and_task_list_hide_demo_but_preserve_real_review_and_same_title(self):
        self.review(self.task("demo", slot="weekend_review"))
        self.review(self.task("real-review", slot="weekend_review"), kind="weekend_review")
        self.task("ordinary")
        before = self.db.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        for result in (self.service.list_today("parent", {"childId": "child-a"}),
                       self.service.list_tasks("parent", {"startDate": self.today, "status": "in_progress"})):
            self.assertEqual(set(self.ids(result["tasks"])), {"real-review", "ordinary"})
        self.assertEqual(self.db.execute("SELECT * FROM tasks ORDER BY id").fetchall(), before)

    def test_camera_current_task_ignores_unassigned_demo_and_keeps_real_task(self):
        self.review(self.task("demo", slot="weekend_review"))
        self.assertIsNone(self.service.current_in_progress("parent", device_id="camera-a", include_unassigned=True))
        self.task("real", status="delayed")
        self.assertEqual(self.service.current_in_progress("parent", device_id="camera-a", include_unassigned=True)["id"], "real")
        self.assertIsNone(self.service.current_in_progress("parent", device_id="other-camera"))

    def test_scheduler_never_advances_or_reminds_demo_tasks(self):
        self.review(self.task("demo", status="scheduled", slot="weekend_review"))
        self.task("real", status="scheduled")
        runtime = object.__new__(TaskRuntimeService)
        runtime.repository = self.repo
        runtime._advance_task = Mock(side_effect=lambda conn, task, **_: (task, []))
        runtime.tick(now=datetime.now().astimezone())
        self.assertEqual([call.args[1]["id"] for call in runtime._advance_task.call_args_list], ["real"])

    def test_demo_does_not_change_real_family_conversation_focus_policy(self):
        policy = object.__new__(ConversationPolicyService)
        policy.conversation_repository = SimpleNamespace(
            daily_free_chat_seconds=lambda *args, **kwargs: 0,
            active_session=lambda *args, **kwargs: None,
        )
        rules = {"freeChatEnabled": True, "homeworkModeRestricted": True, "bedtimeQuietEnabled": False}
        def evaluate():
            return policy.evaluate_chat_turn(self.db, family_id="family-a", rules=rules, now_ms=1000)
        before = evaluate()
        self.review(self.task("demo", slot="weekend_review"))
        self.assertEqual(evaluate(), before)
        self.assertFalse(evaluate()["focusRestricted"])
        self.task("other-family", family="family-b", child="child-b")
        self.assertFalse(evaluate()["focusRestricted"])
        self.task("real")
        self.assertTrue(evaluate()["focusRestricted"])

    def test_conversation_retains_legacy_active_statuses_and_old_database_behavior(self):
        for index, status in enumerate(("in_progress", "started", "active")):
            self.task(f"legacy-{index}", family=f"family-{index}", status=status)
            self.assertTrue(self.repo.has_active_task(self.db, family_id=f"family-{index}"))
        self.db.execute("DROP TABLE learning_review_runs")
        self.assertTrue(self.repo.has_active_task(self.db, family_id="family-0"))

    def test_exclusion_uses_persisted_type_and_matching_family_child(self):
        self.review(self.task("different-family"), family="family-b")
        self.review(self.task("different-child"), child="child-b")
        self.review(self.task("synthetic-without-title-or-slot"))
        self.db.execute("UPDATE tasks SET title='普通标题' WHERE id='synthetic-without-title-or-slot'")
        self.task("other-family", family="family-b", child="child-b")
        self.assertEqual(set(self.ids(self.repo.list_tasks(self.db, family_id="family-a"))),
                         {"different-family", "different-child"})

    def test_review_repository_can_still_progress_its_private_demo_task(self):
        self.review(self.task("demo", slot="weekend_review"))
        reviews = LearningReviewRepository(self.db)
        with self.db.transaction() as conn:
            run = reviews.run(conn, "family-a", "child-a", "review-demo")
            reviews.task_status(conn, run, "completed", 123)
            row = self.repo.get_task(conn, family_id="family-a", task_id="demo")
            self.assertEqual(row["status"], "completed")
            self.assertEqual(row["completed_at"], 123)
            self.assertEqual(self.repo.list_tasks(conn, family_id="family-a"), [])

    def test_pre_review_database_keeps_existing_tasks_in_all_projections(self):
        self.task("real")
        # No migration or implicit table creation occurs on this compatibility path.
        self.db.execute("DROP TABLE learning_review_runs")
        self.assertEqual(self.ids(self.repo.list_tasks(self.db, family_id="family-a")), ["real"])
        self.assertEqual(self.ids(self.repo.list_in_progress_tasks(self.db, family_id="family-a")), ["real"])
        self.assertEqual(self.ids(self.repo.list_scheduler_tasks(self.db, end_date=self.today)), ["real"])

    def test_long_scheduler_list_filters_demo_after_first_query_batch(self):
        for index in range(202):
            self.task(f"task-{index:03}")
        self.review("task-201")
        rows = self.repo.list_scheduler_tasks(self.db, end_date=self.today)
        self.assertEqual(len(rows), 201)
        self.assertNotIn("task-201", self.ids(rows))

    def test_only_expected_missing_table_is_ignored(self):
        row = {"id": "real", "family_id": "family-a", "child_id": "child-a"}
        for error in (RuntimeError("connection lost"), RuntimeError(1146, "Table 'other' does not exist"),
                      RuntimeError(1054, "Unknown column in learning_review_runs"), RuntimeError()):
            with self.subTest(error=repr(error)):
                conn = SimpleNamespace(execute=Mock(side_effect=error))
                with self.assertRaises(RuntimeError):
                    self.repo._without_synthetic_reviews(conn, [row])
        conn = SimpleNamespace(execute=Mock(side_effect=RuntimeError(1146, "Table 'db.learning_review_runs' doesn't exist")))
        self.assertEqual(self.repo._without_synthetic_reviews(conn, [row]), [row])


if __name__ == "__main__":
    unittest.main()
