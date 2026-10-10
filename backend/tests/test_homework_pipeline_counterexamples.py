"""Failure-injection audits use temporary SQLite/assets and fake provider replies.

These cases specify recovery behavior for concrete partial-paper and storage
failures, rather than replaying live submissions or making paid requests.
"""
import io
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from PIL import Image, ImageDraw

from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_math import check_item
from services.homework_service import parsed
from tests import test_homework_analysis as fixtures


POLICY = json.loads((Path(__file__).parents[1] / "content/homework_analysis_policy.v1.json").read_text())


class HomeworkNonterminatingDivisionAuditTests(TestCase):
    def test_decimal_parser_shortcuts_do_not_turn_unclear_ocr_strings_into_correct_answers(self):
        for answer in ("0_5", "5_", "_5", "0__5", "0 5", "5\n0", "0,5", "NaN", "Infinity", "Ⅳ", "²"):
            with self.subTest(answer=answer):
                result = check_item({
                    "prompt": "3+2", "studentAnswer": answer, "type": "arithmetic",
                    "confidence": 0.99, "annotationAmbiguous": False, "region": {"x": .1, "y": .1, "width": .5, "height": .1},
                }, grade="primary_3", subject="math", policy=POLICY)
                self.assertEqual(result["status"], "pending")

    def test_standard_decimal_signs_unicode_decimal_digits_and_scientific_values_remain_valid(self):
        for answer in ("5", "+5", "5.", "5.0", "0.5e1", "5E+0", " 5 ", "５", "٥"):
            with self.subTest(answer=answer):
                result = check_item({
                    "prompt": "3+2", "studentAnswer": answer, "type": "arithmetic",
                    "confidence": 0.99, "annotationAmbiguous": False, "region": {"x": .1, "y": .1, "width": .5, "height": .1},
                }, grade="primary_3", subject="math", policy=POLICY)
                self.assertEqual(result["status"], "correct")

    def test_rounded_inverse_multiplication_does_not_make_repeating_decimal_supported(self):
        for prompt in ("2/3", "6/7", "1/7", "1/6", "2/6", "1/3", "0.1/0.3", "1÷0.7"):
            with self.subTest(prompt=prompt):
                result = check_item({
                    "prompt": prompt, "studentAnswer": "0.1", "type": "arithmetic",
                    "confidence": 0.99, "annotationAmbiguous": False, "region": {"x": .1, "y": .1, "width": .5, "height": .1},
                }, grade="primary_3", subject="math", policy=POLICY)
                self.assertEqual(result["status"], "unsupported")
                self.assertIsNone(result["answerMode"])
                self.assertEqual(result["voiceTexts"], {})
                self.assertIsNone(result["knowledgeId"])
                self.assertIsNone(result["expectedAnswer"])

    def test_reduced_fraction_factors_allow_exact_terminating_answers(self):
        cases = (("1/8", "0.125"), ("3/6", "0.5"), ("6/3", "2"),
                 ("0.1/0.2", "0.5"), ("1÷0.8", "1.25"), ("0/3", "0"),
                 ("9999.999/8388.608", "1.19209277629852294921875"))
        for prompt, answer in cases:
            with self.subTest(prompt=prompt):
                result = check_item({
                    "prompt": prompt, "studentAnswer": answer, "type": "arithmetic",
                    "confidence": 0.99, "annotationAmbiguous": False, "region": {"x": .1, "y": .1, "width": .5, "height": .1},
                }, grade="primary_3", subject="math", policy=POLICY)
                self.assertEqual(result["status"], "correct")
                self.assertEqual(result["expectedAnswer"], answer)
                self.assertEqual(result["answerMode"], "numeric")

    def test_zero_denominator_and_negative_result_still_have_no_assessment_or_voice(self):
        for prompt in ("1/0", "0÷0", "2-5"):
            with self.subTest(prompt=prompt):
                result = check_item({
                    "prompt": prompt, "studentAnswer": "0", "type": "arithmetic",
                    "confidence": 0.99, "annotationAmbiguous": False, "region": {"x": .1, "y": .1, "width": .5, "height": .1},
                }, grade="primary_3", subject="math", policy=POLICY)
                self.assertEqual(result["status"], "unsupported")
                self.assertEqual(result["voiceTexts"], {})
                self.assertIsNone(result["knowledgeId"])


