"""No network/provider/database configuration is loaded by these checks."""
import json
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import wave
from unittest.mock import Mock

from content.textbook_catalog import generation_brief
from content.textbook_preview import blueprint_prompt, lesson_blueprint, preview_checks, preview_input, preview_media
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository
from services.textbook_learning_service import TextbookLearningService
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_audio import narrate_preview
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from tests.test_textbook_learning import IsolatedDatabase


def scene_content(kind):
    reference = preview_media()["assets"][0]["mediaPath"]
    if kind == "quiz":
        return {"questions": [{}] * 6}
    if kind == "interactive":
        return {"html": f'<img src="{reference}" />'}
    return {"canvas": {"elements": [{"type": "image", "src": reference}]}}


class TextbookPreviewTest(unittest.TestCase):
    def setUp(self):
        self.db = IsolatedDatabase(("082_fixed_textbook_learning.sql", "083_textbook_course_previews.sql", "087_learning_course_reuse.sql"))
        self.addCleanup(self.db.raw.close)
        self.repo = TextbookRepository(self.db)
        self.manifest = json.loads((Path(__file__).parents[1] / "content/textbooks/revisions/pep-chinese-g1-upper.preview.v2.json").read_text())
        TextbookLearningService(self.repo).import_manifest(self.manifest)
        self.runtime = Mock(base_url="http://127.0.0.1:3100")
        self.job = SimpleNamespace(job_id="job-a", status="running", step="generating_scenes", progress=40, scenes_count=2, classroom_id=None)
        self.runtime.start_generation.return_value = self.job
        self.runtime.get_generation_job.return_value = self.job
        self.service = TextbookPreviewService(self.repo, self.runtime)

    def prepare(self):
        return self.service.prepare(self.manifest["editionId"], self.manifest["revisionId"], "u1-l1")["previewKey"]

    def test_continuous_unit_has_distinct_scopes_and_stops_before_billing_without_art(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        for node, count in [('u1-l2', 7), ('u1-l3', 7), ('u1-l4', 8), ('u1-l5', 5)]:
            blueprint = lesson_blueprint(manifest, node)
            self.assertEqual(blueprint_prompt(blueprint)['expectedQuestionCount'], count)
            self.assertFalse(blueprint['generationReady'])
            with self.assertRaises(ApiError) as error:
                preview_input(manifest, node)
            self.assertEqual(error.exception.code, 'textbook_preview_media_required')
        self.runtime.start_generation.assert_not_called()
        self.assertIsNone(lesson_blueprint({**manifest, 'revisionId': 'another-version'}, 'u1-l2'))

    def test_preview_uses_the_lesson_question_count(self):
        classroom = {'scenes': [{'type': 'quiz', 'content': {'questions': [{}] * 7}}]}
        self.assertNotIn('question_count_mismatch', preview_checks(classroom, 1, expected_question_count=7)['issues'])
        self.assertIn('question_count_mismatch', preview_checks(classroom, 1, expected_question_count=8)['issues'])

    def test_preview_does_not_approve_publication_or_dispatch_on_prepare(self):
        key = self.prepare()
        self.assertEqual(key, self.prepare())
        self.runtime.start_generation.assert_not_called()
        self.assertFalse(preview_input(self.manifest, "u1-l1")["publicationAllowed"])
        with self.assertRaises(ApiError):
            generation_brief(self.manifest, "u1-l1")
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)
        with self.assertRaises(ApiError):
            preview_input(self.manifest, "u1-l2")

    def test_repeated_start_and_poll_never_create_a_second_job(self):
        key = self.prepare()
        for _ in range(3):
            self.service.start(key)
            self.service.poll(key)
        self.runtime.start_generation.assert_called_once()

    def test_freeze_keeps_audio_and_reuses_an_immutable_preview_url(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        scenes = [{"id": f"scene-{i}", "type": t, "actions": [{"type": "speech", "text": "天", "audioId": str(i), "audioUrl": "/audio/a.wav"}],
                   "content": scene_content(t)}
                  for i, t in enumerate(["slide"] * 5 + ["interactive", "quiz", "slide"])]
        documents = {"class-a": {"id": "class-a", "stage": {"id": "class-a"}, "scenes": scenes}}
        def read(classroom_id):
            if classroom_id not in documents:
                raise OpenMaicFullRuntimeError("not_found", "Not found", status_code=404)
            return deepcopy(documents[classroom_id])
        self.runtime.get_classroom.side_effect = read
        self.runtime.save_preview_classroom.side_effect = lambda c: documents.update({c["id"]: deepcopy(c)})
        self.service.poll(key)
        frozen = self.service.freeze(key)
        self.assertIn("/classroom/tbprev_", frozen["previewUrl"])
        self.assertEqual(frozen, self.service.freeze(key))
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_generation.assert_called_once()
        options = self.runtime.start_generation.call_args.kwargs
        self.assertFalse(options["enable_web_search"])
        self.assertFalse(options["enable_image_generation"])
        self.assertFalse(options["enable_video_generation"])
        self.assertFalse(options["enable_tts"])

    def test_unknown_dispatch_and_crashed_claim_never_retry(self):
        key = self.prepare()
        self.runtime.start_generation.side_effect = TimeoutError()
        with self.assertRaises(ApiError):
            self.service.start(key)
        self.assertEqual(self.service.start(key)["status"], "dispatch_unknown")
        self.runtime.start_generation.assert_called_once()
        self.db.execute("UPDATE learning_textbook_course_previews SET status='dispatching'")
        self.assertEqual(self.service.start(key)["status"], "dispatching")
        self.runtime.start_generation.assert_called_once()

    def test_failed_job_does_not_retry_and_incomplete_output_is_not_ready(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status = "failed"
        self.assertEqual(self.service.poll(key)["status"], "failed")
        self.assertEqual(self.service.start(key)["status"], "failed")
        self.runtime.start_generation.assert_called_once()

    def test_success_snapshots_classroom_and_reuses_without_native_calls(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        scenes = [{"type": t, "actions": [{"type": "speech", "text": "天", "audioId": str(i), "audioUrl": "/audio/a.wav"}],
                   "content": scene_content(t)}
                  for i, t in enumerate(["slide"] * 5 + ["interactive", "quiz", "slide"])]
        self.runtime.get_classroom.return_value = {"id": "class-a", "stage": {"id": "class-a"}, "scenes": scenes}
        ready = self.service.poll(key)
        self.assertEqual(ready["status"], "preview_ready")
        self.assertFalse(ready["publicationAllowed"])
        self.assertEqual(ready, self.service.poll(key))
        self.assertEqual(ready, self.service.start(key))
        self.runtime.get_classroom.assert_called_once()
        self.runtime.start_generation.assert_called_once()

    def test_incomplete_output_and_changed_origin_are_rejected(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        self.runtime.get_classroom.return_value = {"id": "class-a", "stage": {"id": "class-a"}, "scenes": []}
        self.assertEqual(self.service.poll(key)["status"], "review_required")
        self.runtime.base_url = "http://127.0.0.1:4100"
        with self.assertRaises(ApiError):
            self.service.start(key)

    def test_text_only_or_placeholder_images_cannot_pass_picture_lesson_review(self):
        scenes = [{"type": t, "actions": [{"type": "speech", "text": "天", "audioId": str(i), "audioUrl": "/audio/a.wav"}],
                   "content": scene_content(t)} for i, t in enumerate(["slide"] * 5 + ["interactive", "quiz", "slide"])]
        self.assertEqual(preview_checks({"scenes": scenes}, media_manifest=preview_media())["issues"], [])
        scenes[0]["content"]["canvas"]["elements"][0]["src"] = "generated_image_placeholder"
        scenes[5]["content"] = {"html": "<p>请看插画</p>"}
        issues = preview_checks({"scenes": scenes}, media_manifest=preview_media())["issues"]
        self.assertIn("original_teaching_image_missing", issues)
        self.assertIn("interactive_teaching_image_missing", issues)

    def test_durable_segment_audio_reuses_receipts_and_stops_ambiguous_attempt(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        classroom = {"id": "class-a", "stage": {"id": "class-a"}, "scenes": [{"id": "scene-a", "order": 1, "type": "slide",
                     "actions": [{"id": "action-a", "type": "speech", "text": "天空的天。"}], "content": {}}]}
        self.runtime.get_classroom.side_effect = lambda _: deepcopy(classroom)
        self.runtime.save_preview_classroom.side_effect = lambda value: classroom.update(deepcopy(value))
        self.service.poll(key)
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
            wav.writeframes(b"\0\0" * 2400)
        bytes_ = audio.getvalue()
        receipts = {}
        def read(request_id):
            if request_id not in receipts:
                raise OpenMaicFullRuntimeError("not_found", "Not found", status_code=404)
            return receipts[request_id]
        def start(**kwargs):
            receipt = {"requestId": kwargs["request_id"], "status": "succeeded", "audioSha256": hashlib.sha256(bytes_).hexdigest()}
            receipts[kwargs["request_id"]] = receipt
            return receipt
        self.runtime.get_formal_audio_tts.side_effect = read
        self.runtime.start_formal_audio_tts.side_effect = start
        self.runtime.download_formal_audio_tts.return_value = bytes_
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "class-a.json"
            source.write_text(json.dumps(classroom))
            result = narrate_preview(self.service, key, root)
            self.assertEqual(result["result"]["audioSeconds"], 0.1)
            source.write_text(json.dumps(classroom))
            narrate_preview(self.service, key, root)
            self.runtime.start_formal_audio_tts.assert_called_once()
            self.runtime.download_formal_audio_tts.assert_called_once()
            # An ambiguous durable receipt must never be replaced by a POST.
            for receipt in receipts.values():
                receipt["status"] = "ambiguous"
            result = narrate_preview(self.service, key, root)
            self.assertEqual(result["result"]["audioStopCode"], "textbook_preview_audio_ambiguous")
            self.runtime.start_formal_audio_tts.assert_called_once()


if __name__ == "__main__":
    unittest.main()
