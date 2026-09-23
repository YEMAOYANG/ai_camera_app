"""Offline curriculum regressions: scope, real dependencies and immutable identity."""
import copy
import hashlib
import json
from pathlib import Path
import re
import string
import unittest

from content.build_progressive_curriculum import build
from content.progressive_curriculum import (
    CURRICULUM_VERSION, all_lessons, curriculum_identity, lesson_by_id,
    lessons_for, load_curriculum, prerequisite_closure, unit_by_id,
    validate_curriculum,
)


class ProgressiveCurriculumTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load_curriculum()
        cls.lessons = all_lessons()

    def test_all_187_documented_units_and_every_step_have_lesson_authority(self):
        root = Path(__file__).resolve().parents[2]
        expected = {}
        for name in ("primary-language-sequence-v1.md", "primary-math-sequence-v1.md"):
            for match in re.finditer(r"^\| ((?:ZH|EN|M)[1-6][AB]\d{2}) ([^|]+)\| ([^|]+)\|$", (root / "docs/curriculum" / name).read_text(), re.M):
                expected[match[1]] = len(match[3].split("→"))
        self.assertEqual(187, len(expected))
        self.assertEqual(set(expected), {unit["unitId"] for unit in self.payload["units"]})
        for unit in self.payload["units"]:
            self.assertEqual(set(range(1, expected[unit["unitId"]] + 1)), {lesson["sourceStepSequence"] for lesson in unit["lessons"]})
        self.assertGreater(len(self.lessons), 1000)
        for grade in range(1, 7):
            for subject in ("chinese", "math", "english"):
                rows = lessons_for(f"primary_{grade}", subject)
                self.assertEqual({"upper", "lower"}, {row["phase"] for row in rows})
                self.assertEqual(list(range(1, len(rows) + 1)), [row["sequence"] for row in rows])

    def test_alphabet_has_each_letter_and_distinct_case_name_sound_lessons(self):
        rows = [row for row in self.lessons if row["lessonId"].startswith("EN1A")]
        self.assertEqual(104, len(rows))
        for letter in string.ascii_uppercase:
            taught = [row for row in rows if row["constraints"]["introducedTokens"] == [letter]]
            self.assertEqual({1, 2, 3, 4}, {row["sourceStepSequence"] for row in taught})
        self.assertEqual(["A"], lesson_by_id("EN1A01.01")["constraints"]["allowedLetters"])
        self.assertEqual(set(string.ascii_uppercase), set(rows[-1]["constraints"]["allowedLetters"]))

    def test_pinyin_inventory_has_individual_targets_and_no_later_symbols_in_first_vowel(self):
        expected = set("a o e i u ü b p m f d t n l g k h j q x y w z c s zh ch sh r ai ei ui ao ou iu ie üe er an en in un ün ang eng ing ong zhi chi shi ri zi ci si yi wu yu ye yue yuan yin yun ying".split())
        rows = [row for row in self.lessons if row["lessonId"].startswith("ZH1A")]
        symbols = {token for row in rows for token in row["constraints"]["introducedTokens"]}
        self.assertTrue(expected <= symbols)
        first_a = next(row for row in rows if row["constraints"]["introducedTokens"] == ["a"])
        self.assertEqual(["a"], first_a["constraints"]["allowedPinyin"])
        self.assertNotIn("j", first_a["constraints"]["allowedPinyin"])
        for token in expected:
            self.assertTrue(any(row["constraints"]["introducedTokens"] == [token] for row in rows), token)

    def test_entry_math_is_small_and_number_recognition_does_not_precede_counting(self):
        rows = unit_by_id("M1A01")["lessons"]
        self.assertGreater(len(rows), 5)
        self.assertEqual((0, 1), (rows[0]["constraints"]["minimumNumber"], rows[0]["constraints"]["maximumNumber"]))
        for row in rows:
            self.assertLessEqual(row["constraints"]["maximumNumber"], 5)
            self.assertEqual([], row["constraints"]["allowedOperations"])
            self.assertEqual(row["sourceStepSequence"] >= 4, row["constraints"]["writtenNumberRecognitionRequired"])
            if not row["constraints"]["writtenNumberRecognitionRequired"]:
                self.assertEqual(["count_objects"], row["constraints"]["assessmentEvidenceKinds"])
        for n in range(1, 6):
            self.assertTrue(any(row["constraints"]["introducedTokens"] == [str(n)] and row["sourceStepSequence"] == 4 for row in rows))
        zeros = [row for row in unit_by_id("M1A02")["lessons"] if row["constraints"]["introducedTokens"] == ["0"]]
        self.assertEqual(1, len(zeros))

    def test_geometry_is_not_locked_behind_unrelated_arithmetic(self):
        self.assertEqual([], prerequisite_closure("M1A05.01"))
        self.assertEqual([], prerequisite_closure("M1B05.01"))
        advanced = prerequisite_closure("M3B05.04")
        self.assertTrue(any(lid.startswith("M2A04.") for lid in advanced), "area needs multiplication")
        self.assertTrue(any(lid.startswith("M2A05.") for lid in advanced), "area needs length measures")
        self.assertFalse(any(lid.startswith("M3B03.") for lid in advanced), "area does not require fractions")

    def test_grammar_is_opened_by_actual_lessons_not_by_grade_label(self):
        for row in lessons_for("primary_3", "english"):
            self.assertNotIn("simple_past", row["constraints"]["allowedGrammarCodes"])
            self.assertNotIn("past_irregular", row["constraints"]["allowedGrammarCodes"])
            self.assertIn("simple_past", row["constraints"]["excludedGrammarCodes"])
        past = lesson_by_id("EN5A03.01")
        self.assertIn("past_irregular", past["constraints"]["allowedGrammarCodes"])
        self.assertIn("simple_past", past["constraints"]["allowedGrammarCodes"])
        self.assertNotIn("future_will", past["constraints"]["allowedGrammarCodes"])
        future = lesson_by_id("EN5B01.02")
        self.assertIn("future_will", future["constraints"]["allowedGrammarCodes"])
        self.assertNotIn("future_going_to", future["constraints"]["allowedGrammarCodes"])
        for row in lessons_for("primary_6", "english"):
            self.assertTrue({"present_perfect", "passive_voice", "complex_clause"} <= set(row["constraints"]["excludedGrammarCodes"]))

    def test_observed_skills_are_not_automatically_scored_or_used_as_reading_proof(self):
        handwriting = lesson_by_id("ZH1B02.02")
        self.assertEqual("observed", handwriting["assessmentMode"])
        self.assertEqual([], handwriting["constraints"]["assessmentEvidenceKinds"])
        self.assertTrue(handwriting["assessmentCriteria"]["requiresObservedConfirmation"])
        self.assertNotIn("ZH1B02.02", prerequisite_closure("ZH1B03.01"))
        self.assertTrue(any(row["assessmentMode"] == "observed" for row in lessons_for("primary_6", "chinese")))

    def test_graph_rejects_dangling_cycles_cross_subjects_and_missing_phases(self):
        broken = copy.deepcopy(self.payload)
        broken["units"][0]["lessons"][0]["prerequisiteLessonIds"] = ["ZH1A01.99"]
        with self.assertRaisesRegex(ValueError, "dangling"):
            validate_curriculum(broken)
        for reference in ("ZH1A01.01", "ZH1A01.02", "EN1A01.01"):
            broken = copy.deepcopy(self.payload)
            broken["units"][0]["lessons"][0]["prerequisiteLessonIds"] = [reference]
            with self.assertRaisesRegex(ValueError, "cyclic|cross-subject|backwards"):
                validate_curriculum(broken)
        broken = copy.deepcopy(self.payload)
        broken["units"] = [unit for unit in broken["units"] if not(unit["gradeCode"] == "primary_6" and unit["subject"] == "english" and unit["phase"] == "lower")]
        with self.assertRaisesRegex(ValueError, "both learning phases"):
            validate_curriculum(broken)

    def test_public_values_are_detached_and_identity_reproduces_authority(self):
        lesson = lesson_by_id("M1A01.01")
        lesson["constraints"]["maximumNumber"] = 99999
        self.assertEqual(1, lesson_by_id("M1A01.01")["constraints"]["maximumNumber"])
        identity = curriculum_identity()
        digest = hashlib.sha256(json.dumps(self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, identity["datasetSha256"])
        self.assertEqual(digest, identity["identitySha256"])
        self.assertEqual(CURRICULUM_VERSION, identity["curriculumVersion"])
        self.assertEqual(self.payload, build())
        for call in (lambda: lesson_by_id("missing"), lambda: unit_by_id("M7A01"), lambda: lessons_for("primary_7"), lambda: lessons_for("primary_1", "science")):
            with self.assertRaises(ValueError): call()


if __name__ == "__main__":
    unittest.main()
