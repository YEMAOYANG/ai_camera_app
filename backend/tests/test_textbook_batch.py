"""Offline task planning must preserve identity and never imply finished lessons."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from content.textbook_batch import build_plan, write_plan


def manifest(*, edition="synthetic-book", grade="primary_1", subject="chinese", revision="r1"):
    return {
        "schemaVersion": "mira.learning.textbook-manifest.v1", "editionId": edition, "revisionId": revision,
        "title": "Synthetic book", "publisher": "Synthetic publisher", "editionLabel": "Synthetic edition",
        "gradeCode": grade, "subject": subject, "volume": "upper", "schoolSystem": "six_year",
        "source": {"url": "https://basic.smartedu.cn/tchMaterial/detail?contentId=synthetic-resource",
                   "resourceId": "synthetic-resource", "verifiedAt": "2026-10-09"},
        "coverage": {"status": "complete", "note": "Synthetic directory"},
        "rightsReview": {"status": "pending", "basis": "Synthetic pending review"},
        "units": [{"unitId": "unit-1", "title": "Synthetic unit", "sequence": 1, "lessons": [
            {"nodeId": "lesson-1", "title": "Synthetic lesson", "sequence": 1,
             "printedPage": None, "pdfPage": None,
             "brief": {"status": "draft", "objectives": [], "knowledgePoints": [], "priorKnowledge": [],
                       "excludedTopics": [], "assessmentMode": "objective", "reviewNote": "Not reviewed"}}]}],
    }


def introduction():
    return {"introductionId": "intro-1", "title": "Original discovery", "hook": "Look and discover",
            "estimatedMinutes": 3, "authorship": "original", "nextNodeIds": ["lesson-1"], "steps": [
                {"kind": "discover", "title": "Observe", "body": "Observe the scene",
                 "cards": [{"label": "A", "response": "Observe A"}, {"label": "B", "response": "Observe B"}]},
                {"kind": "choose", "title": "Choose", "body": "Choose a scene",
                 "options": [{"label": "A", "response": "Try A"}, {"label": "B", "response": "Try B"}]},
                {"kind": "do", "title": "Act", "body": "Try it", "actions": ["Point to the picture"]},
                {"kind": "bridge", "title": "Continue", "body": "Explore the lesson", "question": "What did you observe?"}]}


class TextbookBatchTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.catalog = self.root / "catalog"
        self.catalog.mkdir()

    def put(self, name, value):
        path = self.catalog / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def plan(self, **kwargs):
        return build_plan(self.catalog, superseded_ids=set(), **kwargs)

    def test_conflicting_revision_and_immutable_book_changes_fail(self):
        original = manifest()
        self.put("original.json", original)
        changed = deepcopy(original)
        changed["units"][0]["lessons"][0]["title"] = "Changed lesson"
        self.put("nested/conflict.json", changed)
        with self.assertRaisesRegex(ValueError, "Conflicting immutable textbook revision"):
            self.plan()
        changed = manifest(revision="r2", grade="primary_2")
        self.put("nested/conflict.json", changed)
        with self.assertRaisesRegex(ValueError, "Immutable textbook identity changed"):
            self.plan()

    def test_identical_files_deduplicate_and_complete_revision_beats_later_index(self):
        self.put("a.json", manifest())
        self.put("nested/duplicate.json", manifest())
        later = manifest(revision="z-index")
        later.update(units=[], coverage={"status": "index_only", "note": "Only index"})
        self.put("later.json", later)
        summary, tasks = self.plan()
        self.assertEqual(summary["counts"]["identicalDuplicateFileCount"], 1)
        self.assertEqual(summary["counts"]["taskCount"], 3)
        self.assertEqual(summary["books"][0]["revisionId"], "r1")
        self.assertEqual(summary["books"][0]["alternatives"][0]["revisionId"], "z-index")
        self.assertEqual(len({task["taskId"] for task in tasks}), 3)
        self.assertFalse(summary["runtimeOrParentSelectionVerified"])

    def test_index_only_book_has_blocked_exploration_without_invented_units(self):
        value = manifest()
        value.update(units=[], coverage={"status": "index_only", "note": "No verified directory"})
        self.put("a.json", value)
        summary, tasks = self.plan()
        self.assertEqual([task["kind"] for task in tasks], ["book_exploration"])
        self.assertIn("official_directory_missing", tasks[0]["blockers"])
        self.assertEqual(tasks[0]["objectives"], [])
        self.assertEqual(summary["counts"]["knownDirectoryLessonNodes"], 0)
        self.assertFalse(summary["fullScopeEnumerated"])
        self.assertFalse(tasks[0]["executionReady"])

    def test_grade_and_book_identity_isolation_for_same_unit_node_ids(self):
        self.put("g1.json", manifest(edition="g1-chinese"))
        self.put("g2.json", manifest(edition="g2-math", grade="primary_2", subject="math"))
        summary, tasks = self.plan()
        lessons = [task for task in tasks if task["kind"] == "lesson_courseware"]
        self.assertEqual(len({task["taskId"] for task in lessons}), 2)
        self.assertEqual({task["scope"]["editionId"] for task in lessons}, {"g1-chinese", "g2-math"})
        for task in lessons:
            self.assertEqual(task["teachingProfile"]["gradeCode"], task["scope"]["gradeCode"])
            self.assertIn("lesson_segmentation_review_required", task["blockers"])
            self.assertEqual(task["objectives"], [])
        self.assertEqual(summary["scope"]["requestedSubjects"], ["chinese", "math", "english", "science"])

    def test_original_content_reuse_does_not_imply_audio_qa_publication(self):
        value = manifest()
        value["introduction"] = introduction()
        value["units"][0]["introduction"] = introduction()
        value["units"][0]["introduction"]["introductionId"] = "unit-intro-1"
        self.put("a.json", value)
        summary, tasks = self.plan()
        self.assertEqual(summary["counts"]["reusableOriginalContentTaskCount"], 2)
        for task in tasks[:2]:
            self.assertEqual(task["contentStatus"], "reuse_original_content_only")
            self.assertEqual(task["verification"]["narration"], "not_checked")
            self.assertFalse(task["published"])
            self.assertFalse(task["executionReady"])
        self.assertTrue(all("textbook_rights_review_pending" in task["blockers"] for task in tasks))

    def test_partial_directory_and_missing_policy_are_explicit_blocks(self):
        value = manifest()
        value["coverage"] = {"status": "partial", "note": "Only one verified unit"}
        self.put("a.json", value)
        summary, tasks = self.plan(quality_policy_path=self.root / "missing-policy.json")
        self.assertEqual(summary["bySubject"]["chinese"]["directoryPartialCount"], 1)
        for task in tasks:
            self.assertIn("official_directory_incomplete", task["blockers"])
            self.assertIn("courseware_quality_policy_missing", task["blockers"])

    def test_superseded_choices_excluded_unless_explicitly_requested(self):
        self.put("a.json", manifest())
        summary, tasks = build_plan(self.catalog, superseded_ids={"synthetic-resource"})
        self.assertEqual(summary["counts"]["excludedSupersededBookCount"], 1)
        self.assertEqual(tasks, [])
        included, tasks = build_plan(self.catalog, superseded_ids={"synthetic-resource"}, include_superseded=True)
        self.assertEqual(included["counts"]["activeBookCount"], 1)
        self.assertEqual(len(tasks), 3)

    def test_plan_is_deterministic_create_only_and_fails_before_partial_overwrite(self):
        self.put("a.json", manifest())
        summary, tasks = self.plan()
        self.assertEqual((summary, tasks), self.plan())
        output = self.root / "output"
        write_plan(output, summary, tasks)
        before = (output / "tasks.jsonl").stat().st_mtime_ns
        write_plan(output, summary, tasks)
        self.assertEqual(before, (output / "tasks.jsonl").stat().st_mtime_ns)
        (output / "summary.json").unlink()
        (output / "tasks.jsonl").write_text("different content", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            write_plan(output, summary, tasks)
        self.assertFalse((output / "summary.json").exists())
        self.assertEqual((output / "tasks.jsonl").read_text(), "different content")


if __name__ == "__main__":
    unittest.main()
