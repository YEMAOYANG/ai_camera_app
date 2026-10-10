"""Private authoring dispatch safety on local files and mocked providers."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from content.textbook_batch import build_plan
from content.textbook_batch_generation import SCOPE_SCHEMA, freeze_input
from content.textbook_catalog import canonical, digest
from scripts.generate_textbook_batch import matches, select_inputs, select_reservations
from services.textbook_batch_generation_service import TextbookBatchGenerationService


class PrivateBatchGenerationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()
        original = Path(__file__).parents[1] / "content/textbooks/official-directories-v1/bnu-math-g1-lower-2022-standard.directory-c4be26f1b4e105927cc4b5a0.json"
        self.manifest = json.loads(original.read_text())
        self.source = self.catalog / "book.json"
        self.source.write_text(canonical(self.manifest))
        _, self.tasks = build_plan(self.catalog, superseded_ids=set())
        self.book = next(task for task in self.tasks if task["kind"] == "book_exploration")
        self.runtime = Mock(base_url="http://127.0.0.1:3100")
        self.runtime.start_generation.return_value = SimpleNamespace(job_id="job-1", status="running")
        self.service = TextbookBatchGenerationService(self.root / "drafts", self.runtime)

    def prepare(self):
        frozen = freeze_input(self.book)
        return self.service.prepare(frozen), frozen

    def arguments(self, **changes):
        values = dict(task_id=None, kind=None, subject="math", grade="primary_1", volume="lower", edition=None,
                      enrich_existing=False, reviewed_scope=None, limit=1, start=False, poll=False,
                      work_directory=self.root / "drafts")
        values.update(changes)
        return SimpleNamespace(**values)

    def test_provider_free_prepare_freezes_real_directory_and_pending_reviews(self):
        result, frozen = self.prepare()
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["providerDispatched"])
        self.assertEqual(frozen["manifest"], self.manifest)
        self.assertEqual(frozen["binding"]["subject"], "math")
        self.assertIn(self.manifest["units"][0]["title"], frozen["requirement"])
        self.assertIn(self.manifest["units"][0]["lessons"][0]["title"], frozen["requirement"])
        self.assertFalse(frozen["publicationAllowed"])
        self.assertFalse(frozen["studentDeliveryAllowed"])
        self.assertFalse(frozen["qualityPolicyRuntimeEnforcementVerified"])
        self.runtime.start_generation.assert_not_called()
        self.assertEqual(self.service.prepare(frozen), result)
        lines = frozen["requirement"].splitlines()
        self.assertEqual(lines[0], "MIRA_TEXTBOOK_BATCH_V2")
        context = json.loads(lines[1])
        self.assertEqual(context, frozen["runtimeBatchContext"])
        self.assertEqual(context["taskId"], frozen["taskId"])
        self.assertEqual(context["binding"], self.book["scope"])
        self.assertEqual(context["teacher"]["teacherName"], "小数老师")
        self.assertEqual(context["teacher"]["avatarPath"], "/avatars/teacher.png")
        self.assertFalse(context["teacher"]["tts"]["fallbackAllowed"])

    def test_private_design_frozen_with_exact_unit_and_no_approval(self):
        unit = next(task for task in self.tasks if task["kind"] == "unit_guide")
        design = {"schemaVersion": "mira.textbook.activity-design.v1", "status": "draft",
                  "kind": "unit_guide", "binding": deepcopy(unit["scope"]), "manifestSha256": unit["manifestSha256"],
                  "publicationAllowed": False, "designInstructions": "Use concrete, pictured object matching."}
        path = self.root / "design.json"
        path.write_text(canonical(design))
        frozen = freeze_input(unit, design_plan_path=path)
        self.assertEqual(frozen["activityDesignSha256"], digest(design))
        self.assertFalse(frozen["publicationAllowed"])
        design["binding"]["unitId"] = "another-unit"
        path.write_text(canonical(design))
        with self.assertRaisesRegex(ValueError, "does not match"):
            freeze_input(unit, design_plan_path=path)

    def test_new_low_reading_drafts_freeze_actual_viewport_contract_without_rewriting_v2(self):
        current = freeze_input(self.book)
        self.assertEqual(current["authoringPrompt"]["version"], "4")
        contract = current["activityPresentationContract"]
        self.assertEqual(contract["minimumActualTouchTargetPx"], 48)
        self.assertEqual(contract["requiredViewportWidths"], [360, 768, 1280])
        self.assertTrue(contract["browserMeasurementRequired"])
        self.assertFalse(contract["browserMeasurementPassed"])
        self.assertIn('"activityPresentationContract"', current["requirement"])
        legacy = freeze_input(self.book, prompt_path=Path(__file__).parents[1] /
                              "prompts/textbook-batch-authoring.v2.json")
        self.assertNotIn("activityPresentationContract", legacy)
        self.assertEqual(legacy["authoringPrompt"]["version"], "2")
        self.assertEqual(legacy["runtimeBatchContext"], current["runtimeBatchContext"])
        self.assertEqual(legacy["binding"], current["binding"])
        self.assertEqual(legacy["manifestSha256"], current["manifestSha256"])
        self.service.prepare(legacy)
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.service.prepare(current)
        self.runtime.start_generation.assert_not_called()

    def test_single_dispatch_repeated_start_poll_and_real_saved_artifact(self):
        _, frozen = self.prepare()
        task_id = frozen["taskId"]
        self.service.start(task_id)
        self.service.start(task_id)
        self.runtime.start_generation.assert_called_once()
        options = self.runtime.start_generation.call_args.kwargs
        self.assertFalse(options["enable_tts"])
        self.assertFalse(options["enable_web_search"])
        self.assertTrue(options["enable_image_generation"])
        self.assertFalse(options["enable_video_generation"])
        self.runtime.get_generation_job.return_value = SimpleNamespace(
            job_id="job-1", status="succeeded", progress=100, classroom_id="draft-1")
        artifact = {"id": "draft-1", "stage": {"id": "draft-1"}, "scenes": [
            {"id": "game", "type": "interactive", "content": {"widgetType": "game"}, "actions": [
                {"type": "speech", "text": "观察这些物体。"}]},
            {"id": "model", "type": "interactive", "content": {"widgetType": "visualization3d"}, "actions": []}]}
        self.runtime.get_classroom.return_value = artifact
        result = self.service.poll(task_id)
        self.assertEqual(result["status"], "generated_needs_review")
        self.assertFalse(result["qualityPassed"])
        self.assertEqual(result["classroomSha256"], digest(artifact))
        self.assertIn("qwen_narration_and_asr_pending", result["qualityIssues"])
        self.assertNotIn("explicit_game_widget_missing", result["qualityIssues"])
        folder = self.root / "drafts" / task_id
        self.assertEqual(json.loads((folder / "classroom.json").read_text()), artifact)
        self.assertFalse(json.loads((folder / "quality-report.json").read_text())["publicationAllowed"])
        self.assertEqual(self.service.poll(task_id), result)
        self.service.start(task_id)
        self.runtime.start_generation.assert_called_once()
        self.runtime.get_generation_job.assert_called_once()

    def test_incompatible_design_cues_stop_before_any_provider_dispatch(self):
        design = {"schemaVersion": "mira.textbook.activity-design.v1", "status": "draft",
                  "kind": self.book["kind"], "binding": deepcopy(self.book["scope"]),
                  "manifestSha256": self.book["manifestSha256"], "publicationAllowed": False,
                  "designInstructions": "Observe pictured objects.",
                  "finiteCues": [{"cueId": "intro.with.dot", "teacherText": "看一看。"}],
                  "scenes": [{"entryCueId": "intro.with.dot"}]}
        path = self.root / "design.json"
        path.write_text(canonical(design))
        with self.assertRaisesRegex(ValueError, "incompatible"):
            freeze_input(self.book, design_plan_path=path)
        design["finiteCues"][0]["cueId"] = "intro_safe"
        design["scenes"][0]["entryCueId"] = "unknown"
        path.write_text(canonical(design))
        with self.assertRaisesRegex(ValueError, "unknown narration"):
            freeze_input(self.book, design_plan_path=path)
        design["scenes"][0]["entryCueId"] = "intro_safe"
        path.write_text(canonical(design))
        self.assertEqual(freeze_input(self.book, design_plan_path=path)["activityDesign"], design)
        self.runtime.start_generation.assert_not_called()

    def test_timeout_and_process_crash_remain_fenced_without_paid_retry(self):
        _, frozen = self.prepare()
        task_id = frozen["taskId"]
        self.runtime.start_generation.side_effect = TimeoutError("do not log request details")
        result = self.service.start(task_id)
        self.assertEqual(result["status"], "dispatch_unknown")
        self.service.start(task_id)
        self.service.poll(task_id)
        self.runtime.start_generation.assert_called_once()
        self.runtime.get_generation_job.assert_not_called()
        state_file = self.root / "drafts" / task_id / "state.json"
        state = json.loads(state_file.read_text())
        state["status"] = "prepared"
        state_file.write_text(canonical(state))
        self.runtime.start_generation.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.service.start(task_id)
        self.assertEqual(json.loads(state_file.read_text())["status"], "dispatching")
        self.service.start(task_id)
        self.assertEqual(self.runtime.start_generation.call_count, 2)

    def test_changed_input_or_runtime_cannot_reuse_reservation(self):
        _, frozen = self.prepare()
        different = deepcopy(frozen)
        different["requirement"] += "different teaching scope"
        different["inputSha256"] = digest({k: v for k, v in different.items() if k != "inputSha256"})
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.service.prepare(different)
        self.service.start(frozen["taskId"])
        other = TextbookBatchGenerationService(self.root / "drafts", Mock(base_url="http://127.0.0.1:3999"))
        with self.assertRaisesRegex(ValueError, "different runtime"):
            other.start(frozen["taskId"])
        with self.assertRaisesRegex(ValueError, "different runtime"):
            other.poll(frozen["taskId"])
        self.runtime.start_generation.assert_called_once()

    def test_source_task_and_pedagogy_mutations_stop_before_dispatch(self):
        tampered = deepcopy(self.book)
        tampered["directoryScope"][0]["lessons"][0]["title"] = "Invented lesson"
        with self.assertRaisesRegex(ValueError, "directory scope"):
            freeze_input(tampered)
        self.source.write_text(canonical({**self.manifest, "title": "Changed source"}))
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            freeze_input(self.book)
        self.runtime.start_generation.assert_not_called()

    def test_lessons_require_explicit_matching_nonempty_reviewed_scope(self):
        lesson = next(task for task in self.tasks if task["kind"] == "lesson_courseware")
        with self.assertRaisesRegex(ValueError, "explicit reviewed scope"):
            freeze_input(lesson)
        reviewed = {"schemaVersion": SCOPE_SCHEMA, "taskId": lesson["taskId"], "binding": lesson["scope"],
            "manifestSha256": lesson["manifestSha256"], "reviewStatus": "approved", "reviewer": "synthetic reviewer",
            "basis": "Synthetic isolated scope fixture; no publication approval", "assessmentMode": "objective",
            "objectives": [], "knowledgePoints": [], "priorKnowledge": [], "excludedTopics": []}
        path = self.root / "scope.json"
        path.write_text(canonical(reviewed))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            freeze_input(lesson, reviewed_scope_path=path)
        reviewed.update(objectives=["Compare two pictured groups within 5"], knowledgePoints=["one-to-one comparison"])
        path.write_text(canonical(reviewed))
        frozen = freeze_input(lesson, reviewed_scope_path=path)
        self.assertEqual(frozen["reviewedLessonScope"], reviewed)
        self.assertTrue(frozen["generationOptions"]["enable_video_generation"])
        reviewed["binding"] = {**reviewed["binding"], "gradeCode": "primary_6"}
        path.write_text(canonical(reviewed))
        with self.assertRaisesRegex(ValueError, "binding"):
            freeze_input(lesson, reviewed_scope_path=path)
        self.runtime.start_generation.assert_not_called()

    def test_failed_or_mismatched_upstream_result_is_never_redispatched(self):
        _, frozen = self.prepare()
        task_id = frozen["taskId"]
        self.service.start(task_id)
        self.runtime.get_generation_job.return_value = SimpleNamespace(job_id="other-job", status="succeeded", progress=100)
        with self.assertRaisesRegex(ValueError, "identity changed"):
            self.service.poll(task_id)
        self.runtime.get_generation_job.return_value = SimpleNamespace(job_id="job-1", status="failed", progress=12)
        self.assertEqual(self.service.poll(task_id)["status"], "failed_needs_reconciliation")
        self.service.start(task_id)
        self.runtime.start_generation.assert_called_once()

    def test_concurrent_start_cannot_dispatch_twice(self):
        _, frozen = self.prepare()
        entered, release = Event(), Event()
        def dispatch(**kwargs):
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError()
            return SimpleNamespace(job_id="job-1", status="running")
        self.runtime.start_generation.side_effect = dispatch
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(self.service.start, frozen["taskId"])
            self.assertTrue(entered.wait(timeout=5))
            try:
                with self.assertRaisesRegex(ValueError, "already being operated"):
                    self.service.start(frozen["taskId"])
            finally:
                release.set()
            self.assertEqual(running.result(timeout=5)["status"], "generating")
        self.runtime.start_generation.assert_called_once()

    def test_bounded_prepare_advances_and_explicit_task_id_recovers_original(self):
        path = self.root / "tasks.jsonl"
        path.write_text("".join(canonical(task) + "\n" for task in self.tasks))
        args = self.arguments(kind="unit_guide")
        first = select_inputs(path, args, self.service)
        self.assertEqual(len(first), 1)
        self.service.prepare(first[0])
        second = select_inputs(path, args, self.service)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0]["taskId"], second[0]["taskId"])
        self.service.prepare(second[0])
        third = select_inputs(path, args, self.service)
        self.assertNotIn(third[0]["taskId"], {first[0]["taskId"], second[0]["taskId"]})
        exact = select_inputs(path, self.arguments(kind="unit_guide", task_id=[first[0]["taskId"]]), self.service)
        self.assertEqual(exact, first)
        self.runtime.start_generation.assert_not_called()
        # A changed source is rejected before an existing task could be skipped.
        self.source.write_text(canonical({**self.manifest, "title": "Unreviewed source change"}))
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            select_inputs(path, args, self.service)

    def test_queue_start_and_poll_filter_states_but_explicit_id_is_idempotent(self):
        _, book = self.prepare()
        unit = freeze_input(next(task for task in self.tasks if task["kind"] == "unit_guide"))
        self.service.prepare(unit)
        start_args = self.arguments(start=True)
        first = select_reservations(start_args, self.service)
        self.assertEqual(len(first), 1)
        self.service.start(first[0])
        second = select_reservations(start_args, self.service)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first, second)
        self.service.start(second[0])
        self.assertEqual(select_reservations(start_args, self.service), [])
        self.assertEqual(self.runtime.start_generation.call_count, 2)
        poll_args = self.arguments(poll=True, limit=2)
        self.assertEqual(set(select_reservations(poll_args, self.service)), {book["taskId"], unit["taskId"]})
        self.runtime.get_generation_job.return_value = SimpleNamespace(job_id="job-1", status="failed", progress=10)
        self.service.poll(first[0])
        self.assertEqual(select_reservations(poll_args, self.service), second)
        explicit = self.arguments(start=True, task_id=first)
        self.assertEqual(select_reservations(explicit, self.service), first)
        self.assertEqual(self.service.start(first[0])["status"], "failed_needs_reconciliation")
        self.assertEqual(self.runtime.start_generation.call_count, 2)

    def test_volume_and_edition_filters_preserve_exact_book_binding(self):
        self.assertTrue(matches(self.book, self.arguments(edition=self.manifest["editionId"])))
        self.assertFalse(matches(self.book, self.arguments(volume="upper")))
        self.assertFalse(matches(self.book, self.arguments(edition="another-edition")))
        self.assertTrue(matches(freeze_input(self.book), self.arguments(edition=self.manifest["editionId"])))


if __name__ == "__main__":
    unittest.main()
