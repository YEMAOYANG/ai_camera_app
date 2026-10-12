from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import digest
from content.textbook_deepseek_release import CONTRACT, STAGES, validate_new_authoring, validate_new_release_admission
from core.errors import ApiError
from services.textbook_activity_publication_service import TextbookActivityPublicationService
from tests.test_textbook_deepseek_authoring import fixture


class DeepSeekReleaseTests(unittest.TestCase):
    def test_directly_authored_content_cannot_enter_new_publication(self):
        with self.assertRaises(ApiError):
            validate_new_authoring({"activityDesign": {"authoringMode": "structured_local_original"}}, {}, {})
        with self.assertRaises(ApiError):
            validate_new_release_admission({}, {})
        repository = Mock()
        service = TextbookActivityPublicationService(repository, "http://127.0.0.1:3100", "/private/tmp")
        with self.assertRaises(ApiError):
            service.publish({"frozen": {}, "course": {}, "review": {}})
        repository.transaction.assert_not_called()

    def test_exact_provider_text_and_goal_review_are_required(self):
        source, blueprint = fixture()
        source["manifestSha256"] = "f" * 64
        with tempfile.TemporaryDirectory() as tmp, patch("content.textbook_deepseek_release.ROOT", Path(tmp).resolve()):
            request = {"taskId": source["taskId"], "source": source, "providerId": "deepseek",
                       "payload": {"model": "deepseek-v4-pro"}}
            request["requestSha256"] = digest(request)
            response = {"id": "synthetic-provider-response", "model": "deepseek-v4-pro",
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(blueprint)}}]}
            proof = {"schemaVersion": CONTRACT, "blueprintSha256": digest(blueprint)}
            for name, value in [("request", request), ("response", response)]:
                path = Path(tmp) / (name + ".json")
                path.write_text(json.dumps(value))
                proof[name + "Path"] = str(path)
                proof[name + "ByteSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            proof["cueOrigins"] = [{"cueId": "c1", "sceneId": "scene1", "activityId": "a1",
                                    "method": "deepseek_exact", "pointer": "/activities/0/teacherText"}]
            cues = {"schemaVersion": "mira.interactive.narration-cues.v1", "cues": [
                {"id": "c1", "text": blueprint["activities"][0]["teacherText"]}]}
            room = {"scenes": [{"id": "scene1", "type": "interactive", "content": {
                "html": '<script id="mira-narration-cues" type="application/json">' + json.dumps(cues) + '</script>'}}]}
            original = {"taskId": source["taskId"], "binding": source["binding"], "manifestSha256": source["manifestSha256"],
                "activityDesign": {"deepseekAuthoring": proof}, "reviewedLessonScope": {
                    "activityGoalIds": source["activityGoalIds"], "outstandingGoalIds": source["outstandingGoalIds"]}}
            depth = {"schemaVersion": CONTRACT, "status": "passed", "blueprintSha256": digest(blueprint),
                     "sourceSha256": digest(room), "unresolvedFindings": [], "reviewer": "Synthetic test only",
                     "outstandingGoalIds": source["outstandingGoalIds"], "goalEvidence": [{"goalId": "meaning",
                         "basis": "Fixture binds real references, not a semantic approval of a real lesson.",
                         **{s: [{"cueId": "c1", "sceneId": "scene1"}] for s in STAGES}}]}
            review = {"teachingDepthReview": depth}
            admission = validate_new_authoring(original, room, review)
            self.assertEqual(admission["responseId"], response["id"])
            validate_new_release_admission({"deepseekAuthoringAdmissionSha256": digest(admission), "sourceSha256": digest(room)},
                {**review, "deepseekAuthoringAdmission": admission})
            for mutation in ("local_text", "wrong_pointer", "missing_cue", "missing_phase", "unresolved", "forged_model"):
                other, other_room, other_review = deepcopy(original), deepcopy(room), deepcopy(review)
                if mutation == "local_text":
                    other_room["scenes"][0]["content"]["html"] = other_room["scenes"][0]["content"]["html"].replace(
                        json.dumps(cues), json.dumps({**cues, "cues": [{"id": "c1", "text": "不是原始模型讲解"}]}))
                elif mutation == "wrong_pointer":
                    other["activityDesign"]["deepseekAuthoring"]["cueOrigins"][0]["pointer"] = "/activities/1/teacherText"
                elif mutation == "missing_cue":
                    other["activityDesign"]["deepseekAuthoring"]["cueOrigins"] = []
                elif mutation == "missing_phase":
                    other_review["teachingDepthReview"]["goalEvidence"][0]["transfer"] = []
                elif mutation == "unresolved":
                    other_review["teachingDepthReview"]["unresolvedFindings"] = ["not reviewed"]
                else:
                    other["activityDesign"]["deepseekAuthoring"]["responseByteSha256"] = "0" * 64
                with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                    validate_new_authoring(other, other_room, other_review)


if __name__ == "__main__":
    unittest.main()
