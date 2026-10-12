from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest

from content.teacher_presentations import public_teacher_payload, teacher_presentation
from content.teacher_profiles import (TEACHER_PROFILES, SCIENCE_TEACHER_PROFILES,
    get_teacher_profile, get_formal_runtime_teacher_contract, list_teacher_profiles)
from services.learning_teacher_library_service import LearningTeacherLibraryService
from services.learning_media_materialization_service import LearningMediaMaterializationError


class MemoryTeacherRepository:
    def __init__(self):
        self.profiles = {(p.profile_id, p.version): p.to_storage_payload() for p in TEACHER_PROFILES}
        self.original = deepcopy(self.profiles)
        self.added = []
        self.preference = None

    @contextmanager
    def transaction(self):
        yield None

    def sync_teacher_profile(self, conn, *, profile, now):
        key = (profile.profile_id, profile.version)
        payload = profile.to_storage_payload()
        if key in self.profiles:
            assert self.profiles[key] == payload
        else:
            self.added.append(key)
            self.profiles[key] = payload

    def child_belongs_to_family(self, conn, **scope):
        return scope == {"family_id": "family", "child_id": "child"}

    def get_teacher_preference(self, conn, **scope):
        return self.preference

    def set_teacher_preference(self, conn, **value):
        self.preference = {"child_id": value["child_id"], "subject": value["subject"],
            "teacher_profile_id": value["profile_id"], "teacher_profile_version": value["profile_version"],
            "updated_at": value["now"]}
        return self.preference


class TeacherPresentationTest(unittest.TestCase):
    def test_formal_portraits_share_exact_bytes_on_both_surfaces_and_preserve_identities(self):
        root = Path(__file__).resolve().parents[2]
        source = root / "backend/content/teacher_presentations.v1.json"
        native = root / "openmaic-runtime/.runtime/OpenMAIC"
        self.assertEqual(source.read_bytes(), (native / "lib/mira/teacher-presentations.v1.json").read_bytes())
        registry = json.loads(source.read_bytes())
        self.assertEqual(len(registry["items"]), 4)
        for item in registry["items"]:
            key = item["teacherProfile"]
            profile = get_teacher_profile(key["id"], key["version"])
            self.assertEqual(profile.content_hash, key["contentHash"])
            original = profile.to_storage_payload()
            result = public_teacher_payload(profile)
            self.assertEqual(profile.to_storage_payload(), original)
            self.assertEqual((result["id"], result["version"]), (profile.profile_id, profile.version))
            for directory in (root / "student-web/public", native / "public"):
                self.assertEqual(hashlib.sha256((directory / item["avatarPath"].lstrip("/")).read_bytes()).hexdigest(), item["assetSha256"])
            self.assertEqual(result["avatarPath"], item["avatarPath"])
            self.assertNotIn("voicePrompt", result)
        # Existing runtime/audio contracts remain the original frozen values.
        self.assertEqual(get_formal_runtime_teacher_contract("science")["runtime"]["avatar"], "/avatars/teacher-2.png")
        self.assertEqual(len(list_teacher_profiles()), 3)

    def test_unknown_version_changed_hash_and_same_name_never_gain_a_portrait(self):
        profile = get_teacher_profile("mira_science_inquiry", 1)
        for candidate in (replace(profile, version=2), replace(profile, voice_prompt="changed"),
                          replace(profile, profile_id="other")):
            self.assertIsNone(teacher_presentation(candidate))
            self.assertEqual(public_teacher_payload(candidate), candidate.to_public_payload())
        presentation = teacher_presentation(profile)
        presentation["teacherProfile"]["id"] = "changed"
        self.assertEqual(teacher_presentation(profile)["teacherProfile"]["id"], profile.profile_id)

    def test_library_has_four_formal_teachers_and_sync_is_additive_only(self):
        repo = MemoryTeacherRepository()
        library = LearningTeacherLibraryService(repo)
        result = library.list_teachers()
        self.assertEqual(result["registryVersion"], "mira.teacher-registry.v3")
        self.assertEqual([p["subject"] for p in result["items"]], ["chinese", "math", "english", "science"])
        self.assertEqual([p["version"] for p in result["items"]], [2, 2, 2, 1])
        self.assertEqual(repo.added, [(SCIENCE_TEACHER_PROFILES[0].profile_id, 1)])
        for key, original in repo.original.items():
            self.assertEqual(repo.profiles[key], original)
        library.list_teachers()
        self.assertEqual(len(repo.added), 1)

    def test_science_filter_preference_and_family_scope_use_existing_teacher_identity(self):
        repo = MemoryTeacherRepository()
        library = LearningTeacherLibraryService(repo)
        result = library.list_teachers(subject="science", family_id="family", child_id="child")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["avatarPath"], "/teachers/ke-science-v1.png")
        saved = library.set_teacher_preference(subject="science", family_id="family", child_id="child",
            teacher_profile_id="mira_science_inquiry", teacher_profile_version=1)
        self.assertEqual(saved["teacher"]["id"], "mira_science_inquiry")
        self.assertEqual(library.list_teachers(subject="science", family_id="family", child_id="child")["selected"],
            {"id": "mira_science_inquiry", "version": 1})
        with self.assertRaises(LearningMediaMaterializationError):
            library.list_teachers(subject="science", family_id="wrong", child_id="child")
        with self.assertRaises(LearningMediaMaterializationError):
            library.set_teacher_preference(subject="science", family_id="family", child_id="child",
                teacher_profile_id="mira_math_clear", teacher_profile_version=2)
