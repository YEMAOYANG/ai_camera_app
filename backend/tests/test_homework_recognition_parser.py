"""Returned transcription regressions: pure parsing, no DB, HTTP or paid AI."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from services.homework_math import check_item
from services.homework_recognition_parser import (
    PARSER_VERSION,
    RecognitionParseError,
    parse_recognition_response,
)


POLICY = json.loads((Path(__file__).parents[1] / "content/homework_analysis_policy.v1.json").read_text())


class HomeworkRecognitionParserTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "prompt": "3 + 2 =", "studentAnswer": "4", "type": "arithmetic",
            "confidence": 0.99, "annotationAmbiguous": False,
            "region": {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1},
        }

    def parse(self, items, **kwargs):
        return parse_recognition_response(
            json.dumps({"pageReadable": True, "items": items}), maximum_items=40, **kwargs
        )

    def grade(self, item, **kwargs):
        return check_item(item, grade="primary_1", subject="math", policy=POLICY, **kwargs)

    def reason(self, text, reason, maximum_items=40):
        with self.assertRaises(RecognitionParseError) as caught:
            parse_recognition_response(text, maximum_items=maximum_items)
        self.assertEqual(caught.exception.reason, reason)
        self.assertEqual(str(caught.exception), reason)
        self.assertNotIn("SECRET_PAPER", str(caught.exception))

    def test_valid_question_retains_original_answer_coordinate_and_assessment(self):
        value, diagnostics = self.parse([self.raw])
        item = value["items"][0]
        for key in self.raw:
            self.assertEqual(item[key], self.raw[key])
        self.assertFalse(item["recognitionNeedsConfirmation"])
        self.assertEqual(self.grade(item)["status"], "incorrect")
        self.assertEqual(diagnostics, {
            "parserVersion": PARSER_VERSION, "inputItems": 1, "normalizedItems": 1,
            "confirmationRequiredItems": 0, "numericAnswersNormalized": 0, "issueCounts": {},
        })

    def test_numeric_answers_are_normalized_without_float_precision_loss(self):
        text = '''{"pageReadable":true,"items":[
          {"prompt":"0.1+0.2","studentAnswer":0.300000000000000000000000000001,"type":"arithmetic","confidence":0.99,"annotationAmbiguous":false,"region":null},
          {"prompt":"3+2","studentAnswer":5,"type":"arithmetic","confidence":1,"annotationAmbiguous":false,"region":null},
          {"prompt":"3+2","studentAnswer":5.000,"type":"arithmetic","confidence":0.99,"annotationAmbiguous":false,"region":null}
        ]}'''
        value, diagnostics = parse_recognition_response(text, maximum_items=40)
        self.assertEqual([item["studentAnswer"] for item in value["items"]], [
            "0.300000000000000000000000000001", "5", "5.000",
        ])
        # Numeric normalization is independent of a reliable original location.
        self.assertEqual(self.grade(value["items"][0])["status"], "pending")
        self.assertEqual(self.grade(value["items"][1])["status"], "pending")
        self.assertEqual(diagnostics["numericAnswersNormalized"], 3)
        self.assertEqual(diagnostics["confirmationRequiredItems"], 0)

    def test_null_absent_bool_object_and_nonfinite_answers_never_become_blank_or_wrong(self):
        invalid_answers = (None, True, False, [], {}, float("nan"), float("inf"), "x" * 161)
        for answer in invalid_answers:
            with self.subTest(answer_type=type(answer).__name__):
                value, diagnostics = self.parse([{**self.raw, "studentAnswer": answer}])
                item = value["items"][0]
                self.assertTrue(item["recognitionNeedsConfirmation"])
                self.assertTrue(item["annotationAmbiguous"])
                result = self.grade(item)
                self.assertEqual(result["status"], "pending")
                self.assertTrue(result["recognitionNeedsConfirmation"])
                self.assertEqual(diagnostics["issueCounts"], {"answer_invalid": 1})
        missing = dict(self.raw)
        del missing["studentAnswer"]
        value, _ = self.parse([missing])
        self.assertEqual(self.grade(value["items"][0])["status"], "pending")

    def test_explicit_empty_string_is_the_only_blank_answer_in_this_contract(self):
        for answer in ("", "   "):
            value, diagnostics = self.parse([{**self.raw, "studentAnswer": answer}])
            item = value["items"][0]
            self.assertFalse(item["recognitionNeedsConfirmation"])
            self.assertEqual(self.grade(item)["status"], "blank")
            self.assertEqual(diagnostics["issueCounts"], {})

    def test_uncertain_empty_answer_is_pending_before_blank_but_explicit_confirmation_can_confirm_blank(self):
        uncertain = (
            {**self.raw, "studentAnswer": "", "confidence": 0.2},
            {**self.raw, "studentAnswer": "", "annotationAmbiguous": True},
            {**self.raw, "studentAnswer": "", "confidence": 0.2, "annotationAmbiguous": True},
        )
        for raw in uncertain:
            with self.subTest(confidence=raw["confidence"], ambiguous=raw["annotationAmbiguous"]):
                value, diagnostics = self.parse([raw])
                item = value["items"][0]
                # These are structurally valid provider fields, not a parser error.
                self.assertEqual(diagnostics["issueCounts"], {})
                self.assertFalse(item["recognitionNeedsConfirmation"])
                self.assertEqual(self.grade(item)["status"], "pending")
                self.assertEqual(self.grade(item, confirmed=True)["status"], "blank")
        # The marker also wins over blank until an explicit source confirmation.
        value, _ = self.parse([{**self.raw, "studentAnswer": None}])
        item = value["items"][0]
        self.assertEqual(self.grade(item)["status"], "pending")
        self.assertEqual(self.grade(item, confirmed=True)["status"], "blank")

    def test_bad_region_preserves_siblings_and_original_question_order(self):
        bad = {**self.raw, "region": {"x": 0.9, "y": 0.2, "width": 0.2, "height": 0.1}}
        original = [deepcopy(self.raw), bad, {**self.raw, "studentAnswer": "5", "region": {**self.raw["region"], "y": .5}}]
        value, diagnostics = self.parse(original)
        self.assertEqual(len(value["items"]), 3)
        self.assertEqual([self.grade(item)["status"] for item in value["items"]], [
            "incorrect", "pending", "correct",
        ])
        self.assertEqual(value["items"][1]["prompt"], self.raw["prompt"])
        self.assertEqual(value["items"][1]["studentAnswer"], "4")
        self.assertIsNone(value["items"][1]["region"])
        self.assertEqual(diagnostics["confirmationRequiredItems"], 1)
        self.assertEqual(diagnostics["issueCounts"], {"region_invalid": 1})
        self.assertEqual(original[1]["region"], bad["region"])

    def test_invalid_region_shapes_numbers_and_dimensions_are_isolated(self):
        regions = (
            [], "0.1,0.2", {"x": 0.1},
            {"x": True, "y": 0, "width": 0.1, "height": 0.1},
            {"x": -0.1, "y": 0, "width": 0.1, "height": 0.1},
            {"x": 0, "y": 0, "width": 0, "height": 0.1},
            {"x": 0, "y": float("nan"), "width": 0.1, "height": 0.1},
            {"x": 0.1, "y": 0.2, "width": 0.7, "height": 0.1, "extra": "SECRET_PAPER"},
        )
        for region in regions:
            with self.subTest(region_type=type(region).__name__):
                value, diagnostics = self.parse([{**self.raw, "region": region}, self.raw])
                self.assertIsNone(value["items"][0]["region"])
                self.assertEqual(self.grade(value["items"][0])["status"], "pending")
                self.assertEqual(self.grade(value["items"][1])["status"], "incorrect")
                self.assertEqual(diagnostics["issueCounts"], {"region_invalid": 1})

    def test_unknown_coordinate_is_distinct_from_malformed_coordinate(self):
        for changes in ({"region": None}, {}):
            raw = dict(self.raw)
            del raw["region"]
            raw.update(changes)
            value, diagnostics = self.parse([raw])
            self.assertIsNone(value["items"][0]["region"])
            self.assertFalse(value["items"][0]["recognitionNeedsConfirmation"])
            self.assertEqual(diagnostics["issueCounts"], {})

    def test_exact_overlapping_duplicate_is_preserved_but_never_scores_two_mistakes(self):
        sibling = {**self.raw, "region": {"x": 0.1, "y": 0.5, "width": 0.7, "height": 0.1}}
        original = [deepcopy(self.raw), deepcopy(self.raw), sibling]
        value, diagnostics = self.parse(original)
        self.assertEqual(len(value["items"]), 3)
        self.assertEqual([self.grade(item)["status"] for item in value["items"]], [
            "pending", "pending", "incorrect",
        ])
        self.assertTrue(all(item["recognitionNeedsConfirmation"] for item in value["items"][:2]))
        self.assertTrue(all(item["annotationAmbiguous"] for item in value["items"][:2]))
        self.assertEqual(diagnostics["confirmationRequiredItems"], 2)
        self.assertEqual(diagnostics["issueCounts"], {"overlapping_duplicate": 2})
        self.assertFalse(original[0]["annotationAmbiguous"])

    def test_same_arithmetic_at_distinct_or_unknown_positions_is_not_silently_deduplicated(self):
        for second_region in ({"x": 0.1, "y": 0.5, "width": 0.7, "height": 0.1}, None):
            first = {**self.raw, "region": None if second_region is None else self.raw["region"]}
            value, diagnostics = self.parse([first, {**self.raw, "region": second_region}])
            self.assertEqual(len(value["items"]), 2)
            self.assertEqual([self.grade(item)["status"] for item in value["items"]],
                             ["pending", "pending"] if second_region is None else ["incorrect", "incorrect"])
            self.assertEqual(diagnostics["confirmationRequiredItems"], 0)
            self.assertEqual(diagnostics["issueCounts"], {})

    def test_duplicate_diagnostics_count_each_untrusted_item_only_once(self):
        value, diagnostics = self.parse([{**self.raw, "confidence": None}, self.raw])
        self.assertEqual(diagnostics["confirmationRequiredItems"], 2)
        self.assertEqual(diagnostics["issueCounts"], {"confidence_invalid": 1, "overlapping_duplicate": 2})
        self.assertEqual([self.grade(item)["status"] for item in value["items"]], ["pending", "pending"])

    def test_missing_answer_does_not_make_a_separate_explicit_blank_a_duplicate(self):
        value, diagnostics = self.parse([{**self.raw, "studentAnswer": None}, {**self.raw, "studentAnswer": ""}])
        self.assertEqual(diagnostics["confirmationRequiredItems"], 1)
        self.assertEqual(diagnostics["issueCounts"], {"answer_invalid": 1})
        self.assertEqual([self.grade(item)["status"] for item in value["items"]], ["pending", "blank"])

    def test_same_position_with_different_source_answer_is_untrusted_not_two_opposing_grades(self):
        value, diagnostics = self.parse([self.raw, {**self.raw, "studentAnswer": "5"}])
        self.assertEqual(diagnostics["issueCounts"], {"overlapping_conflict": 2})
        self.assertEqual([self.grade(item)["status"] for item in value["items"]], ["pending", "pending"])

    def test_invalid_confidence_and_annotation_do_not_confirm_a_wrong_answer(self):
        changes = (
            {"confidence": True}, {"confidence": "0.99"}, {"confidence": None},
            {"confidence": -1}, {"confidence": 1.1}, {"confidence": float("inf")},
            {"annotationAmbiguous": "false"}, {"annotationAmbiguous": None},
        )
        for change in changes:
            with self.subTest(fields=list(change)):
                value, diagnostics = self.parse([{**self.raw, **change}])
                self.assertTrue(value["items"][0]["recognitionNeedsConfirmation"])
                self.assertEqual(self.grade(value["items"][0])["status"], "pending")
                self.assertEqual(diagnostics["confirmationRequiredItems"], 1)
        # A legitimate model uncertainty also remains pending, with no fake schema error.
        value, diagnostics = self.parse([{**self.raw, "confidence": 0.2}])
        self.assertEqual(self.grade(value["items"][0])["status"], "pending")
        self.assertEqual(diagnostics["issueCounts"], {})

    def test_malformed_items_and_prompts_preserve_ordinals_without_grading(self):
        malformed = (
            None, "SECRET_PAPER", 4, [],
            {**self.raw, "prompt": ""}, {**self.raw, "prompt": ["SECRET_PAPER"]},
            {**self.raw, "prompt": "3+2" * 400}, {**self.raw, "type": ["arithmetic"]},
        )
        for raw in malformed:
            with self.subTest(item_type=type(raw).__name__):
                if isinstance(raw, dict):
                    raw = {**raw, "region": {"x": 0.1, "y": 0.4, "width": 0.7, "height": 0.1}}
                value, diagnostics = self.parse([self.raw, raw, {**self.raw, "studentAnswer": "5", "region": {**self.raw["region"], "y": .5}}])
                self.assertEqual(len(value["items"]), 3)
                self.assertTrue(value["items"][1]["recognitionNeedsConfirmation"])
                self.assertIn(self.grade(value["items"][1])["status"], {"unsupported", "pending"})
                self.assertEqual(self.grade(value["items"][0])["status"], "incorrect")
                self.assertEqual(self.grade(value["items"][2])["status"], "correct")
                self.assertEqual(diagnostics["confirmationRequiredItems"], 1)
                self.assertNotIn("SECRET_PAPER", json.dumps(diagnostics))

    def test_readable_unsupported_question_is_retained_without_arithmetic_guessing(self):
        raw = {**self.raw, "prompt": "图形题", "type": "unsupported", "studentAnswer": None}
        value, diagnostics = self.parse([raw, self.raw])
        self.assertEqual(value["items"][0]["type"], "unsupported")
        self.assertEqual(self.grade(value["items"][0])["status"], "unsupported")
        self.assertEqual(self.grade(value["items"][1])["status"], "incorrect")
        self.assertEqual(diagnostics["issueCounts"], {"answer_invalid": 1})

    def test_over_limit_is_explicit_and_never_silently_drops_the_last_question(self):
        value, diagnostics = self.parse([self.raw] * 40)
        self.assertEqual(len(value["items"]), 40)
        self.assertEqual(diagnostics["inputItems"], 40)
        self.reason(json.dumps({"pageReadable": True, "items": [self.raw] * 41}), "over_limit")
        self.reason(json.dumps({"pageReadable": True, "items": [self.raw] * 2}), "over_limit", maximum_items=1)

    def test_invalid_envelopes_have_fixed_reasons_without_source_text(self):
        invalid_json = ("SECRET_PAPER", "", '{"pageReadable":true,"items":[',
                        '{"pageReadable":true,"items":[],"items":["SECRET_PAPER"]}')
        for text in invalid_json:
            self.reason(text, "invalid_json")
        for value in (None, [], {"pageReadable": "true", "items": []},
                      {"pageReadable": True, "items": None}, {"items": []}):
            self.reason(json.dumps(value), "invalid_schema")

    def test_unreadable_page_does_not_assess_contradictory_items(self):
        text = json.dumps({"pageReadable": False, "items": [self.raw]})
        value, diagnostics = parse_recognition_response(text, maximum_items=40)
        self.assertEqual(value, {"pageReadable": False, "items": []})
        self.assertEqual(diagnostics["inputItems"], 1)
        self.assertEqual(diagnostics["normalizedItems"], 0)
        self.assertEqual(diagnostics["issueCounts"], {"unreadable_items_present": 1})

    def test_confirmation_marker_survives_storage_roundtrip_until_explicit_confirmation(self):
        value, _ = self.parse([{**self.raw, "studentAnswer": None}])
        result = self.grade(value["items"][0])
        restored = json.loads(json.dumps(result))
        self.assertEqual(self.grade(restored)["status"], "pending")
        self.assertTrue(self.grade(restored)["recognitionNeedsConfirmation"])
        # Explicitly confirmed source edits, unlike parser cleanup, can replace an answer.
        confirmed = self.grade({**restored, "studentAnswer": "5"}, confirmed=True)
        self.assertEqual(confirmed["status"], "correct")
        self.assertFalse(confirmed["recognitionNeedsConfirmation"])


if __name__ == "__main__":
    unittest.main()
