"""Verify the real shared assets and their grade/source identity without providers."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import digest, generation_brief, validate_frozen_brief
from content.textbook_introductions import public_introduction
from content.textbook_pedagogy import teaching_profile
from content.textbook_picture_guides import published_pack, validate_pack
from content.textbook_preview import preview_input
from core.errors import ApiError
from tests.test_textbook_learning import sample
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts import textbook_intro_media as operator

ROOT = Path(__file__).parents[2]


class PictureGuideTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "backend/content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json").read_text())

    def test_all_ten_guides_have_real_complete_media_and_immutable_source_identity(self):
        guides = [self.manifest["introduction"], *(u["introduction"] for u in self.manifest["units"])]
        audio, pictures = set(), set()
        for guide in guides:
            public = public_introduction(guide, manifest=self.manifest)
            media = public["presentation"]
            self.assertEqual(media["sourceContentSha256"], digest(guide))
            self.assertEqual(len(media["scenes"]), 4)
            self.assertEqual(len(media["choices"]), 3)
            for scene in media["scenes"] + media["choices"]:
                self.assertLessEqual(len(scene["caption"]), 16)
                for key in ("audio", "art"):
                    asset = ROOT / "student-web/public" / scene[key]["src"].lstrip("/")
                    self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(), scene[key]["sha256"])
                audio.add(scene["audio"]["sha256"])
                pictures.add((scene["art"]["src"], scene["art"]["panel"]))
        self.assertEqual(len(audio), 69)  # One existing closing clip is shared; unknown dispatch was never retried.
        self.assertEqual(len(pictures), 24)

    def test_media_never_attaches_to_a_different_grade_revision_or_changed_introduction(self):
        for field, value in (("gradeCode", "primary_6"), ("revisionId", "older"), ("editionId", "another-book")):
            wrong = {**self.manifest, field: value}
            self.assertNotIn("presentation", public_introduction(self.manifest["introduction"], manifest=wrong))
        changed = {**self.manifest["introduction"], "title": "changed"}
        self.assertNotIn("presentation", public_introduction(changed, manifest=self.manifest))
        first = public_introduction(self.manifest["introduction"], manifest=self.manifest)
        first["presentation"]["scenes"][0]["caption"] = "mutated"
        self.assertNotEqual(first, public_introduction(self.manifest["introduction"], manifest=self.manifest))

    def test_media_pack_rejects_tampering_even_if_presentation_hash_is_recomputed(self):
        for field, replacement in (("src", "https://example.com/voice.mp3"), ("sha256", "0" * 64), ("durationSeconds", 0)):
            bad = deepcopy(published_pack())
            guide = bad["guides"]["chinese-welcome"]
            guide["scenes"][0]["audio"][field] = replacement
            guide["presentationSha256"] = digest({k: v for k, v in guide.items() if k != "presentationSha256"})
            with self.assertRaises(ApiError):
                validate_pack(bad)

    def test_new_briefs_differ_by_grade_but_old_frozen_courses_still_validate(self):
        manifest = sample(reviewed=True)
        low = generation_brief(manifest, "u1-l1")
        high = generation_brief({**manifest, "gradeCode": "primary_6"}, "u1-l1")
        self.assertEqual(low["teachingProfile"]["readingMode"], "pre_reader")
        self.assertEqual(high["teachingProfile"]["readingMode"], "critical_reader")
        self.assertLess(low["teachingProfile"]["maxVisibleCharactersPerScene"], high["teachingProfile"]["maxVisibleCharactersPerScene"])
        self.assertNotEqual(low["contentKey"], high["contentKey"])
        legacy = deepcopy(low)
        legacy.pop("teachingProfile")
        legacy["schemaVersion"] = "mira.learning.textbook-original-generation.v1"
        legacy["promptSha256"] = "b" * 64
        legacy["contentKey"] = digest({k: v for k, v in legacy.items() if k != "contentKey"})
        self.assertEqual(validate_frozen_brief(manifest, legacy), legacy)
        self.assertEqual(validate_frozen_brief(manifest, low), low)
        prior_profile = deepcopy(low)
        prior_profile['teachingProfile'] = teaching_profile('primary_1', version=1)
        prior_profile['contentKey'] = digest({k: v for k, v in prior_profile.items() if k != 'contentKey'})
        self.assertEqual(validate_frozen_brief(manifest, prior_profile), prior_profile)
        tampered = deepcopy(low); tampered["teachingProfile"] = high["teachingProfile"]
        tampered["contentKey"] = digest({k: v for k, v in tampered.items() if k != "contentKey"})
        with self.assertRaises(ApiError):
            validate_frozen_brief(manifest, tampered)
        self.assertEqual(len({teaching_profile(f"primary_{i}")["readingMode"] for i in range(1, 7)}), 6)

    def test_new_operator_preview_receives_the_grade_constraints(self):
        manifest = json.loads((ROOT / "backend/content/textbooks/revisions/pep-chinese-g1-upper.preview.v2.json").read_text())
        preview = preview_input(manifest, "u1-l1")
        self.assertIn("pre_reader", preview["requirement"])
        self.assertEqual(preview["teachingProfile"], teaching_profile("primary_1"))
        self.assertFalse(preview["publicationAllowed"])

    def test_replaying_completed_operator_work_never_calls_the_provider(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            payload = b"saved synthetic test audio"
            (root / "saved.mp3").write_bytes(payload)
            (root / "request.json").write_text(json.dumps({"asset": {"file": "saved.mp3", "sha256": hashlib.sha256(payload).hexdigest()}}))
            runtime = Mock()
            config = SimpleNamespace(OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100", INTERNAL_API_TOKEN="synthetic-test")
            with patch.object(operator, "ASSETS", root), patch.object(operator, "WORK", root), \
                    patch.object(operator.AppConfig, "from_env", return_value=config), \
                    patch.object(operator, "OpenMaicFullRuntimeClient", return_value=runtime), \
                    patch.object(operator, "segments", return_value=[({"id": "test"}, "scenes", 0, ["image", 0, "提示", "讲解"], "request")]):
                operator.synthesize({}, Mock())
            self.assertEqual(runtime.mock_calls, [])

    def test_a_lost_operator_receipt_does_not_authorize_a_second_paid_dispatch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "request.json").write_text(json.dumps({"state": "dispatching"}))
            runtime = Mock()
            runtime.get_formal_audio_tts.side_effect = OpenMaicFullRuntimeError("not_found", "Not found", status_code=404)
            config = SimpleNamespace(OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100", INTERNAL_API_TOKEN="synthetic-test")
            with patch.object(operator, "ASSETS", root), patch.object(operator, "WORK", root), \
                    patch.object(operator.AppConfig, "from_env", return_value=config), \
                    patch.object(operator, "OpenMaicFullRuntimeClient", return_value=runtime), \
                    patch.object(operator, "segments", return_value=[({"id": "test"}, "scenes", 0, ["image", 0, "提示", "讲解"], "request")]):
                with self.assertRaisesRegex(RuntimeError, "Uncertain prior dispatch"):
                    operator.synthesize({}, Mock())
            runtime.start_formal_audio_tts.assert_not_called()