class HomeworkPipelineCounterexampleTests(TestCase):
    create = fixtures.HomeworkTest.create
    upload = fixtures.HomeworkTest.upload
    ready = fixtures.HomeworkTest.ready

    def setUp(self):
        fixtures.HomeworkTest.setUp(self)

    def response(self, *, valid=True):
        text = json.dumps({"pageReadable": True, "items": [self.raw]}) if valid else '{"pageReadable":true,"items":['
        return AiVisionResponse(text, "fixture", "fixture-vision")

    def two_pages(self):
        submission = self.upload(self.create())
        # Distinct content avoids legitimately reusing the first page's reply.
        image = Image.open(io.BytesIO(fixtures.picture())).convert("RGB")
        ImageDraw.Draw(image).rectangle((80, 950, 700, 970), fill="black")
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        submission = self.upload(submission, key="page2", body=image_bytes.getvalue())
        self.service.analyze("parent-a", submission["id"], {"revision": submission["revision"]})
        return submission

    def test_repeating_decimal_is_not_recorded_as_child_mistake_or_given_teacher_audio(self):
        self.db.execute("UPDATE children SET grade_code='primary_3' WHERE id='child-a'")
        self.db.raw.commit()
        self.raw.update(prompt="2/3", studentAnswer="0.667")
        submission = self.upload(self.create())
        self.service.analyze("parent-a", submission["id"], {"revision": submission["revision"]})
        result = self.service.process_next()
        self.assertTrue(result["ok"])
        detail = self.service.get("parent-a", submission["id"])["submission"]
        self.assertEqual(detail["items"][0]["status"], "unsupported")
        self.assertIsNone(detail["items"][0]["knowledgeId"])
        self.assertFalse(detail["items"][0]["readyForStudent"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM learning_answer_events").fetchone()["n"], 0)
        self.transport.assert_not_called()

    def test_underscored_ocr_answer_is_not_recorded_as_correct_work(self):
        self.raw.update(studentAnswer="0_5")
        submission = self.upload(self.create())
        self.service.analyze("parent-a", submission["id"], {"revision": submission["revision"]})
        self.assertTrue(self.service.process_next()["ok"])
        detail = self.service.get("parent-a", submission["id"])["submission"]
        self.assertEqual(detail["items"][0]["status"], "pending")
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM learning_answer_events").fetchone()["n"], 0)
        self.transport.assert_not_called()

    def test_duplicate_reading_does_not_create_duplicate_mistake_evidence_or_remove_reliable_sibling(self):
        sibling = {**self.raw, "region": {"x": 0.1, "y": 0.5, "width": 0.7, "height": 0.1}}
        self.provider.analyze_image.side_effect = lambda **kw: AiVisionResponse(
            json.dumps({"pageReadable": True, "items": [self.raw, self.raw, sibling]}), "fixture", "fixture-vision"
        )
        submission = self.upload(self.create())
        self.service.analyze("parent-a", submission["id"], {"revision": submission["revision"]})
        self.assertTrue(self.service.process_next()["ok"])
        detail = self.service.get("parent-a", submission["id"])["submission"]
        self.assertEqual([item["status"] for item in detail["items"]], ["pending", "pending", "incorrect"])
        self.assertEqual([item["readyForStudent"] for item in detail["items"]], [False, False, True])
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM learning_answer_events").fetchone()["n"], 1)
        self.assertEqual(self.transport.call_count, 5)

    def test_first_returned_parse_failure_does_not_prevent_other_page_correction(self):
        submission = self.two_pages()
        self.provider.analyze_image.side_effect = [self.response(valid=False), self.response()]
        self.service.process_next()
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        detail = self.service.get("parent-a", submission["id"])["submission"]
        self.assertEqual(len(detail["items"]), 1)
        self.assertTrue(detail["items"][0]["readyForStudent"])

    def test_second_returned_parse_failure_does_not_block_already_identified_first_page_mistake(self):
        submission = self.two_pages()
        self.provider.analyze_image.side_effect = [self.response(), self.response(valid=False)]
        self.service.process_next()
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        detail = self.service.get("parent-a", submission["id"])["submission"]
        self.assertEqual(len(detail["items"]), 1)
        self.assertTrue(detail["items"][0]["readyForStudent"])

    def test_transient_metadata_failure_does_not_delete_the_only_received_paid_reply(self):
        submission = self.upload(self.create())
        self.service.analyze("parent-a", submission["id"], {"revision": submission["revision"]})
        original_put = self.store.put_response
        original_current = self.service._current
        captured = {}

        def put(data, *, namespace):
            key = original_put(data, namespace=namespace)
            if namespace.startswith("homework-vision-response:"):
                captured["key"] = key
            return key

        def current(conn, job):
            if "key" in captured and not captured.get("failed"):
                captured["failed"] = True
                # A transient database error after the durable file write.
                raise RuntimeError("isolated metadata-write failure")
            return original_current(conn, job)

        with patch.object(self.store, "put_response", side_effect=put), patch.object(self.service, "_current", side_effect=current):
            result = self.service.process_next()
        self.assertEqual(result["error"], "homework_recognition_storage_failed")
        self.assertEqual(self.provider.analyze_image.call_count, 1)
        self.assertTrue(self.store._path(captured["key"]).exists())
        self.service.purge_files()
        # Purging temporary files must retain the only received provider result
        # when its private envelope still belongs to this live submission.
        self.assertTrue(self.store._path(captured["key"]).exists())
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='expired'")
        self.db.raw.commit()
        self.assertTrue(self.service.process_next()["ok"])
        self.assertEqual(self.provider.analyze_image.call_count, 1)
        self.assertEqual(self.transport.call_count, 5)

    def test_media_resume_validates_a_ready_clip_before_claiming_paper_ready(self):
        submission = self.ready()
        item = self.db.execute("SELECT * FROM homework_items").fetchone()
        media = parsed(item["media_json"])
        self.store._path(media["prompt"]["storageKey"]).unlink()
        self.db.execute("UPDATE homework_jobs SET status='queued',stage='media'")
        self.db.raw.commit()
        calls_before = (self.provider.analyze_image.call_count, self.transport.call_count)
        result = self.service.process_next()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "homework_audio_missing")
        self.assertEqual((self.provider.analyze_image.call_count, self.transport.call_count), calls_before)
