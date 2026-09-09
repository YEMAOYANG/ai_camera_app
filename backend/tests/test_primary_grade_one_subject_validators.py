import copy
import hashlib
import json
import unittest
from unittest.mock import patch

import content.primary_skill_boundaries as primary_skill_boundaries_module

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_ONE_CONTENT_DATASET_SHA256,
    PRIMARY_ONE_CANARY_MANIFEST_VERSION,
    SUBJECT_LANGUAGE_POLICY_VERSION,
    boundaries_for,
    primary_one_content_contract,
    validate_primary_one_content_contract,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
    PrimaryOneHostGateControlError,
)
from tests.test_learning_generated_course_validator import (
    _FORMAL_SKILLS,
    _formal_evidence,
    formal_host_fixture,
)


EXPECTED_BOUNDARIES = (
    (1, 1, "chinese", "pinyin_syllables"),
    (1, 2, "chinese", "pinyin_initials_syllables"),
    (1, 3, "chinese", "characters_words"),
    (1, 4, "chinese", "simple_sentences"),
    (2, 1, "math", "number_sense_20"),
    (2, 2, "math", "addition_subtraction_20"),
    (2, 3, "math", "shapes_position"),
    (3, 1, "english", "letters_sounds"),
    (3, 2, "english", "greetings"),
    (3, 3, "english", "numbers_colors"),
)
EXPECTED_CANARIES = (
    (1, 1, 1, "chinese", "pinyin_syllables"),
    (2, 1, 1, "math", "number_sense_20"),
    (3, 1, 1, "english", "letters_sounds"),
)
EXPECTED_INVENTORY_KEYS = {
    "pinyin_syllables": [
        "chinese.pinyin_vowels_aoe.v1",
        "chinese.guidance_characters.v1",
    ],
    "pinyin_initials_syllables": [
        "chinese.initials.v1",
        "chinese.pinyin_vowels_aoe.v1",
        "chinese.simple_syllables.v1",
    ],
    "characters_words": ["chinese.common_characters_radicals_words.v1"],
    "simple_sentences": ["chinese.simple_sentence_punctuation.v1"],
    "number_sense_20": ["math.number_sense_20_ranges.v1"],
    "addition_subtraction_20": ["math.addition_subtraction_20_ast.v1"],
    "shapes_position": ["math.shapes_position_relations.v1"],
    "letters_sounds": ["english.letter_case_initial_sound.v1"],
    "greetings": ["english.greeting_patterns.v1"],
    "numbers_colors": ["english.numbers_1_20_colors.v1"],
}
EXPECTED_INVENTORY_KINDS = {
    "chinese.pinyin_vowels_aoe.v1": "pinyin_vowel_rules",
    "chinese.guidance_characters.v1": "character_allowlist",
    "chinese.initials.v1": "pinyin_initial_rules",
    "chinese.simple_syllables.v1": "pinyin_syllable_rules",
    "chinese.common_characters_radicals_words.v1": (
        "character_radical_word_relation_rules"
    ),
    "chinese.simple_sentence_punctuation.v1": "sentence_language_rules",
    "math.number_sense_20_ranges.v1": "number_sense_rules",
    "math.addition_subtraction_20_ast.v1": "arithmetic_ast_rules",
    "math.shapes_position_relations.v1": "shape_position_rules",
    "english.letter_case_initial_sound.v1": "letter_initial_sound_rules",
    "english.greeting_patterns.v1": "greeting_phrase_rules",
    "english.numbers_1_20_colors.v1": "number_color_rules",
}


