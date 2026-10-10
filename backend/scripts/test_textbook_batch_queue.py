"""Provider-free counterexamples for the whole-catalog operator."""
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.run_textbook_batch_queue as cli
from content.textbook_batch import build_plan
from content.textbook_catalog import canonical, digest
from services.textbook_batch_generation_service import atomic_json
from services.textbook_batch_queue_service import INDEX_SCHEMA, TextbookBatchQueueService


class QueueTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()
        sample = Path(__file__).parents[1] / "content/textbooks/official-directories-v1/bnu-math-g1-lower-2022-standard.directory-c4be26f1b4e105927cc4b5a0.json"
        self.source = self.catalog / "book.json"
        self.source.write_bytes(sample.read_bytes())
        _, self.tasks = build_plan(self.catalog, superseded_ids=set())
        self.eligible = [task for task in self.tasks if task["kind"] != "lesson_courseware"][:4]
        self.tasks_path = self.root / "tasks.jsonl"
        self.tasks_path.write_text("".join(canonical(task) + "\n" for task in self.tasks))
        self.runtime = Mock(base_url="http://127.0.0.1:3100")
        self.runtime.start_generation.side_effect = lambda **_kwargs: SimpleNamespace(
            job_id="job-" + str(self.runtime.start_generation.call_count), status="running")
        self.runtime.get_generation_job.side_effect = lambda identity: SimpleNamespace(
            job_id=identity, status="running", progress=30, classroom_id=None)
        self.queue = TextbookBatchQueueService(self.root / "queue", self.runtime, minimum_free_bytes=0)
        self.queue.initialize(self.tasks_path, enrich_existing=True)

    def index(self, tasks=None):
        entries = []
        for task in tasks or self.eligible:
            path = self.root / (task["taskId"] + "-design.json")
            design = {"schemaVersion": "mira.textbook.activity-design.v1", "kind": task["kind"],
                "binding": task["scope"], "manifestSha256": task["manifestSha256"],
                "status": "draft", "publicationAllowed": False,
                "designInstructions": "Synthetic local mock: observe meaningful pictures and match them."}
            path.write_text(canonical(design))
            entries.append({"taskId": task["taskId"], "designPlanPath": str(path)})
        path = self.root / "index.json"
        path.write_text(canonical({"schemaVersion": INDEX_SCHEMA, "entries": entries}))
        return path

    def admit(self, tasks=None):
        self.queue.admit_index(self.index(tasks))

    def test_full_inventory_retains_missing_lesson_scope_and_rights_do_not_block_private(self):
        status = self.queue.status()
        self.assertEqual(status["taskCount"], len(self.tasks))
        lessons = sum(task["kind"] == "lesson_courseware" for task in self.tasks)
        self.assertEqual(status["statusCounts"], {"source_blocked": lessons, "design_pending": len(self.tasks) - lessons})
        self.assertEqual(status["blockerCounts"]["reviewed_lesson_scope_required"], lessons)
        self.admit([self.eligible[0]])
        self.assertEqual(self.queue.status()["statusCounts"]["pending"], 1)
        prepared = self.queue.prepare(limit=2)
        self.assertEqual(len(prepared), 1)
        frozen = json.loads((self.queue.drafts / self.eligible[0]["taskId"] / "input.json").read_text())
        self.assertEqual(frozen["authoringPrompt"]["version"], "4")
        self.assertFalse(frozen["sourceReviewResolved"])
        self.assertFalse(frozen["publicationAllowed"])
        self.runtime.start_generation.assert_not_called()

    def test_whole_index_validated_before_any_admission(self):
        path = self.index()
        value = json.loads(path.read_text())
        value["entries"][-1]["taskId"] = "0" * 64
        path.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, "entry_invalid"):
            self.queue.admit_index(path)
        self.assertFalse((self.queue.directory / "authoring").exists())
        self.runtime.start_generation.assert_not_called()

    def test_admission_idempotent_but_different_design_or_duplicate_rejected(self):
        path = self.index()
        self.queue.admit_index(path)
        self.queue.admit_index(path)
        value = json.loads(path.read_text())
        value["entries"].append(value["entries"][0])
        path.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.queue.admit_index(path)
        design_path = Path(value["entries"][0]["designPlanPath"])
        design = json.loads(design_path.read_text())
        design["designInstructions"] += " changed"
        design_path.write_text(canonical(design))
        with self.assertRaisesRegex(ValueError, "source_changed"):
            self.queue.prepare()

    def test_two_slots_failure_progresses_other_tasks_without_redispatching_failed(self):
        self.admit()
        first = self.queue.run_once()
        self.assertEqual(len(first["started"]), 2)
        self.assertEqual(first["summary"]["occupiedJobSlots"], 2)
        second = self.queue.run_once()
        self.assertEqual(second["started"], [])
        self.assertEqual(self.runtime.start_generation.call_count, 2)
        first_id = first["started"][0]["taskId"]
        self.runtime.get_generation_job.side_effect = lambda identity: SimpleNamespace(
            job_id=identity, status="failed" if identity == "job-1" else "running", progress=31)
        third = self.queue.run_once()
        self.assertEqual(len(third["started"]), 1)
        self.assertEqual(third["summary"]["statusCounts"]["failed_needs_reconciliation"], 1)
        receipt = json.loads((self.queue.drafts / first_id / "upstream-terminal-response.json").read_text())
        self.assertEqual(receipt["job"]["status"], "failed")
        self.queue.run_once()
        self.assertEqual(self.runtime.start_generation.call_count, 3)

    def test_unknown_timeouts_keep_both_slots_and_are_never_resent(self):
        self.admit()
        self.runtime.start_generation.side_effect = TimeoutError("private request must not be logged")
        first = self.queue.run_once()
        self.assertEqual(first["summary"]["statusCounts"]["dispatch_unknown"], 2)
        again = self.queue.run_once()
        self.assertEqual(again["started"], [])
        self.assertEqual(again["summary"]["occupiedJobSlots"], 2)
        self.assertEqual(self.runtime.start_generation.call_count, 2)
        self.runtime.get_generation_job.assert_not_called()

    def test_ambiguous_known_job_is_get_only_reconciled_and_still_occupies_slot(self):
        self.admit([self.eligible[0]])
        self.queue.run_once(max_starts=1)
        self.runtime.get_generation_job.side_effect = lambda identity: SimpleNamespace(
            job_id=identity, status="ambiguous", progress=30)
        result = self.queue.run_once(max_starts=0)
        self.assertEqual(result["summary"]["occupiedJobSlots"], 1)
        self.runtime.get_generation_job.reset_mock()
        self.queue.run_once(max_starts=0)
        self.assertEqual(self.runtime.get_generation_job.call_count, 2)
        self.assertEqual(self.runtime.start_generation.call_count, 1)

    def test_returned_identity_survives_state_crash_and_recovers_only_with_get(self):
        self.admit([self.eligible[0]])
        def crash(path, value, **kwargs):
            if Path(path).name == "state.json" and value.get("status") == "generating":
                raise KeyboardInterrupt()
            return atomic_json(path, value, **kwargs)
        with patch("services.textbook_batch_generation_service.atomic_json", side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.queue.run_once(max_starts=1)
        folder = self.queue.drafts / self.eligible[0]["taskId"]
        self.assertEqual(json.loads((folder / "state.json").read_text())["status"], "dispatching")
        self.assertTrue((folder / "upstream-dispatch-response.json").exists())
        result = self.queue.run_once(max_starts=0)
        self.assertEqual(result["summary"]["statusCounts"]["generating"], 1)
        self.assertEqual(self.runtime.start_generation.call_count, 1)
        self.assertEqual(self.runtime.get_generation_job.call_count, 2)

    def test_unknown_returned_identity_get404_never_reposts_or_frees_slot(self):
        self.admit([self.eligible[0]])
        self.queue.run_once(max_starts=1)
        folder = self.queue.drafts / self.eligible[0]["taskId"]
        state = json.loads((folder / "state.json").read_text())
        state.update(status="dispatch_unknown", runtimeJobId=None)
        atomic_json(folder / "state.json", state)
        self.runtime.get_generation_job.side_effect = FileNotFoundError()
        result = self.queue.run_once(max_starts=0)
        self.assertEqual(result["summary"]["occupiedJobSlots"], 1)
        self.assertEqual(len(result["operatorErrors"]), 1)
        self.queue.run_once(max_starts=0)
        self.assertEqual(self.runtime.start_generation.call_count, 1)

    def test_source_manifest_changed_after_preparation_stops_before_post(self):
        self.admit()
        self.queue.prepare()
        manifest = json.loads(self.source.read_text())
        manifest["title"] += " changed"
        self.source.write_text(canonical(manifest))
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            self.queue.run_once()
        self.runtime.start_generation.assert_not_called()

    def test_tasks_byte_drift_rejected_even_with_semantically_same_json(self):
        self.tasks_path.write_text(self.tasks_path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "source_or_policy_changed"):
            self.queue.run_once()
        self.runtime.start_generation.assert_not_called()

    def test_capacity_block_preserves_prepared_state_and_is_recoverable(self):
        self.admit()
        self.queue.prepare()
        self.queue.minimum_free_bytes = 10 ** 30
        result = self.queue.run_once()
        self.assertEqual(result["started"], [])
        self.assertEqual(result["summary"]["capacity"]["status"], "capacity_blocked")
        self.assertEqual(result["summary"]["statusCounts"]["prepared"], 2)
        self.runtime.start_generation.assert_not_called()
        self.queue.minimum_free_bytes = 0
        self.assertEqual(len(self.queue.run_once()["started"]), 2)

    def test_filter_admission_cannot_ignore_other_inflight_slots(self):
        self.admit()
        self.queue.run_once(filters={"taskId": [task["taskId"] for task in self.eligible[:2]]})
        result = self.queue.run_once(filters={"taskId": [self.eligible[2]["taskId"]]})
        self.assertEqual(result["started"], [])
        self.assertEqual(len(result["polled"]), 2)

    def test_queue_lock_prevents_parallel_operator(self):
        with self.queue._lock():
            with self.assertRaisesRegex(ValueError, "already_running"):
                TextbookBatchQueueService(self.queue.directory).status()

    def test_additive_hold_freezes_input_permits_prepare_and_skips_only_held_dispatch(self):
        self.admit()
        identity = self.eligible[0]["taskId"]
        admission = (self.queue.directory / "authoring" / identity / "admission.json").read_bytes()
        receipt = self.queue.hold_tasks([identity], reason="local original authoring")
        self.assertFalse((self.queue.drafts / identity / "state.json").exists())
        self.assertEqual(self.queue.hold_tasks([identity], reason="local original authoring"), receipt)
        self.queue.prepare(limit=1, filters={"taskId": [identity]})
        folder = self.queue.drafts / identity
        before = (folder / "state.json").read_bytes()
        frozen = json.loads((folder / "input.json").read_text())
        self.assertEqual(receipt["heldTasks"][0]["inputSha256"], frozen["inputSha256"])
        result = self.queue.run_once()
        self.assertEqual(len(result["started"]), 2)
        self.assertNotIn(identity, [value["taskId"] for value in result["started"]])
        self.assertEqual((folder / "state.json").read_bytes(), before)
        self.assertEqual((self.queue.directory / "authoring" / identity / "admission.json").read_bytes(), admission)
        self.assertEqual(result["summary"]["operatorHoldCount"], 1)

    def test_hold_invalid_batch_or_malformed_receipt_never_dispatches(self):
        self.admit()
        identity = self.eligible[0]["taskId"]
        with self.assertRaisesRegex(ValueError, "unknown_task"):
            self.queue.hold_tasks([identity, "0" * 64], reason="local authoring")
        self.assertFalse((self.queue.directory / "operator-holds").exists())
        self.queue.hold_tasks([identity], reason="local authoring")
        path = self.queue.directory / "operator-holds" / (identity + ".json")
        value = json.loads(path.read_text())
        value["inputSha256"] = "0" * 64
        value["holdSha256"] = digest({k: v for k, v in value.items() if k != "holdSha256"})
        path.write_text(canonical(value))
        with self.assertRaisesRegex(ValueError, "hold_integrity_failed"):
            self.queue.run_once()
        self.runtime.start_generation.assert_not_called()

    def test_hold_cannot_cancel_inflight_and_cli_is_provider_free(self):
        self.admit([self.eligible[0]])
        identity = self.eligible[0]["taskId"]
        with patch("core.config.AppConfig.from_env") as config, patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(cli.main(["--hold-task", "--task-id", identity, "--hold-reason", "local authoring",
                                       "--queue-directory", str(self.queue.directory)]), 0)
            config.assert_not_called()
        other = self.eligible[1]
        self.admit([other])
        self.queue.run_once(max_starts=1, filters={"taskId": [other["taskId"]]})
        with self.assertRaisesRegex(ValueError, "cannot_cancel"):
            self.queue.hold_tasks([other["taskId"]], reason="local authoring")

    def test_success_saves_real_classroom_and_never_marks_quality_or_publication_passed(self):
        self.admit([self.eligible[0]])
        self.queue.run_once(max_starts=1)
        classroom = {"id": "actual-classroom", "stage": {"id": "actual-classroom"}, "scenes": []}
        self.runtime.get_generation_job.side_effect = lambda identity: SimpleNamespace(
            job_id=identity, status="succeeded", progress=100, classroom_id=classroom["id"])
        self.runtime.get_classroom.return_value = classroom
        result = self.queue.run_once(max_starts=0)
        self.assertEqual(result["summary"]["statusCounts"]["generated_needs_review"], 1)
        state = result["polled"][0]
        self.assertFalse(state["qualityPassed"])
        self.assertFalse(state["publicationAllowed"])
        self.assertEqual(state["classroomSha256"], digest(classroom))
        self.queue.run_once(max_starts=0)
        self.assertEqual(self.runtime.start_generation.call_count, 1)
        self.runtime.get_classroom.assert_called_once()

    def test_cli_invalid_audio_limit_stops_before_configuration_or_any_dispatch(self):
        with patch("core.config.AppConfig.from_env") as config, patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main(["--run-once", "--narrate-generated", "--audio-limit", "25",
                          "--queue-directory", str(self.queue.directory)])
            config.assert_not_called()

    def test_bounded_watch_limits_total_starts_across_multiple_iterations(self):
        fake = Mock()
        fake.run_once.side_effect = [
            {"started": [{}, {}], "polled": [], "summary": {"occupiedJobSlots": 2}},
            {"started": [{}], "polled": [{}], "summary": {"occupiedJobSlots": 1}},
            {"started": [], "polled": [{}], "summary": {"occupiedJobSlots": 0}}]
        config = Mock(OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100", INTERNAL_API_TOKEN="synthetic-only")
        with patch.object(cli, "TextbookBatchQueueService", return_value=fake), patch(
                "core.config.AppConfig.from_env", return_value=config), patch(
                "integrations.openmaic_full_runtime_client.OpenMaicFullRuntimeClient"), patch(
                "time.monotonic", side_effect=iter(range(0, 1000, 20))), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(cli.main(["--watch", "--max-starts", "3", "--poll-seconds", "15",
                                       "--queue-directory", str(self.queue.directory)]), 0)
        self.assertEqual([call.kwargs["max_starts"] for call in fake.run_once.call_args_list], [2, 1, 0])


if __name__ == "__main__":
    unittest.main()
