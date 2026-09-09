from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from content.primary_skill_boundaries import PRIMARY_SKILL_BOUNDARIES
from integrations.openmaic_formal_media import (
    LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY, INTEGRATED_PROFESSIONAL_POLICY,
    PROFESSIONAL_POLICY, canonical_sha256, compatible_preparation_target, generation_options,
)
from integrations.openmaic_formal_pedagogy import grade_boundary_fields, validate_generation_grade_boundary
from integrations.openmaic_formal_skill_selection import select_formal_skills, skill_selection_plan
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint
from services.lesson_package_validator import formal_runtime_teaching_brief
from tests.test_formal_runtime_candidate_generation import SOURCE_COURSE_CONTENT_JSON, TEACHING_BRIEF, TEACHING_BRIEF_SHA256


def boundary_course(boundary):
    return {"id": "candidate-course-1", "version": "course-version-1", "grade_code": boundary.grade_code,
        "subject": boundary.subject, "node_code": boundary.skill_id, "title": "20以内数的认识",
        "objective": "理解20以内数的组成", "curriculum_version": boundary.curriculum_version,
        "boundary_version": boundary.boundary_version, "content_json": SOURCE_COURSE_CONTENT_JSON}


class OpenMaicFormalPedagogyTest(unittest.TestCase):
    def test_all_55_boundaries_are_exact_registry_projections_without_mutation(self):
        self.assertEqual(len(PRIMARY_SKILL_BOUNDARIES), 55)
        for boundary in PRIMARY_SKILL_BOUNDARIES:
            with self.subTest(grade=boundary.grade_code, skill=boundary.skill_id):
                course = boundary_course(boundary)
                original = deepcopy(course)
                fields = grade_boundary_fields(course, PROFESSIONAL_POLICY)
                self.assertEqual(fields["gradeBoundary"], boundary.to_catalog_payload())
                self.assertEqual(fields["gradeBoundarySha256"], canonical_sha256(boundary.to_catalog_payload()))
                generation = {"professionalCreationPolicy": PROFESSIONAL_POLICY, **fields,
                    "teachingBrief": {"schemaVersion": "mira.learning.formal-runtime-teaching-brief.v1",
                        "course": {"id": course["id"], "version": course["version"],
                        "gradeCode": boundary.grade_code, "subject": boundary.subject, "skillId": boundary.skill_id}}}
                generation["teachingBriefSha256"] = canonical_sha256(generation["teachingBrief"])
                self.assertEqual(validate_generation_grade_boundary(generation, course), fields)
                self.assertEqual(course, original)

    def test_old_brief_bytes_and_three_historical_target_hashes_remain_exact(self):
        course = boundary_course(PRIMARY_SKILL_BOUNDARIES[0])
        brief, digest, _ = formal_runtime_teaching_brief(course)
        self.assertEqual(brief, TEACHING_BRIEF)
        self.assertEqual(digest, TEACHING_BRIEF_SHA256)
        current = build_preparation_target("primary_1")
        for policy, expected in (
            (LEGACY_PROFESSIONAL_POLICY, "174a787e2ddbb8dd9c50e859a829bd2fe08fec71838448a8c5e5b0d2246766f1"),
            (IMAGE_PROFESSIONAL_POLICY, "48cceefd0543abe9e3bfcf2f8d640ef21b8e03503cfa3dc6ef89a0428bcef2df"),
            (INTEGRATED_PROFESSIONAL_POLICY, "7d4c0980789621cffb338e14b39c7dbc7b0d34c40013be0725c0076dad3b90a3"),
        ):
            with self.subTest(policy=policy):
                target = deepcopy(current)
                target["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(policy)
                from integrations.openmaic_formal_media import LEGACY_CONTENT_PROVIDER_PROFILE
                target["contentProviderProfileContractVersion"] = LEGACY_CONTENT_PROVIDER_PROFILE
                self.assertEqual(preparation_target_fingerprint(target), expected)
                self.assertNotEqual(preparation_target_fingerprint(current), expected)
                self.assertTrue(compatible_preparation_target(target, current))
                self.assertEqual(grade_boundary_fields(course, policy), {})
                self.assertEqual(validate_generation_grade_boundary({"professionalCreationPolicy": policy}), {})
                target["subjectTargets"]["math"]["totalCourseCount"] += 1
                self.assertFalse(compatible_preparation_target(target, current))

    def test_new_boundary_rejects_wrong_identity_version_hash_and_content(self):
        course = boundary_course(PRIMARY_SKILL_BOUNDARIES[0])
        generation = {"professionalCreationPolicy": PROFESSIONAL_POLICY, "teachingBrief": deepcopy(TEACHING_BRIEF),
                      "teachingBriefSha256": TEACHING_BRIEF_SHA256,
                      **grade_boundary_fields(course, PROFESSIONAL_POLICY)}
        mutations = (
            lambda g: g.pop("gradeBoundary"), lambda g: g.pop("gradeBoundarySha256"),
            lambda g: g.update(gradeBoundarySha256="a" * 64),
            lambda g: g["gradeBoundary"].update(gradeCode="primary_2"),
            lambda g: g["gradeBoundary"].update(estimatedMinutes=True),
            lambda g: g["gradeBoundary"]["learningObjectives"].append("超纲目标"),
            lambda g: g["gradeBoundary"].pop("excludedContent"),
            lambda g: g["teachingBrief"]["course"].update(skillId="unregistered"),
        )
        for mutation in mutations:
            bad = deepcopy(generation)
            mutation(bad)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_generation_grade_boundary(bad, course)
        for field in ("grade_code", "subject", "node_code", "boundary_version", "curriculum_version"):
            bad_course = {**course, field: "wrong"}
            with self.subTest(field=field), self.assertRaises(ValueError):
                grade_boundary_fields(bad_course, PROFESSIONAL_POLICY)
        for policy in (LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY, INTEGRATED_PROFESSIONAL_POLICY):
            with self.subTest(historical=policy), self.assertRaises(ValueError):
                validate_generation_grade_boundary({**generation, "professionalCreationPolicy": policy})

    def test_selection_matches_runtime_golden_plans_byte_for_byte(self):
        cases = json.loads(Path(__file__).with_name("fixtures").joinpath("mira_formal_skill_selection_v2.json").read_text())
        for case in cases:
            with self.subTest(case=case["name"]):
                raw = case["input"]
                plan = select_formal_skills(teaching_brief=raw["teachingBrief"], grade_boundary=raw["gradeBoundary"],
                                           grade_boundary_sha256=raw["gradeBoundarySha256"])
                self.assertEqual(plan, case["expected"])
                self.assertEqual(skill_selection_plan(plan), plan)

    def test_selection_rejects_forged_decisions_even_with_recomputed_plan_hash(self):
        boundary = PRIMARY_SKILL_BOUNDARIES[0].to_catalog_payload()
        plan = select_formal_skills(teaching_brief=TEACHING_BRIEF, grade_boundary=boundary,
                                   grade_boundary_sha256=canonical_sha256(boundary))
        for mutation in (lambda p: p["decisions"].pop(), lambda p: p["decisions"].reverse(),
                         lambda p: p["selectedSkillIds"].append("vocational"),
                         lambda p: p["decisions"][0].update(status="unknown"),
                         lambda p: p["decisions"][0].update(evidencePaths=["/arbitrary/title"])):
            bad = deepcopy(plan)
            mutation(bad)
            bad.pop("planSha256")
            bad["planSha256"] = canonical_sha256(bad)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                skill_selection_plan(bad)

    def test_grade_projection_does_not_open_additional_student_grades(self):
        from services.formal_student_learning_access import FORMAL_STUDENT_GRADE_CODES
        self.assertEqual(FORMAL_STUDENT_GRADE_CODES, frozenset({"primary_1"}))


if __name__ == "__main__":
    unittest.main()