def _rehash_contract(contract):
    payload = copy.deepcopy(contract)
    payload.pop("datasetSha256", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    contract["datasetSha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


class PrimaryGradeOneContentAuthorityTest(unittest.TestCase):
    def test_all_ten_boundaries_have_typed_versioned_deterministic_rules(self):
        inventories = primary_one_content_contract()["inventories"]
        self.assertEqual(set(inventories), set(EXPECTED_INVENTORY_KINDS))
        self.assertTrue(
            all(isinstance(inventory, dict) for inventory in inventories.values())
        )
        for key, inventory in inventories.items():
            with self.subTest(inventory=key):
                self.assertEqual(
                    inventory["kind"], EXPECTED_INVENTORY_KINDS[key]
                )
                self.assertEqual(inventory["schemaVersion"], key)
                self.assertIsInstance(inventory["rules"], dict)
                self.assertTrue(inventory["rules"])

        letter_rules = inventories[
            "english.letter_case_initial_sound.v1"
        ]["rules"]
        letters = letter_rules["letters"]
        self.assertEqual(len(letters), 26)
        self.assertEqual(
            [(item["uppercase"], item["lowercase"]) for item in letters],
            [(chr(65 + index), chr(97 + index)) for index in range(26)],
        )
        self.assertTrue(
            all(item["initialSoundWords"] for item in letters)
        )

        character_rules = inventories[
            "chinese.common_characters_radicals_words.v1"
        ]["rules"]
        self.assertGreaterEqual(len(character_rules["characters"]), 12)
        self.assertGreaterEqual(len(character_rules["radicals"]), 4)
        self.assertGreaterEqual(len(character_rules["wordRelations"]), 6)

        sentence_rules = inventories[
            "chinese.simple_sentence_punctuation.v1"
        ]["rules"]
        self.assertTrue(sentence_rules["sentencePatterns"])
        self.assertTrue(sentence_rules["wordOrderRules"])
        self.assertEqual(sentence_rules["terminalPunctuation"], ["。", "？"])
        self.assertEqual(
            sentence_rules["predicateGrammarVersion"],
            "mira.learning.primary-1-simple-sentence-predicate-grammar.v2",
        )
        self.assertEqual(sentence_rules["aspectMarkers"], ["了", "着", "过"])
        self.assertIn("工作", sentence_rules["intransitivePredicates"])
        self.assertIn("叫", sentence_rules["intransitivePredicates"])
        self.assertIn("跑步", sentence_rules["intransitivePredicates"])
        self.assertTrue(
            all(len(item) >= 2 for item in sentence_rules["actionPhrases"])
        )
        self.assertEqual(sentence_rules["identityMarkers"], ["是"])
        self.assertTrue(sentence_rules["descriptionMarkers"])
        self.assertEqual(
            sentence_rules["markerBearingSubjectNouns"],
            ["太空人", "真菌", "过山车", "太太", "老太太"],
        )
        self.assertEqual(
            sentence_rules["identityComplements"],
            [
                "老师",
                "学生",
                "同学",
                "朋友",
                "医生",
                "工人",
                "农民",
                "警察",
                "爸爸",
                "妈妈",
                "哥哥",
                "姐姐",
                "弟弟",
                "妹妹",
                "孩子",
                "太空人",
            ],
        )
        self.assertEqual(
            [item["shape"] for item in sentence_rules["subjectPredicateShapes"]],
            [
                ["subject", "predicate"],
                ["subject", "predicate"],
                ["subject", "predicate"],
                ["subject", "predicate", "complement"],
                ["subject", "predicate", "complement"],
            ],
        )

        shape_rules = inventories["math.shapes_position_relations.v1"][
            "rules"
        ]
        self.assertIs(shape_rules["rectangleSquareRule"]["squareIsRectangle"], True)
        self.assertEqual(
            shape_rules["rectangleSquareRule"]["requiredDiscriminators"],
            ["四条边不全相等", "相邻边长度不同", "长和宽不相等"],
        )

    def test_contract_has_exact_subject_boundaries_languages_and_canaries(self):
        contract = primary_one_content_contract()
        self.assertEqual(
            contract["schemaVersion"], CONTENT_VALIDATION_CONTRACT_VERSION
        )
        self.assertEqual(
            CONTENT_VALIDATION_CONTRACT_VERSION,
            "mira.learning.primary-1-content-validation.v1",
        )
        self.assertEqual(
            contract["subjectLanguagePolicyVersion"],
            SUBJECT_LANGUAGE_POLICY_VERSION,
        )
        self.assertEqual(
            contract["canaryManifest"]["version"],
            PRIMARY_ONE_CANARY_MANIFEST_VERSION,
        )
        self.assertEqual(len(contract["datasetSha256"]), 64)
        self.assertEqual(
            contract["datasetSha256"],
            PRIMARY_ONE_CONTENT_DATASET_SHA256,
        )

        actual_boundaries = []
        languages = {}
        for subject in contract["subjects"]:
            languages[subject["subject"]] = (
                subject["instructionLanguageCode"],
                subject["targetLanguageCode"],
            )
            actual_boundaries.extend(
                (
                    subject["subjectOrdinal"],
                    boundary["boundaryOrdinal"],
                    subject["subject"],
                    boundary["skillId"],
                )
                for boundary in subject["boundaries"]
            )
        self.assertEqual(tuple(actual_boundaries), EXPECTED_BOUNDARIES)
        self.assertEqual(
            languages,
            {
                "chinese": ("zh-CN", "zh-CN"),
                "math": ("zh-CN", "zh-CN"),
                "english": ("zh-CN", "en-US"),
            },
        )
        self.assertEqual(
            tuple(
                (
                    target["subjectOrdinal"],
                    target["boundaryOrdinal"],
                    target["variantOrdinal"],
                    target["subject"],
                    target["skillId"],
                )
                for target in contract["canaryManifest"]["targets"]
            ),
            EXPECTED_CANARIES,
        )

    def test_contract_loader_returns_an_independent_validated_copy(self):
        first = primary_one_content_contract()
        first["subjects"][0]["boundaries"][0]["skillId"] = "mutated"
        second = primary_one_content_contract()
        self.assertEqual(
            second["subjects"][0]["boundaries"][0]["skillId"],
            "pinyin_syllables",
        )

    def test_ambiguous_english_language_field_is_rejected(self):
        contract = primary_one_content_contract()
        english = next(
            item for item in contract["subjects"] if item["subject"] == "english"
        )
        english["language"] = "zh-CN"
        with self.assertRaisesRegex(ValueError, "unsupported subject fields"):
            validate_primary_one_content_contract(contract)

    def test_missing_prerequisite_inventory_is_rejected(self):
        contract = primary_one_content_contract()
        del contract["prerequisiteInventory"]
        with self.assertRaisesRegex(ValueError, "prerequisiteInventory"):
            validate_primary_one_content_contract(contract)

    def test_embedded_hash_must_match_actual_canonical_dataset(self):
        contract = primary_one_content_contract()
        contract["datasetSha256"] = "0" * 64
        with self.assertRaisesRegex(
            ValueError, "content validation dataset hash mismatch"
        ):
            validate_primary_one_content_contract(contract)

    def test_each_of_ten_boundaries_rejects_invalid_authority_mutation(self):
        pristine = primary_one_content_contract()
        for subject_index, subject in enumerate(pristine["subjects"]):
            for boundary_index, boundary in enumerate(subject["boundaries"]):
                mutated = copy.deepcopy(pristine)
                mutated_boundary = mutated["subjects"][subject_index]["boundaries"][
                    boundary_index
                ]
                mutated_boundary["boundaryOrdinal"] = 99
                with self.subTest(skill_id=boundary["skillId"]):
                    with self.assertRaisesRegex(
                        ValueError, "boundary ordinal mismatch"
                    ):
                        validate_primary_one_content_contract(mutated)

    def test_each_boundary_rejects_a_rehashed_wrong_inventory_binding(self):
        pristine = primary_one_content_contract()
        wrong_key = "math.number_sense_20_ranges.v1"
        for subject_index, subject in enumerate(pristine["subjects"]):
            for boundary_index, boundary in enumerate(subject["boundaries"]):
                mutated = copy.deepcopy(pristine)
                mutated_boundary = mutated["subjects"][subject_index]["boundaries"][
                    boundary_index
                ]
                replacement = (
                    "english.greeting_patterns.v1"
                    if wrong_key in EXPECTED_INVENTORY_KEYS[boundary["skillId"]]
                    else wrong_key
                )
                mutated_boundary["validationInventoryKeys"] = [replacement]
                _rehash_contract(mutated)
                with self.subTest(skill_id=boundary["skillId"]):
                    with self.assertRaisesRegex(
                        ValueError, "pinned dataset hash mismatch"
                    ):
                        validate_primary_one_content_contract(mutated)

    def test_rehashed_semantic_mutations_fail_closed_for_all_ten_boundaries(self):
        semantic_mutations = (
            (
                "pinyin_syllables_vowel",
                ("chinese.pinyin_vowels_aoe.v1", "symbols", 0, "soundCue"),
                "错音",
            ),
            (
                "pinyin_syllables_guidance",
                ("chinese.guidance_characters.v1", "characters", 0),
                "错",
            ),
            (
                "pinyin_initials_syllables_initial",
                ("chinese.initials.v1", "initials", 0),
                "v",
            ),
            (
                "pinyin_initials_syllables_syllable",
                ("chinese.simple_syllables.v1", "syllables", 0),
                "xyz",
            ),
            (
                "characters_words",
                (
                    "chinese.common_characters_radicals_words.v1",
                    "characters",
                    0,
                    "reading",
                ),
                "cuò",
            ),
            (
                "simple_sentences",
                (
                    "chinese.simple_sentence_punctuation.v1",
                    "sentencePatterns",
                    0,
                ),
                {"bad": True},
            ),
            (
                "number_sense_20",
                ("math.number_sense_20_ranges.v1", "placeValue", "tensMaximum"),
                99,
            ),
            (
                "addition_subtraction_20",
                ("math.addition_subtraction_20_ast.v1", "resultRange", "maximum"),
                99,
            ),
            (
                "shapes_position",
                ("math.shapes_position_relations.v1", "shapes", 2, "properties"),
                ["三条边"],
            ),
            (
                "letters_sounds",
                (
                    "english.letter_case_initial_sound.v1",
                    "letters",
                    0,
                    "initialSoundWords",
                ),
                ["banana"],
            ),
            (
                "greetings",
                ("english.greeting_patterns.v1", "phrases", 0, "canonical"),
                "Goodbye.",
            ),
            (
                "numbers_colors",
                ("english.numbers_1_20_colors.v1", "colors"),
                ["red"],
            ),
        )
        for boundary, path, invalid_value in semantic_mutations:
            contract = primary_one_content_contract()
            inventory_key, *rule_path = path
            target = contract["inventories"][inventory_key]["rules"]
            for segment in rule_path[:-1]:
                target = target[segment]
            target[rule_path[-1]] = invalid_value
            _rehash_contract(contract)
            with self.subTest(boundary=boundary, inventory=inventory_key):
                with self.assertRaisesRegex(
                    ValueError, "pinned dataset hash mismatch"
                ):
                    validate_primary_one_content_contract(contract)

    def test_rehashed_predicate_grammar_mutation_and_deletion_hit_external_pin(self):
        mutation_names = ("replace_predicate", "delete_inventory")
        for mutation_name in mutation_names:
            contract = primary_one_content_contract()
            rules = contract["inventories"][
                "chinese.simple_sentence_punctuation.v1"
            ]["rules"]
            if mutation_name == "replace_predicate":
                rules["intransitivePredicates"][0] = "篡改"
            else:
                del rules["actionPhrases"]
            _rehash_contract(contract)
            with self.subTest(mutation=mutation_name):
                with self.assertRaisesRegex(
                    ValueError, "pinned dataset hash mismatch"
                ):
                    validate_primary_one_content_contract(contract)

    def test_sentence_word_boundary_inventories_reject_shape_and_content_mutations(self):
        mutations = (
            (
                "missing_marker_subjects",
                lambda rules: rules.pop("markerBearingSubjectNouns"),
                "fields mismatch",
            ),
            (
                "extra_marker_subjects",
                lambda rules: rules.__setitem__("subjectAliases", ["妈妈"]),
                "fields mismatch",
            ),
            (
                "duplicate_marker_subject",
                lambda rules: rules["markerBearingSubjectNouns"].append("太太"),
                "unique non-empty strings",
            ),
            (
                "empty_marker_subjects",
                lambda rules: rules.__setitem__("markerBearingSubjectNouns", []),
                "unique non-empty strings",
            ),
            (
                "non_han_marker_subject",
                lambda rules: rules["markerBearingSubjectNouns"].__setitem__(0, "AI"),
                "bounded Han text",
            ),
            (
                "missing_identity_complements",
                lambda rules: rules.pop("identityComplements"),
                "fields mismatch",
            ),
            (
                "duplicate_identity_complement",
                lambda rules: rules["identityComplements"].append("老师"),
                "unique non-empty strings",
            ),
            (
                "empty_identity_complements",
                lambda rules: rules.__setitem__("identityComplements", []),
                "unique non-empty strings",
            ),
            (
                "non_han_identity_complement",
                lambda rules: rules["identityComplements"].__setitem__(0, "teacher"),
                "bounded Han text",
            ),
        )
        for mutation_name, mutate, message in mutations:
            contract = primary_one_content_contract()
            rules = contract["inventories"][
                "chinese.simple_sentence_punctuation.v1"
            ]["rules"]
            mutate(rules)
            _rehash_contract(contract)
            with self.subTest(mutation=mutation_name), patch.object(
                primary_skill_boundaries_module,
                "PRIMARY_ONE_CONTENT_DATASET_SHA256",
                contract["datasetSha256"],
            ):
                with self.assertRaisesRegex(ValueError, message):
                    validate_primary_one_content_contract(contract)

    def test_rehashed_word_boundary_semantic_mutations_hit_external_pin(self):
        for inventory_name, replacement in (
            ("markerBearingSubjectNouns", "太空员"),
            ("identityComplements", "校长"),
        ):
            contract = primary_one_content_contract()
            values = contract["inventories"][
                "chinese.simple_sentence_punctuation.v1"
            ]["rules"][inventory_name]
            values[0] = replacement
            _rehash_contract(contract)
            with self.subTest(inventory=inventory_name):
                with self.assertRaisesRegex(ValueError, "pinned dataset hash mismatch"):
                    validate_primary_one_content_contract(contract)

    def test_simple_sentence_boundary_projects_the_sealed_predicate_scope(self):
        rules = primary_one_content_contract()["inventories"][
            "chinese.simple_sentence_punctuation.v1"
        ]["rules"]
        boundary = next(
            item
            for item in boundaries_for("primary_1", "chinese")
            if item.skill_id == "simple_sentences"
        )
        boundary_text = "\n".join(
            (*boundary.learning_objectives, *boundary.allowed_content)
        )
        self.assertIn(rules["predicateGrammarVersion"], boundary_text)
        for inventory_name in (
            "intransitivePredicates",
            "actionPhrases",
            "statePredicates",
            "identityMarkers",
            "descriptionMarkers",
            "markerBearingSubjectNouns",
            "identityComplements",
        ):
            with self.subTest(inventory=inventory_name):
                for token in rules[inventory_name]:
                    self.assertIn(token, boundary_text)

    def test_all_ordinal_authority_fields_reject_non_integer_types(self):
        invalid_ordinals = (True, 1.0, "1", None)
        mutation_paths = (
            ("subjectOrdinal", ("subjects", 0, "subjectOrdinal")),
            (
                "boundaryOrdinal",
                ("subjects", 0, "boundaries", 0, "boundaryOrdinal"),
            ),
            (
                "canarySubjectOrdinal",
                ("canaryManifest", "targets", 0, "subjectOrdinal"),
            ),
            (
                "canaryBoundaryOrdinal",
                ("canaryManifest", "targets", 0, "boundaryOrdinal"),
            ),
            (
                "variantOrdinal",
                ("canaryManifest", "targets", 0, "variantOrdinal"),
            ),
        )
        for field, path in mutation_paths:
            for invalid in invalid_ordinals:
                contract = primary_one_content_contract()
                target = contract
                for segment in path[:-1]:
                    target = target[segment]
                target[path[-1]] = invalid
                _rehash_contract(contract)
                with self.subTest(field=field, invalid=repr(invalid)):
                    with self.assertRaisesRegex(ValueError, "must be an integer"):
                        validate_primary_one_content_contract(contract)


class PrimaryGradeOnePreparationManifestTest(unittest.TestCase):
    def test_target_has_exact_boundary_and_variant_ordinals(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(target["schemaVersion"], "mira.learning.preparation-target.v2")
        expected = tuple(
            (*boundary, variant_ordinal)
            for boundary in EXPECTED_BOUNDARIES
            for variant_ordinal in (1, 2, 3)
        )
        actual = tuple(
            (
                item["subjectOrdinal"],
                item["boundaryOrdinal"],
                item["subject"],
                item["skillId"],
                item["variantOrdinal"],
            )
            for item in target["courseTargets"]
        )
        self.assertEqual(actual, expected)

    def test_target_uses_unambiguous_subject_languages_and_exact_canaries(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(
            target["subjectLanguagePolicies"],
            {
                "chinese": {
                    "subjectOrdinal": 1,
                    "instructionLanguageCode": "zh-CN",
                    "targetLanguageCode": "zh-CN",
                },
                "math": {
                    "subjectOrdinal": 2,
                    "instructionLanguageCode": "zh-CN",
                    "targetLanguageCode": "zh-CN",
                },
                "english": {
                    "subjectOrdinal": 3,
                    "instructionLanguageCode": "zh-CN",
                    "targetLanguageCode": "en-US",
                },
            },
        )
        self.assertNotIn("language", target["subjectLanguagePolicies"]["english"])
        self.assertEqual(
            tuple(
                (
                    item["subjectOrdinal"],
                    item["boundaryOrdinal"],
                    item["variantOrdinal"],
                    item["subject"],
                    item["skillId"],
                )
                for item in target["canaryManifest"]["targets"]
            ),
            EXPECTED_CANARIES,
        )

    def test_content_dataset_hash_participates_in_target_fingerprint(self):
        target = build_preparation_target("primary_1")
        changed = copy.deepcopy(target)
        changed["contentValidationDatasetSha256"] = "0" * 64
        self.assertNotEqual(
            preparation_target_fingerprint(target),
            preparation_target_fingerprint(changed),
        )


class PrimaryOneTenBoundaryHostValidationTest(unittest.TestCase):
    def setUp(self):
        self.validator = LearningGeneratedCourseValidator()

    def _refresh(self, course, target, boundary, identity):
        evidence, refreshed_identity = _formal_evidence(
            course,
            target,
            boundary,
            identity.generation_request_id,
        )
        self.assertEqual(refreshed_identity, identity)
        return evidence

    def _host(self, course, target, boundary, identity):
        return self.validator.validate_primary_one_host_gate(
            self._refresh(course, target, boundary, identity),
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )

    @staticmethod
    def _first_choice(course):
        return next(
            question
            for question in course["content"]["questions"][1:]
            if question["type"] == "single_choice"
        )

    def test_number_sequence_detection_accepts_host_compiled_adjacent_stem(self):
        self.assertTrue(
            self.validator.catalog_validator._is_number_sequence_question(
                {"prompt": "数字19的后一个数是几?"}
            )
        )
        self.assertTrue(
            self.validator.catalog_validator._is_number_sequence_question(
                {"prompt": "数字1的前一个数是几?"}
            )
        )
        self.assertFalse(
            self.validator.catalog_validator._is_number_sequence_question(
                {"prompt": "小象站在19号彩旗后面。"}
            )
        )
        self.assertFalse(
            self.validator.catalog_validator._is_number_sequence_question(
                {
                    "prompt": (
                        "小浣熊的阳光实验室里，贴纸墙上贴着数字卡片。"
                        "18和20中间还缺一张贴纸，应该贴哪个数字？"
                    )
                }
            )
        )
        for prompt in (
            "18和19中间还缺一个数，应该填哪个数字？",
            "18和21中间还缺一个数，应该填哪个数字？",
            "19和21中间还缺一个数，应该填哪个数字？",
        ):
            self.assertFalse(
                self.validator.catalog_validator._is_number_sequence_question(
                    {"prompt": prompt}
                )
            )

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        question = course["content"]["questions"][1]
        question["prompt"] = "数字19的后一个数是几?"
        question["hint"] = "从19往后数一个。"
        question["explanation"] = "19的后一个数是20。"
        for choice, label in zip(question["choices"], ("18", "19", "20")):
            choice["label"] = label

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )
        result = self._host(course, target, boundary, identity)
        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_number_sequence_canonical_adjacent_semantics_require_the_unique_computed_choice(self):
        course, target, boundary, _evidence, _identity = formal_host_fixture(
            "number_sense_20"
        )
        question = course["content"]["questions"][1]
        question.update(
            {
                "prompt": "数字按0到20的顺序排列，数字18的后一个数是几？",
                "hint": "从18往后数一个。",
                "explanation": "18的后一个数是19。",
                "answer": "C",
                "choices": [
                    {"id": "A", "label": "17"},
                    {"id": "B", "label": "18"},
                    {"id": "C", "label": "19"},
                    {"id": "D", "label": "20"},
                ],
                "evaluation": {
                    "expectedOptionId": "C",
                    "normalization": ["trim", "casefold"],
                },
            }
        )
        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )

        variants = []
        wrong_answer = copy.deepcopy(course)
        wrong_answer["content"]["questions"][1]["answer"] = "B"
        wrong_answer["content"]["questions"][1]["evaluation"][
            "expectedOptionId"
        ] = "B"
        variants.append(wrong_answer)
        missing_target = copy.deepcopy(course)
        missing_target["content"]["questions"][1]["choices"][2]["label"] = "16"
        variants.append(missing_target)
        duplicate_target = copy.deepcopy(course)
        duplicate_target["content"]["questions"][1]["choices"][1]["label"] = "19"
        variants.append(duplicate_target)
        for variant in variants:
            with self.subTest(variant=variant["content"]["questions"][1]):
                with self.assertRaises(Exception):
                    self.validator.catalog_validator.validate_primary_one_generated_course(
                        variant,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_number_sense_between_authority_uses_explicit_endpoints_in_either_order(self):
        def replace_guided_question(question, prompt, selected_label="19"):
            question.update(
                {
                    "prompt": prompt,
                    "hint": "只根据两个端点找中间唯一的数。",
                    "explanation": f"两个端点之间唯一的数是{selected_label}。",
                    "answer": "C",
                    "choices": [
                        {"id": "A", "label": "17"},
                        {"id": "B", "label": "18"},
                        {"id": "C", "label": selected_label},
                        {"id": "D", "label": "20"},
                    ],
                    "evaluation": {
                        "expectedOptionId": "C",
                        "normalization": ["trim", "casefold"],
                    },
                }
            )

        for prompt in (
            "20和18中间还缺一个数，应该填哪个数字？",
            "20与18之间还缺一个数，应该填哪个数字？",
        ):
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            replace_guided_question(course["content"]["questions"][0], prompt)
            with self.subTest(prompt=prompt):
                self.validator.catalog_validator.validate_primary_one_generated_course(
                    course,
                    target=target,
                    skill_boundary=boundary,
                )

        invalid_cases = (
            ("18和19中间还缺一个数，应该填哪个数字？", "19"),
            ("17和20中间还缺一些数，应该填哪些数字？", "18和19"),
            ("19和21中间还缺一个数，应该填哪个数字？", "20"),
        )
        for prompt, selected_label in invalid_cases:
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            replace_guided_question(
                course["content"]["questions"][0],
                prompt,
                selected_label,
            )
            with self.subTest(prompt=prompt):
                with self.assertRaises(Exception):
                    self.validator.catalog_validator.validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_number_sense_composition_rejects_noncanonical_numeric_target_tokens(self):
        cases = (
            ("零下1", 1),
            ("-1", 1),
            ("- 1", 1),
            ("+1", 1),
            ("+ 1", 1),
            ("－1", 1),
            ("＋1", 1),
            ("−1", 1),
            ("‐1", 1),
            ("–1", 1),
            ("—1", 1),
            ("负1", 1),
            ("负 1", 1),
            ("正1", 1),
            ("正 1", 1),
            ("1.0", 1),
            ("1.1", 1),
            (".1", 1, ".1是由几个十和几个一组成的?"),
            ("．１", 1, "．１是由几个十和几个一组成的?"),
            ("1e0", 1),
            ("1e1", 1),
            ("0x1", 0),
            ("0x0", 0),
            ("01", 1),
            ("1/1", 1),
            ("1+1", 1),
            ("A1", 1),
            ("1_", 1),
            ("1a", 1),
            ("1点1", 1),
            ("1%", 1),
            ("百分之1", 1),
            ("千分之1", 1),
            ("十分之 1", 1),
            ("二分之１", 1),
            ("千分之 １", 1),
            ("1又二分之一", 1),
            ("负的1", 1),
            ("负的 1", 1),
            ("负的,1", 1),
            ("负的:1", 1, "负的:1是由几个十和几个一组成的?"),
            ("比例:1", 1, "比例:1是由几个十和几个一组成的?"),
            (
                "小云雀想知道1",
                1,
                "小云雀想知道1是由几个十和几个一组成的?",
            ),
            (
                "FEFF before target",
                1,
                "请问\uFEFF1是由几个十和几个一组成的?",
            ),
            ("¹", 1),
            ("₁", 1),
            ("①", 1),
            ("½", 1),
            (
                "letter-number background numeral",
                1,
                "卡片写着数字Ⅳ。请问,1是由几个十和几个一组成的?",
            ),
            (
                "Chinese background numeral",
                1,
                "卡片写着数字十六。请问,1是由几个十和几个一组成的?",
            ),
            (
                "Chinese background numeral 廿",
                1,
                "卡片写着数字廿。请问,1是由几个十和几个一组成的?",
            ),
            (
                "Chinese background place value numeral",
                1,
                "卡片写着数字壹拾陆。请问,1是由几个十和几个一组成的?",
            ),
            (
                "Chinese ordinal background",
                16,
                "第十六张卡片写着数字16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "arabic-indic background digit",
                1,
                "卡片写着数字١。请问,1是由几个十和几个一组成的?",
            ),
            ("零下的1", 1),
            ("小于1", 1),
            ("约1", 1),
            ("负数1", 1),
            ("负数数字1", 1),
            ("小鹿请问1", 1),
            (
                "malicious background 负的16",
                16,
                "卡片写着负的16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "malicious background 零下的16",
                16,
                "卡片写着零下的16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "malicious background 小于16",
                16,
                "卡片写着小于16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "malicious background 约16",
                16,
                "卡片写着约16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "malicious background 负数16",
                16,
                "卡片写着负数16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "negated background 有1个",
                1,
                "小鹿没有1个苹果。请问,1是由几个十和几个一组成的?",
            ),
            (
                "negated background 写着数字1",
                1,
                "卡片没有写着数字1。请问,1是由几个十和几个一组成的?",
            ),
            (
                "approximate background 大约有1个",
                1,
                "小鹿大约有1个苹果。请问,1是由几个十和几个一组成的?",
            ),
            (
                "range background 至少有1个",
                1,
                "小鹿至少有1个苹果。请问,1是由几个十和几个一组成的?",
            ),
            *(
                (
                    f"unsupported background {prefix}",
                    1,
                    f"盒子{prefix}1个苹果。请问,1是由几个十和几个一组成的?",
                )
                for prefix in (
                    "最多有",
                    "最少有",
                    "可能有",
                    "估计有",
                    "避免有",
                    "拒绝有",
                    "相反数有",
                    "加一有",
                    "减一有",
                    "左右有",
                )
            ),
            (
                "unsafe background suffix 负数 quantity",
                1,
                "盒子有1个负数。请问,1是由几个十和几个一组成的?",
            ),
            (
                "unsafe background suffix labeled number",
                1,
                "卡片写着数字1是负数。请问,1是由几个十和几个一组成的?",
            ),
            (
                "unsafe background suffix bare numeric label",
                1,
                "数字1是负数。请问,1是由几个十和几个一组成的?",
            ),
            (
                "sunshine-lab fruit-basket approximate prefix",
                16,
                "小浣熊的阳光实验室里，果篮上大约标着数字16。"
                "请问,16是由几个十和几个一组成的?",
            ),
            (
                "sunshine-lab fruit-basket unsafe suffix",
                16,
                "小浣熊的阳光实验室里，果篮上标着数字16是负数。"
                "请问,16是由几个十和几个一组成的?",
            ),
            (
                "finished-sticker negated prefix",
                16,
                "小水獭在童话运动场上贴贴纸。"
                "它没有已经贴好了16张贴纸。"
                "16是由几个十和几个一组成的?",
            ),
            (
                "finished-sticker approximate prefix",
                16,
                "小水獭在童话运动场上贴贴纸。"
                "它大约已经贴好了16张贴纸。"
                "16是由几个十和几个一组成的?",
            ),
            (
                "finished-sticker distinct background value",
                16,
                "小水獭在童话运动场上贴贴纸。"
                "它已经贴好了15张贴纸。"
                "16是由几个十和几个一组成的?",
            ),
            (
                "finished-sticker unsafe suffix",
                16,
                "小水獭在童话运动场上贴贴纸。"
                "它已经贴好了16张贴纸以上。"
                "16是由几个十和几个一组成的?",
            ),
            ("carriage return", 1, "请问\r1是由几个十和几个一组成的?"),
            ("line feed", 1, "请问\n1是由几个十和几个一组成的?"),
            ("vertical tab", 1, "请问\u000B1是由几个十和几个一组成的?"),
            ("form feed", 1, "请问\u000C1是由几个十和几个一组成的?"),
            ("next line", 1, "请问\u00851是由几个十和几个一组成的?"),
            ("line separator", 1, "请问\u20281是由几个十和几个一组成的?"),
            (
                "paragraph separator",
                1,
                "请问\u20291是由几个十和几个一组成的?",
            ),
            (
                "split witness",
                1,
                "请问,1里面有几个十和几个一，是老师示范过的内容。"
                "负的1是由几个十和几个一组成的？",
            ),
            (
                "extra paired cue",
                16,
                "请问,16是由几个十和几个一组成的？"
                "老师又写了“几个十和几个一”。",
            ),
            (
                "distinct story number",
                16,
                "第2张卡片写着数字16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "cross-sentence composition",
                16,
                "卡片上写着数字16。这张卡片由几个十和几个一组成的?",
            ),
            (
                "cross-ASCII-sentence composition",
                16,
                "卡片上写着数字16. 这张卡片由几个十和几个一组成的?",
            ),
            ("21", 20),
        )
        for case in cases:
            token, misparsed_target, *prompt_override = case
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            question = course["content"]["questions"][4]
            represented_values = (
                misparsed_target,
                *(
                    value
                    for value in (0, 1, 2, 8, 9, 10, 15, 16, 17, 18, 19, 20)
                    if value != misparsed_target
                ),
            )[:3]
            question.update(
                {
                    "prompt": prompt_override[0]
                    if prompt_override
                    else (
                        f"卡片上写着数字{token}。"
                        f"请问,{token}是由几个十和几个一组成的?"
                    ),
                    "hint": "先读十位,再读个位。",
                    "explanation": (
                        f"{misparsed_target}由{misparsed_target // 10}个十和"
                        f"{misparsed_target % 10}个一组成。"
                    ),
                }
            )
            other_values = iter(represented_values[1:])
            for choice in question["choices"]:
                value = (
                    represented_values[0]
                    if choice["id"] == question["answer"]
                    else next(other_values)
                )
                choice["label"] = f"{value // 10}个十和{value % 10}个一"
            with self.subTest(token=token):
                with self.assertRaises(Exception):
                    self.validator.catalog_validator.validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_number_sense_composition_accepts_boundary_targets_and_nfkc_digits(self):
        cases = (
            ("0", 0, "0个十和0个一"),
            ("1", 1, "0个十和1个一"),
            ("9", 9, "0个十和9个一"),
            ("10", 10, "1个十和0个一"),
            ("20", 20, "2个十和0个一"),
            ("１６", 16, "1个十和6个一"),
            (
                "16这个数",
                16,
                "1个十和6个一",
                "卡片上写着数字16。"
                "请问,16这个数是由几个十和几个一组成的?",
            ),
            ("start-16", 16, "1个十和6个一", "16由几个十和几个一组成的?"),
            (
                "punctuation-16",
                16,
                "1个十和6个一",
                "请看。16由几个十和几个一组成的?",
            ),
            (
                "numeric-prefix-16",
                16,
                "1个十和6个一",
                "数字16是由几个十和几个一组成的?",
            ),
            (
                "ask-prefix-16",
                16,
                "1个十和6个一",
                "请问16是由几个十和几个一组成的?",
            ),
            (
                "ask-delimiter-16",
                16,
                "1个十和6个一",
                "请问,16是由几个十和几个一组成的?",
            ),
            (
                "ask-colon-16",
                16,
                "1个十和6个一",
                "请问:16是由几个十和几个一组成的?",
            ),
            (
                "ask-python-whitespace-16",
                16,
                "1个十和6个一",
                "请问\u001C16是由几个十和几个一组成的?",
            ),
            (
                "ask-long-python-whitespace-16",
                16,
                "1个十和6个一",
                "请问" + (" " * 60) + "16是由几个十和几个一组成的?",
            ),
            (
                "then-prefix-16",
                16,
                "1个十和6个一",
                "那么16是由几个十和几个一组成的?",
            ),
            (
                "among-prefix-16",
                16,
                "1个十和6个一",
                "其中16是由几个十和几个一组成的?",
            ),
            (
                "colon-18",
                18,
                "1个十和8个一",
                "小云雀想知道:18是由几个十和几个一组成的?",
            ),
            (
                "background-has-16",
                16,
                "1个十和6个一",
                "小刺猬有16颗石子。16由几个十和几个一组成?",
            ),
            (
                "background-loaded-16",
                16,
                "1个十和6个一",
                "盒子装了16个积木。请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-caught-16",
                16,
                "1个十和6个一",
                "小猫钓到了16条鱼。请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-total-16",
                16,
                "1个十和6个一",
                "拼板一共是16块。请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-written-16",
                16,
                "1个十和6个一",
                "卡片写着16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-written-number-16",
                16,
                "1个十和6个一",
                "卡片写着16号。请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-number-is-16",
                16,
                "1个十和6个一",
                "卡片的数字是16。请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-labeled-16",
                16,
                "1个十和6个一",
                "小狐狸有一张写着数字16的星星卡。"
                "请问,16是由几个十和几个一组成的?",
            ),
            (
                "background-sunshine-lab-fruit-basket-16",
                16,
                "1个十和6个一",
                "小浣熊的阳光实验室里，果篮上标着数字16。"
                "16是由几个十和几个一组成的？",
            ),
            (
                "background-finished-stickers-16",
                16,
                "1个十和6个一",
                "小水獭在童话运动场上贴贴纸。"
                "它已经贴好了16张贴纸。"
                "16是由几个十和几个一组成的？",
            ),
            (
                "background-ticket-14",
                14,
                "1个十和4个一",
                "小狐狸有一张写着数字14的车票。"
                "14是由几个十和几个一组成的?",
            ),
            (
                "background-fruit-18",
                18,
                "1个十和8个一",
                "果篮里有18个果子。18是由几个十和几个一组成的?",
            ),
        )
        for case in cases:
            token, target_value, expected_label, *prompt_override = case
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            question = course["content"]["questions"][4]
            other_values = [
                value
                for value in (0, 1, 2, 8, 9, 10, 15, 16, 17, 18, 19, 20)
                if value != target_value
            ][:2]
            question.update(
                {
                    "prompt": prompt_override[0]
                    if prompt_override
                    else (
                        f"卡片上写着数字{token}。"
                        f"请问,{token}是由几个十和几个一组成的?"
                    ),
                    "hint": "先读十位,再读个位。",
                    "explanation": f"{target_value}由{expected_label}组成。",
                }
            )
            values = iter(other_values)
            for choice in question["choices"]:
                value = (
                    target_value
                    if choice["id"] == question["answer"]
                    else next(values)
                )
                choice["label"] = f"{value // 10}个十和{value % 10}个一"
            with self.subTest(token=token):
                self.validator.catalog_validator.validate_primary_one_generated_course(
                    course,
                    target=target,
                    skill_boundary=boundary,
                )

    def test_number_sense_accepts_middle_position_from_three_listed_values(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        question = course["content"]["questions"][0]
        question["prompt"] = (
            "小鲸鱼在童话运动场的邮票屋里整理邮票。"
            "它把邮票按数量排成一排:13张、15张、17张。"
            "小鲸鱼想找出中间那张邮票的数量。中间位置的数是多少?"
        )
        question["hint"] = (
            "想想这三个数在数数时的顺序,谁排在最前面,"
            "谁排在最后面,谁就在中间。"
        )
        question["explanation"] = (
            "13、15、17三个数按顺序排列,13最小,17最大,"
            "15正好在它们中间。所以中间位置的数是15。"
        )
        other_labels = iter(("13", "17"))
        for choice in question["choices"]:
            choice["label"] = (
                "15"
                if choice["id"] == question["answer"]
                else next(other_labels)
            )

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )
        result = self._host(course, target, boundary, identity)
        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_number_sense_accepts_one_recomputable_descending_internal_blank(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        question = course["content"]["questions"][1]
        question["prompt"] = (
            "邮票按号码从大到小排成一队:20、19、18、17、□、15。"
            "空格里的号码应该是几?"
        )
        question["hint"] = "从20开始每次少1。"
        question["explanation"] = "17后面是16,16后面是15。"
        for choice, label in zip(question["choices"], ("14", "18", "16")):
            choice["label"] = label

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )
        result = self._host(course, target, boundary, identity)
        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_number_sense_accepts_recomputable_labeled_comparison_choices(self):
        course, target, boundary, _evidence, _identity = formal_host_fixture(
            "number_sense_20"
        )
        questions = course["content"]["questions"]

        def relabel(question, selected_label, other_labels):
            remaining = iter(other_labels)
            for choice in question["choices"]:
                choice["label"] = (
                    selected_label
                    if choice["id"] == question["answer"]
                    else next(remaining)
                )

        questions[0]["prompt"] = (
            "第一堆有14颗石子，第二堆有17颗石子。哪一堆石子更多呢？"
        )
        relabel(questions[0], "17颗石子", ("14颗石子", "两堆一样多"))
        questions[1]["prompt"] = "数字按0到20的顺序排列，数字19的后一个数是几？"
        relabel(questions[1], "20", ("18", "19"))
        questions[2]["prompt"] = (
            "一张车票写着8号，另一张写着15号。哪张车票的数字更大？"
        )
        relabel(questions[2], "15号车票", ("8号车票", "两个数字一样大"))
        questions[3]["prompt"] = (
            "红色画笔有6支，蓝色画笔有16支。比较这两个数，哪个说法正确？"
        )
        relabel(questions[3], "16大于6", ("6大于16", "6等于16"))

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )

    def test_number_sense_uses_explicit_pair_after_background_range(self):
        course, target, boundary, _evidence, _identity = formal_host_fixture(
            "number_sense_20"
        )
        question = course["content"]["questions"][0]
        question.update(
            {
                "prompt": (
                    "小浣熊的纸艺工坊里，书签编号从1号排到20号。"
                    "15号书签和8号书签，哪个编号更大？"
                ),
                "hint": "分别看15和8有几个十。",
                "explanation": "15比8大，所以应选择15号书签。",
                "choices": [
                    {"id": "A", "label": "15号"},
                    {"id": "B", "label": "8号"},
                ],
                "answer": "A",
                "evaluation": {
                    "expectedOptionId": "A",
                    "normalization": ["trim", "casefold"],
                },
            }
        )

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )

    def test_number_sense_quantity_pair_stays_recomputable_after_host_label_normalization(
        self,
    ):
        for labels in (("17张", "9张"), ("17", "9")):
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            question = course["content"]["questions"][0]
            question.update(
                {
                    "prompt": (
                        "小浣熊的纸艺工坊里，贴纸有两种包装。"
                        "一种贴纸有17张，另一种贴纸有9张。哪种贴纸更多？"
                    ),
                    "hint": "比较17和9的十位。",
                    "explanation": "17比9大，所以17张更多。",
                    "choices": [
                        {"id": "A", "label": labels[0]},
                        {"id": "B", "label": labels[1]},
                    ],
                    "answer": "A",
                    "evaluation": {
                        "expectedOptionId": "A",
                        "normalization": ["trim", "casefold"],
                    },
                }
            )

            with self.subTest(labels=labels):
                self.validator.catalog_validator.validate_primary_one_generated_course(
                    course,
                    target=target,
                    skill_boundary=boundary,
                )

    def test_number_sense_binary_relation_preserves_prompt_operand_order(self):
        course, target, boundary, _evidence, _identity = formal_host_fixture(
            "number_sense_20"
        )
        question = course["content"]["questions"][3]
        question.update(
            {
                "prompt": "14和5的大小关系是哪一个？",
                "choices": [
                    {"id": "A", "label": "14大于5"},
                    {"id": "B", "label": "14小于5"},
                    {"id": "C", "label": "14等于5"},
                ],
                "answer": "A",
                "evaluation": {
                    "expectedOptionId": "A",
                    "normalization": ["trim", "casefold"],
                },
            }
        )

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )

    def test_number_sense_binary_comparison_rejects_non_unique_operand_evidence(
        self,
    ):
        variants = (
            (
                "background range only",
                "书签编号从1号排到20号。哪个编号更大？",
                (("A", "20号"), ("B", "1号")),
                "A",
                "唯一可复算证据",
            ),
            (
                "three comparison values",
                "15号、8号和6号书签中，哪个编号更大？",
                (("A", "15号"), ("B", "8号"), ("C", "6号")),
                "A",
                "唯一可复算证据",
            ),
            (
                "duplicate operands",
                "15号书签和15号书签，哪个编号更大？",
                (("A", "15号"), ("B", "8号")),
                "A",
                "唯一可复算证据",
            ),
            (
                "missing operand choice",
                "15号书签和8号书签，哪个编号更大？",
                (("A", "15号"), ("B", "7号")),
                "A",
                "唯一可复算证据",
            ),
            (
                "duplicate target mapping",
                "15号书签和8号书签，哪个编号更大？",
                (("A", "15号"), ("B", "15"), ("C", "8号")),
                "A",
                "唯一可复算证据",
            ),
            (
                "out of range operand",
                "21号书签和8号书签，哪个编号更大？",
                (("A", "21号"), ("B", "8号")),
                "A",
                "超出0到20",
            ),
            (
                "unit semantic mismatch",
                "一种贴纸有17张，另一种贴纸有9张。哪种贴纸更多？",
                (("A", "17号书签"), ("B", "9号书签")),
                "A",
                "唯一可复算证据",
            ),
            (
                "wrong selected operand",
                "15号书签和8号书签，哪个编号更大？",
                (("A", "15号"), ("B", "8号")),
                "B",
                "唯一可复算证据",
            ),
        )
        for name, prompt, choices, answer, error in variants:
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            question = course["content"]["questions"][0]
            question.update(
                {
                    "prompt": prompt,
                    "hint": "根据题意比较两个明确给出的数。",
                    "explanation": "根据题目明确给出的两个数进行比较。",
                    "choices": [
                        {"id": choice_id, "label": label}
                        for choice_id, label in choices
                    ],
                    "answer": answer,
                    "evaluation": {
                        "expectedOptionId": answer,
                        "normalization": ["trim", "casefold"],
                    },
                }
            )

            with self.subTest(name=name):
                with self.assertRaisesRegex(Exception, error):
                    self.validator.catalog_validator.validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_number_sense_accepts_v55_recomputable_extrema_prompts(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        questions = course["content"]["questions"]
        questions[0].update(
            {
                "prompt": (
                    "小云雀在海风收藏屋里收集树叶。第一天她收集了14片树叶,"
                    "第二天收集了17片树叶,第三天收集了20片树叶。"
                    "她想把树叶按从少到多排好,放在架子上。"
                    "排在最后面的那一堆树叶,数量是多少?"
                ),
                "hint": "把三个数量从少到多排一排。",
                "explanation": "14、17、20从少到多排列,最后面的数量是20。",
            }
        )
        questions[2].update(
            {
                "prompt": (
                    "海风收藏屋里有三个齿轮,上面分别标着数字。"
                    "第一个齿轮标着9,第二个齿轮标着16,第三个齿轮标着20。"
                    "小云雀说:'最大的数所在的齿轮转得最快。'哪个数字最大?"
                ),
                "hint": "比较三个数的大小。",
                "explanation": "9、16、20中最大的数是20。",
            }
        )
        questions[1].update(
            {
                "prompt": "数字按0到20的顺序排列,数字18的后一个数是几?",
                "hint": "从题目给出的数开始,按顺序一个一个数。",
                "explanation": "18的后一个数是19。",
            }
        )
        questions[3].update(
            {
                "prompt": (
                    "小云雀有两张星星卡,一张写着7,另一张写着14。"
                    "她想知道哪张星星卡的数字更大。"
                    "请你帮她比较:7和14,哪个数更大?"
                ),
                "hint": "先比较十位;十位相同,再比较个位。",
                "explanation": "7是一位数,14是两位数,所以14更大。",
            }
        )
        questions[4].update(
            {
                "prompt": (
                    "海风收藏屋里有一张特殊的卡片,上面画着数字18。"
                    "小云雀想知道:18是由几个十和几个一组成的?"
                    "请你从下面的选项中选出正确的答案。"
                ),
                "hint": "先读十位上的数字,再读个位上的数字。",
                "explanation": "18由1个十和8个一组成。",
            }
        )
        exact_choice_shells = (
            (("A", "14"), ("B", "17"), ("C", "20"), "C"),
            (("A", "17"), ("B", "19"), ("C", "20"), "B"),
            (("A", "9"), ("B", "16"), ("C", "20"), "C"),
            (("A", "7"), ("B", "14"), "B"),
            (
                ("A", "0个十和8个一"),
                ("B", "1个十和8个一"),
                ("C", "1个十和0个一"),
                ("D", "2个十和0个一"),
                "B",
            ),
        )
        for question, shell in zip(questions, exact_choice_shells):
            *raw_choices, answer = shell
            question["choices"] = [
                {"id": choice_id, "label": label}
                for choice_id, label in raw_choices
            ]
            question["answer"] = answer
            question["evaluation"] = {
                "expectedOptionId": answer,
                "normalization": ["trim", "casefold"],
            }

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )
        result = self._host(course, target, boundary, identity)
        self.assertEqual(result.outcome, "passed", result.receipt)

    def test_number_sense_rejects_ambiguous_or_unsafe_extrema_prompts(self):
        variants = (
            (
                "both extrema",
                "第一张卡片写着9，第二张写着16，第三张写着20。最大的数和最小的数分别是哪个？",
                ("9", "16", "20"),
            ),
            (
                "duplicate listed value",
                "第一张卡片写着9，第二张写着16，第三张也写着16。哪个数字最大？",
                ("9", "16", "20"),
            ),
            (
                "missing target choice",
                "第一张卡片写着9，第二张写着16，第三张写着20。哪个数字最大？",
                ("9", "16", "15"),
            ),
            (
                "duplicate target choice",
                "第一张卡片写着9，第二张写着16，第三张写着20。哪个数字最大？",
                ("20", "20", "9"),
            ),
            (
                "wrong selected answer",
                "第一张卡片写着9，第二张写着16，第三张写着20。哪个数字最大？",
                ("20", "9", "16"),
            ),
            (
                "out of range listed value",
                "第一张卡片写着9，第二张写着16，第三张写着21。哪个数字最大？",
                ("9", "16", "20"),
            ),
            (
                "unsupported descending endpoint",
                "第一堆有20个，第二堆有16个，第三堆有9个。按从多到少排好，排在最后面的数量是多少？",
                ("20", "16", "9"),
            ),
        )
        for name, prompt, labels in variants:
            course, target, boundary, _evidence, _identity = formal_host_fixture(
                "number_sense_20"
            )
            question = course["content"]["questions"][2]
            question.update(
                {
                    "prompt": prompt,
                    "hint": "根据题意判断。",
                    "explanation": "比较题目中列出的数。",
                }
            )
            for choice, label in zip(question["choices"], labels):
                choice["label"] = label
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    Exception,
                    "唯一可复算证据|选项文案重复|超出0到20|版本化权威不一致",
                ):
                    self.validator.catalog_validator.validate_primary_one_generated_course(
                        course,
                        target=target,
                        skill_boundary=boundary,
                    )

    def test_number_sense_extrema_supports_minimum_and_ascending_front_bounds(self):
        variants = (
            (
                "第一张卡片写着9,第二张写着20。哪个数字最小?",
                (("A", "9"), ("B", "20")),
                "A",
            ),
            (
                "第一张卡片写着1,第二张写着3,第三张写着5,"
                "第四张写着7,第五张写着9,第六张写着11,"
                "第七张写着13,第八张写着20。"
                "按从少到多排好,排在最前面的数字是几?",
                (
                    ("A", "1"),
                    ("B", "3"),
                    ("C", "5"),
                    ("D", "7"),
                    ("E", "9"),
                    ("F", "11"),
                    ("G", "13"),
                    ("H", "20"),
                ),
                "A",
            ),
        )
        for prompt, choices, answer in variants:
            course, target, boundary, _evidence, identity = formal_host_fixture(
                "number_sense_20"
            )
            question = course["content"]["questions"][2]
            question.update(
                {
                    "prompt": prompt,
                    "hint": "根据题意判断。",
                    "explanation": "比较题目中列出的数。",
                    "choices": [
                        {"id": choice_id, "label": label}
                        for choice_id, label in choices
                    ],
                    "answer": answer,
                    "evaluation": {
                        "expectedOptionId": answer,
                        "normalization": ["trim", "casefold"],
                    },
                }
            )
            self.validator.catalog_validator.validate_primary_one_generated_course(
                course,
                target=target,
                skill_boundary=boundary,
            )
            result = self._host(course, target, boundary, identity)
            self.assertEqual(result.outcome, "passed", result.receipt)

    def test_number_sense_accepts_only_matching_compact_comparison_labels(self):
        course, target, boundary, _evidence, _identity = formal_host_fixture(
            "number_sense_20"
        )
        questions = course["content"]["questions"]

        def relabel(question, selected_label, other_labels):
            remaining = iter(other_labels)
            for choice in question["choices"]:
                choice["label"] = (
                    selected_label
                    if choice["id"] == question["answer"]
                    else next(remaining)
                )

        questions[0]["prompt"] = "第一排有14支画笔，第二排有17支。哪个数字更大？"
        relabel(questions[0], "17更大", ("14更大", "一样大"))
        questions[1]["prompt"] = "数字按0到20排列，19的后一个数是几？"
        relabel(questions[1], "20", ("18", "19"))
        questions[2]["prompt"] = "一片树叶写着20，另一片写着15。哪个数字更大？"
        relabel(questions[2], "20更大", ("15更大", "一样大"))
        questions[3]["prompt"] = "一个篮子有12颗豆子，另一个有20颗。请比较12和20，哪个数字更小？"
        relabel(questions[3], "12更小", ("20更小", "一样小"))

        self.validator.catalog_validator.validate_primary_one_generated_course(
            course,
            target=target,
            skill_boundary=boundary,
        )

        mismatched = copy.deepcopy(course)
        selected = next(
            choice
            for choice in mismatched["content"]["questions"][0]["choices"]
            if choice["id"] == mismatched["content"]["questions"][0]["answer"]
        )
        selected["label"] = "17更小"
        with self.assertRaises(Exception):
            self.validator.catalog_validator.validate_primary_one_generated_course(
                mismatched,
                target=target,
                skill_boundary=boundary,
            )

    def test_all_ten_boundaries_have_a_valid_formal_golden(self):
        for skill_id in _FORMAL_SKILLS:
            with self.subTest(skill_id=skill_id):
                course, target, boundary, evidence, identity = formal_host_fixture(
                    skill_id
                )
                result = self.validator.validate_primary_one_host_gate(
                    evidence,
                    target=target,
                    identity=identity,
                    skill_boundary=boundary,
                    accepted_host_receipts=(),
                )
                self.assertEqual(result.outcome, "passed", result.receipt)
                self.assertEqual(result.course["nodeCode"], skill_id)
                self.assertEqual(course["status"], "unverified")

    def test_each_boundary_rejects_leak_prerequisite_range_scoring_language_roles_and_answer(self):
        for skill_id in _FORMAL_SKILLS:
            base_course, target, boundary, _evidence, identity = formal_host_fixture(
                skill_id
            )

            with self.subTest(skill_id=skill_id, mutation="answer-leak"):
                course = copy.deepcopy(base_course)
                question = self._first_choice(course)
                selected = next(
                    choice["label"]
                    for choice in question["choices"]
                    if choice["id"] == question["answer"]
                )
                question["hint"] = f"正确答案是{selected}。"
                self.assertEqual(
                    self._host(course, target, boundary, identity).outcome,
                    "rejected",
                )

            with self.subTest(skill_id=skill_id, mutation="prerequisite-drift"):
                drifted = copy.deepcopy(boundary)
                drifted["prerequisiteSkills"] = [
                    *drifted["prerequisiteSkills"],
                    "forged_prerequisite",
                ]
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self.validator.validate_primary_one_host_gate(
                        self._refresh(base_course, target, boundary, identity),
                        target=target,
                        identity=identity,
                        skill_boundary=drifted,
                        accepted_host_receipts=(),
                    )

            with self.subTest(skill_id=skill_id, mutation="out-of-range"):
                course = copy.deepcopy(base_course)
                question = self._first_choice(course)
                for choice in question["choices"]:
                    if choice["id"] == question["answer"]:
                        choice["label"] = "越界内容"
                self.assertEqual(
                    self._host(course, target, boundary, identity).outcome,
                    "rejected",
                )

            with self.subTest(skill_id=skill_id, mutation="ambiguous-scoring"):
                course = copy.deepcopy(base_course)
                course["content"]["questions"][3]["prompt"] = "请选择正确答案。"
                self.assertEqual(
                    self._host(course, target, boundary, identity).outcome,
                    "rejected",
                )

            with self.subTest(skill_id=skill_id, mutation="wrong-target-language"):
                course = copy.deepcopy(base_course)
                question = self._first_choice(course)
                for choice in question["choices"]:
                    if choice["id"] == question["answer"]:
                        choice["label"] = (
                            "错误目标语言"
                            if target.target_language_code == "en-US"
                            else "wrong-language-answer"
                        )
                self.assertEqual(
                    self._host(course, target, boundary, identity).outcome,
                    "rejected",
                )

            with self.subTest(skill_id=skill_id, mutation="reordered-roles"):
                course = copy.deepcopy(base_course)
                guided = course["content"]["teachingFlow"]["guidedQuestionIds"]
                course["content"]["teachingFlow"]["guidedQuestionIds"] = list(
                    reversed(guided)
                )
                with self.assertRaises(PrimaryOneHostGateControlError):
                    self._host(course, target, boundary, identity)

            with self.subTest(skill_id=skill_id, mutation="invalid-answer"):
                course = copy.deepcopy(base_course)
                question = self._first_choice(course)
                question["answer"] = question["choices"][0]["id"]
                question["evaluation"]["expectedOptionId"] = question["answer"]
                self.assertEqual(
                    self._host(course, target, boundary, identity).outcome,
                    "rejected",
                )

    def test_valid_sealed_inventory_modes_are_not_tied_to_golden_wording(self):
        cases = []

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        question = course["content"]["questions"][0]
        question["prompt"] = "跟读单韵母 a,应选择哪个符号?"
        cases.append(("pinyin-repetition", course, target, boundary, identity))

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "shapes_position"
        )
        question = course["content"]["questions"][0]
        question["prompt"] = (
            "有四个直角且相邻边长度不同的图形叫什么?"
        )
        question["choices"] = [
            {"id": "option_1", "label": "圆形"},
            {"id": "option_2", "label": "正方形"},
            {"id": "option_3", "label": "长方形"},
        ]
        question["answer"] = "option_3"
        question["evaluation"]["expectedOptionId"] = "option_3"
        question["explanation"] = "提交后核对,这是长方形。"
        cases.append(("sealed-rectangle", course, target, boundary, identity))

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "letters_sounds"
        )
        question = course["content"]["questions"][0]
        question["prompt"] = "小写字母 a 对应哪个大写字母?"
        question["choices"] = [
            {"id": "option_1", "label": "B"},
            {"id": "option_2", "label": "E"},
            {"id": "option_3", "label": "A"},
        ]
        question["answer"] = "option_3"
        question["evaluation"]["expectedOptionId"] = "option_3"
        question["explanation"] = "提交后核对,小写 a 对应大写 A。"
        cases.append(("lower-to-upper", course, target, boundary, identity))

        for label, course, target, boundary, identity in cases:
            with self.subTest(label=label):
                self.assertEqual(
                    self._host(
                        course, target, boundary, identity
                    ).outcome,
                    "passed",
                )

    def test_pinyin_sound_evidence_ignores_e_cue_inside_penguin_noun(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        course["content"]["questions"][0]["prompt"] = (
            '小企鹅看到嘴巴张大,听到"啊".这是哪个单韵母?'
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "passed",
        )

    def test_pinyin_quoted_sound_cue_before_reading_context_is_evidence(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        course["content"]["questions"][0]["prompt"] = (
            '小狐狸拿出一张卡片,卡片上写着:"啊".'
            '这个读音对应哪个单韵母?'
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "passed",
        )

    def test_pinyin_bare_read_sound_cue_is_host_sealed_evidence(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        course["content"]["questions"][1]["prompt"] = (
            '小狐狸说:"读喔."这个读音对应哪个单韵母?'
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "passed",
        )

    def test_pinyin_follow_me_cue_is_host_sealed_evidence(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        course["content"]["questions"][0]["prompt"] = (
            '萤火虫说:"跟我读,a."这个单韵母是什么?'
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "passed",
        )

        course["content"]["questions"][0]["prompt"] = (
            '萤火虫举着一张写有 a 的卡片.这个单韵母是什么?'
        )
        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )

    def test_tones_color_coverage_and_one_step_ast_are_required(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_initials_syllables"
        )
        course["content"]["teachingFlow"]["teach"]["sayText"] = (
            "声母和已学韵母可以拼成简单两拼音节。"
        )
        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "numbers_colors"
        )
        all_number_rows = (
            (3, "数字19对应哪个英语数词?", "nineteen", ("nine", "twenty")),
            (4, "数字20对应哪个英语数词?", "twenty", ("twelve", "two")),
        )
        for index, prompt, answer, distractors in all_number_rows:
            question = course["content"]["questions"][index]
            question["prompt"] = prompt
            question["choices"] = [
                {"id": "option_1", "label": distractors[0]},
                {"id": "option_2", "label": distractors[1]},
                {"id": "option_3", "label": answer},
            ]
            question["answer"] = "option_3"
            question["evaluation"]["expectedOptionId"] = "option_3"
            question["explanation"] = f"提交后核对,正确内容是 {answer}。"
        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )

        course, target, boundary, _evidence, identity = formal_host_fixture(
            "addition_subtraction_20"
        )
        course["content"]["questions"][0]["verificationExpression"] = "7+5+0"
        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )

    def test_practice_hint_cannot_be_the_correct_option_without_a_lead_in(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        question = course["content"]["questions"][1]
        question["hint"] = next(
            choice["label"]
            for choice in question["choices"]
            if choice["id"] == question["answer"]
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )

    def test_pinyin_forbidden_teaching_targets_are_rejected(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        course["content"]["teachingFlow"]["teach"]["sayText"] += (
            " 还要学习偏旁和汉字识读。"
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )

    def test_shape_position_rejects_cross_axis_relation_without_shared_axis(self):
        course, target, boundary, _evidence, identity = formal_host_fixture(
            "shapes_position"
        )
        course["content"]["questions"][4]["prompt"] = (
            "练习甲:小猫在小狗左边,小狗在小鸟上方,小鸟在小猫哪一边?"
        )

        self.assertEqual(
            self._host(course, target, boundary, identity).outcome,
            "rejected",
        )


if __name__ == "__main__":
    unittest.main()
