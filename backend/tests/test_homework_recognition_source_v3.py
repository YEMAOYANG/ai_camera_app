"""Source slot/conflict regressions use synthetic JSON, never live papers/AI."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from services.homework_math import check_item
from services.homework_recognition_parser import parse_recognition_response


POLICY = json.loads((Path(__file__).parents[1] / "content/homework_analysis_policy.v3.json").read_text())


class HomeworkSourceEvidenceV3Tests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "sourceQuestionLabel": "二（3）", "prompt": "5 − 4 = □", "studentAnswer": "□",
            "answerState": "blank", "answerRegions": [{"x": .6, "y": .2, "width": .05, "height": .06}],
            "visualEvidence": None, "type": "arithmetic", "confidence": .99,
            "annotationAmbiguous": False, "region": {"x": .1, "y": .18, "width": .6, "height": .1},
        }

    def parse(self, items, *, strict=True, version="v3"):
        return parse_recognition_response(json.dumps({"transcriptVersion": version, "pageReadable": True,
            "items": items}), maximum_items=40, maximum_answer_characters=1000,
            require_source_evidence=strict)

    def grade(self, item, **kwargs):
        return check_item(item, grade="primary_1", subject="math", policy=POLICY, **kwargs)

    def test_observed_empty_box_is_preserved_and_is_not_invented_wrong_answer(self):
        value, diagnostics = self.parse([self.raw])
        item = value["items"][0]
        self.assertEqual(diagnostics["issueCounts"], {})
        self.assertEqual(item["studentAnswer"], "□")
        result = self.grade(item)
        self.assertEqual(result["status"], "blank")
        self.assertEqual(result["expectedAnswer"], "1")
        for key in ("transcriptVersion", "sourceQuestionLabel", "answerState", "answerRegions", "visualEvidence"):
            self.assertEqual(result[key], item[key])
        self.assertFalse(result["recognitionNeedsConfirmation"])

    def test_empty_unknown_operand_and_continued_equality_do_not_get_solved_into_original_answer(self):
        for prompt in ("4 − □ = 3", "5 − 2 = 4 − □"):
            value, _ = self.parse([{**self.raw, "prompt": prompt, "type": "fill_blank"}])
            result = self.grade(value["items"][0])
            self.assertEqual(result["studentAnswer"], "□")
            self.assertIsNone(result["expectedAnswer"])
            self.assertEqual(result["status"], "unsupported")

    def test_computed_digit_contradicting_blank_state_is_never_an_original_grade(self):
        value, diagnostics = self.parse([{**self.raw, "studentAnswer": "1"}])
        item = value["items"][0]
        self.assertEqual(item["studentAnswer"], "1")  # Keep the received transcription for audit.
        self.assertIn("answer_state_conflict", diagnostics["issueCounts"])
        self.assertEqual(self.grade(item)["status"], "pending")
        self.assertEqual(self.grade({**self.raw, "studentAnswer": "1"})["status"], "pending")

    def test_partial_multi_slot_answer_retains_empty_box_and_requires_confirmation(self):
        value, _ = self.parse([{**self.raw, "prompt": "填写两个空：□和□", "type": "fill_blank",
            "answerState": "unclear", "studentAnswer": "1，□"}])
        item = value["items"][0]
        self.assertEqual(item["studentAnswer"], "1，□")
        self.assertTrue(item["recognitionNeedsConfirmation"])
        self.assertTrue(self.grade(item)["recognitionNeedsConfirmation"])

    def test_source_contract_missing_or_invalid_fields_preserves_untrusted_item(self):
        for field, invalid in (("sourceQuestionLabel", "a" * 81), ("answerState", "solved"),
                               ("answerRegions", None), ("visualEvidence", "a" * 501)):
            for missing in (False, True):
                raw = deepcopy(self.raw)
                if missing:
                    raw.pop(field)
                else:
                    raw[field] = invalid
                if field == "visualEvidence" and missing:
                    raw.update(type="geometry", answerState="drawing", studentAnswer="圈了左边的图")
                with self.subTest(field=field, missing=missing):
                    value, diagnostics = self.parse([raw])
                    self.assertTrue(value["items"][0]["recognitionNeedsConfirmation"])
                    self.assertGreater(diagnostics["confirmationRequiredItems"], 0)

    def test_strict_v3_does_not_accept_legacy_transcription_as_source_verified(self):
        raw = {key: value for key, value in self.raw.items() if key not in
               {"sourceQuestionLabel", "answerState", "answerRegions", "visualEvidence"}}
        raw["studentAnswer"] = "1"
        value, diagnostics = self.parse([raw], version="v2")
        self.assertIn("source_version_invalid", diagnostics["issueCounts"])
        self.assertEqual(self.grade(value["items"][0])["status"], "pending")

    def test_legacy_shape_remains_readable_without_v3_requirement(self):
        raw = {key: value for key, value in self.raw.items() if key not in
               {"sourceQuestionLabel", "answerState", "answerRegions", "visualEvidence"}}
        raw["studentAnswer"] = "2"
        value, diagnostics = self.parse([raw], strict=False, version="v2")
        self.assertNotIn("transcriptVersion", value["items"][0])
        self.assertEqual(diagnostics["issueCounts"], {})
        self.assertEqual(self.grade(value["items"][0])["status"], "incorrect")

    def test_original_picture_observation_survives_without_becoming_a_numeric_answer(self):
        raw = {**self.raw, "prompt": "按例子给星星涂色", "studentAnswer": "第二组前4个星形涂色",
            "type": "fill_blank", "answerState": "drawing",
            "visualEvidence": "第一组4个空心星形；第二组5个星形，前4个填色。"}
        value, diagnostics = self.parse([raw])
        result = self.grade(value["items"][0])
        self.assertEqual(diagnostics["issueCounts"], {})
        self.assertEqual(result["visualEvidence"], raw["visualEvidence"])
        self.assertEqual(result["answerState"], "drawing")
        self.assertIsNone(result["expectedAnswer"])

    def test_answer_regions_must_be_bounded_present_and_within_own_question(self):
        for positions in ([], [None], [{"x": .8, "y": .2, "width": .05, "height": .05}],
                          [self.raw["answerRegions"][0]] * 17):
            value, _ = self.parse([{**self.raw, "answerRegions": positions}])
            self.assertTrue(value["items"][0]["recognitionNeedsConfirmation"])
            self.assertEqual(self.grade(value["items"][0])["status"], "pending")

    def test_absent_original_region_blocks_automatic_grading_even_for_legacy_math(self):
        raw = {"prompt": "3+2", "studentAnswer": "4", "type": "arithmetic",
               "confidence": .99, "annotationAmbiguous": False, "region": None}
        result = self.grade(raw)
        self.assertEqual(result["status"], "pending")
        self.assertTrue(result["recognitionNeedsConfirmation"])
        # An explicit human source confirmation is a distinct, nonautomatic path.
        self.assertEqual(self.grade(raw, confirmed=True)["status"], "incorrect")

    def test_near_identical_answer_regions_flag_same_or_conflicting_transcriptions(self):
        written = {**self.raw, "answerState": "written", "studentAnswer": "2"}
        for answer, issue in (("2", "overlapping_duplicate"), ("1", "overlapping_conflict")):
            other = deepcopy(written)
            other["studentAnswer"] = answer
            other["answerRegions"][0]["x"] += .00001
            value, diagnostics = self.parse([written, other])
            self.assertEqual(diagnostics["issueCounts"], {issue: 2})
            self.assertEqual([self.grade(item)["status"] for item in value["items"]], ["pending", "pending"])

    def test_shared_large_stem_does_not_merge_distinct_answer_positions(self):
        first = {**self.raw, "answerState": "written", "studentAnswer": "2"}
        second = deepcopy(first)
        second["answerRegions"][0]["x"] = .3
        second["studentAnswer"] = "1"
        value, diagnostics = self.parse([first, second])
        self.assertEqual(diagnostics["issueCounts"], {})
        self.assertEqual([self.grade(item)["status"] for item in value["items"]], ["incorrect", "correct"])

    def test_explicit_parent_correction_updates_previous_blank_answer_state(self):
        value, _ = self.parse([self.raw])
        result = self.grade({**value["items"][0], "studentAnswer": "1"}, confirmed=True)
        self.assertEqual(result["answerState"], "written")
        self.assertEqual(result["status"], "correct")


if __name__ == "__main__":
    unittest.main()
