import unittest

from core.config import LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from integrations.openmaic_question_adapter import OpenMaicQuestionPhaseAdapter
from repositories.learning_catalog_repository import LearningCatalogRepository
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_curriculum_preparation_contract import (
    PREPARATION_SCHEMA_VERSION,
    TARGET_SCHEMA_V1,
    TARGET_SCHEMA_V2,
    build_preparation_target,
    preparation_target_fingerprint,
)


class LearningCurriculumPreparationContractTest(unittest.TestCase):
    def test_primary_one_target_has_three_subjects_and_thirty_courses(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(target["schemaVersion"], TARGET_SCHEMA_V2)
        self.assertEqual(TARGET_SCHEMA_V2, "mira.learning.preparation-target.v2")
        self.assertEqual(PREPARATION_SCHEMA_VERSION, "mira.learning.preparation.v1")
        self.assertEqual(
            target["contentGenerationContractVersion"],
            "mira.learning.question-contract.v2",
        )
        self.assertEqual(
            target["contentProviderProfileContractVersion"],
            "mira.learning.question-provider-profile.v106-deepseek-professional-video",
        )
        self.assertEqual(
            target["contentValidationContractVersion"],
            "mira.learning.primary-1-content-validation.v1",
        )
        self.assertEqual(target["subjects"], ["chinese", "math", "english"])
        self.assertEqual(target["variantsPerBoundary"], 3)
        self.assertEqual(target["boundaryCount"], 10)
        self.assertEqual(target["totalCourseCount"], 30)
        self.assertEqual(
            target["subjectTargets"],
            {
                "chinese": {"boundaryCount": 4, "totalCourseCount": 12},
                "math": {"boundaryCount": 3, "totalCourseCount": 9},
                "english": {"boundaryCount": 3, "totalCourseCount": 9},
            },
        )

    def test_other_primary_grades_have_twenty_seven_courses(self):
        for grade in range(2, 7):
            target = build_preparation_target(f"primary_{grade}")
            self.assertEqual(target["schemaVersion"], TARGET_SCHEMA_V2)
            self.assertEqual(TARGET_SCHEMA_V1, "mira.learning.preparation-target.v1")
            self.assertEqual(target["boundaryCount"], 9)
            self.assertEqual(target["totalCourseCount"], 27)
            self.assertEqual(
                target["subjectTargets"],
                {
                    "chinese": {"boundaryCount": 3, "totalCourseCount": 9},
                    "math": {"boundaryCount": 3, "totalCourseCount": 9},
                    "english": {"boundaryCount": 3, "totalCourseCount": 9},
                },
            )

    def test_formal_teacher_targets_and_runtime_policy_are_sample_independent(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(
            [target["teacherTargets"][subject]["teacherProfile"]["id"] for subject in target["subjects"]],
            ["mira_chinese_gentle", "mira_math_clear", "mira_english_standard"],
        )
        expected_voices = {
            "chinese": ("小语老师", "female", "Serena", "zh-CN"),
            "math": ("小数老师", "male", "Ethan", "zh-CN"),
            "english": ("Mia 老师", "female", "Jennifer", "en-US"),
        }
        for subject, (teacher, gender, voice_id, language) in expected_voices.items():
            voice = target["teacherTargets"][subject]["formalVoiceSelection"]
            self.assertEqual(voice["teacherName"], teacher)
            self.assertEqual(voice["teacherGender"], gender)
            self.assertEqual(voice["voiceGender"], gender)
            self.assertEqual(voice["voiceId"], voice_id)
            self.assertEqual(voice["languageCode"], language)
            self.assertEqual(voice["tts"], {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "fallbackAllowed": False,
            })
            self.assertEqual(voice["asr"], {
                "providerId": "qwen-asr",
                "modelId": "qwen3-asr-flash",
                "fallbackAllowed": False,
            })
        self.assertEqual(
            target["formalAudioContracts"],
            {
                "audio": "mira.learning.formal-qwen-audio.v1",
                "pcmValidation": "mira.learning.formal-pcm-validation.v1",
                "asrRoundTrip": "mira.learning.formal-qwen-asr-roundtrip.v1",
                "expectedSegmentCount": {
                    "derivedFrom": "runtime_speech_action_count",
                    "min": 1,
                    "max": 240,
                },
            },
        )
        self.assertNotIn("sampleRuntimeReadiness", target)
        self.assertNotIn("asrPolicy", target)
        self.assertNotIn("dialoguePolicy", target)
        self.assertNotIn("ttsPolicy", target)
        self.assertNotIn("lessonPackageCompilerVersion", target)
        self.assertEqual(
            target["formalRuntimePolicy"],
            {
                "runtimeVersion": OpenMaicFullRuntimeClient.FORMAL_RUNTIME_VERSION,
                "runtimeContractVersion": (
                    OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
                ),
                "upstreamIdempotencyKey": "runtimeRequestId",
                "queryByRuntimeRequestId": True,
                "speechAudioGenerated": True,
                "enableTTS": False,
                "enableWebSearch": True,
                "coursewareAuthority": dict(
                    OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
                ),
                "professionalModelPolicy": dict(
                    OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_MODEL_POLICY
                ),
                "professionalCreationPolicy": dict(
                    OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_CREATION_POLICY
                ),
            },
        )
        self.assertEqual(
            target["formalRuntimePackageContract"],
            {
                "schemaVersion": "mira.learning.formal-runtime-candidate-package.v1",
                "compilerVersion": "mira.formal-runtime-package.v1",
                "sourceSchemaVersion": (
                    "mira.openmaic.formal-runtime-package-source.v1"
                ),
                "teachingBriefSchemaVersion": (
                    "mira.learning.formal-runtime-teaching-brief.v1"
                ),
            },
        )

    def test_fingerprint_is_canonical_and_contract_sensitive(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(
            target["formalRuntimeClassroomContract"]["scenePlanning"],
            {
                "mode": "adaptive",
                "authority": "openmaic_professional_agent",
                "exactCountRequired": False,
                "allowedSceneTypes": ["slide", "quiz", "interactive", "pbl"],
                "requiredSceneTypes": ["slide", "quiz", "interactive"],
                "defaultDurationMinutes": {"min": 15, "max": 30},
                "scenesPerMinute": {"min": 1, "max": 2},
                "maxSceneCount": 60,
            },
        )
        self.assertEqual(
            target["formalRuntimeClassroomContract"]["roster"],
            {"teacherCount": 1, "peerCount": 4},
        )
        self.assertTrue(
            target["formalRuntimeClassroomContract"]["speechRequiredForEveryScene"]
        )
        self.assertEqual(
            target["formalRuntimeClassroomContract"]["speechActions"],
            {
                "perScene": {"min": 1, "max": 20},
                "total": {"min": 1, "max": 240},
                "interactiveSpotlightRequired": False,
            },
        )
        self.assertEqual(
            target["formalRuntimeClassroomContract"]["slideSpotlight"],
            {
                "minimumPerSlide": 1,
                "targetMustBeRenderable": True,
                "focusExplanationSequenceRequired": True,
                "consecutiveSpotlightsAllowed": True,
            },
        )
        self.assertEqual(
            target["formalRuntimeClassroomContract"]["distinctPeerDiscussions"],
            2,
        )
        first = preparation_target_fingerprint(target)
        reordered = dict(reversed(list(target.items())))
        self.assertEqual(first, preparation_target_fingerprint(reordered))
        changed = {**target, "fullRuntimeContractVersion": "mira.openmaic.formal-classroom.v2"}
        self.assertNotEqual(first, preparation_target_fingerprint(changed))
        changed_voice = {
            **target,
            "teacherTargets": {
                **target["teacherTargets"],
                "math": {
                    **target["teacherTargets"]["math"],
                    "formalVoiceSelection": {
                        **target["teacherTargets"]["math"]["formalVoiceSelection"],
                        "voiceId": "Serena",
                    },
                },
            },
        }
        self.assertNotEqual(first, preparation_target_fingerprint(changed_voice))
        for field in (
            "schemaVersion",
            "compilerVersion",
            "sourceSchemaVersion",
            "teachingBriefSchemaVersion",
        ):
            changed_package = {
                **target,
                "formalRuntimePackageContract": {
                    **target["formalRuntimePackageContract"],
                    field: f"changed-{field}",
                },
            }
            self.assertNotEqual(
                first, preparation_target_fingerprint(changed_package)
            )

    def test_primary_one_sealed_dataset_and_target_fingerprint_are_pinned(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(
            target["contentValidationDatasetSha256"],
            "1ca7707b75f9d55c775201676dfc234c496e1655b048494517ac2aea8736b63d",
        )
        simple_sentences = next(
            item
            for item in target["boundaries"]
            if item["skillId"] == "simple_sentences"
        )
        self.assertEqual(
            simple_sentences["boundaryVersion"],
            "mira.primary.2026-fall.v1:simple_sentences:afab3e2d8a53d220",
        )
        self.assertEqual(
            preparation_target_fingerprint(target),
            "d526af0146e824185c7eedf0e0b0eba3c195d0f17247c7297525205b3428d0d3",
        )

    def test_v95_provider_phase_budget_fits_every_formal_deadline(self):
        required_phase_budget_ms = OpenMaicQuestionPhaseAdapter(
            provider_timeout_ms=300_000,
            process_timeout_seconds=305.0,
        ).required_phase_budget_ms
        deadlines = {
            "planLease": (
                LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS * 1000
            ),
            "planStage": (
                LearningCurriculumPreparationRepository
                .FORMAL_V2_PROVIDER_STAGE_DEADLINE_MS
            ),
            "contentWorkUnit": LearningCatalogRepository.FORMAL_CONTENT_WORK_UNIT_MS,
            "providerAttempt": (
                LearningCatalogRepository.FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS
            ),
        }

        self.assertEqual(required_phase_budget_ms, 315_000)
        self.assertTrue(all(value >= 360_000 for value in deadlines.values()))
        self.assertGreaterEqual(min(deadlines.values()), required_phase_budget_ms)
        self.assertEqual(
            LearningCatalogRepository.FORMAL_CONTENT_WORK_UNIT_MS,
            600_000,
        )
        self.assertEqual(
            LearningCurriculumPreparationRepository._claim_stage_deadline_ms(
                is_v2=True,
                next_stage="planning",
                deadlines={"planning": 120_000},
            ),
            360_000,
        )
        self.assertEqual(
            LearningCurriculumPreparationRepository._claim_stage_deadline_ms(
                is_v2=True,
                next_stage="generating_content",
                deadlines={"generating_content": 120_000},
            ),
            360_000,
        )
        self.assertEqual(
            LearningCatalogRepository._formal_content_work_deadline(
                now=1_000,
                outer_deadline=1_801_000,
            ),
            601_000,
        )

    def test_non_primary_grade_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported primary grade"):
            build_preparation_target("kindergarten_middle")
