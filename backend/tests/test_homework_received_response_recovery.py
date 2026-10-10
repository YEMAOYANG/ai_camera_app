"""Private returned OCR bytes survive local faults without another AI dispatch.

All persistence is in-memory SQLite and temporary assets. Providers and teacher
audio use synthetic fixtures; no configured service, phone or paid API is used.
"""
import base64
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_recognition_parser import RecognitionParseError, parse_recognition_response
from services.homework_service import canonical
from tests import test_homework_analysis as homework_fixture


class ReceivedRecognitionRecoveryTests(unittest.TestCase):
    create = homework_fixture.HomeworkTest.create
    upload = homework_fixture.HomeworkTest.upload
    events = homework_fixture.HomeworkTest.events

    def setUp(self):
        homework_fixture.HomeworkTest.setUp(self)

    def returned(self, *, items=None, text=None, finish_reason="stop", response_error=None):
        text = text if text is not None else json.dumps({"pageReadable": True, "items": items or [self.raw]})
        envelope = json.dumps({"id": "fixture-request-1", "choices": [{"finish_reason": finish_reason,
            "message": {"content": text}}], "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50}}).encode()
        response = AiVisionResponse(text, "fixture", "fixture-vision", finish_reason=finish_reason,
            usage={"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            request_id="fixture-request-1", response_error=response_error, raw_response=envelope)
        self.provider.analyze_image.side_effect = lambda **kwargs: response
        return response

    def queued(self):
        submission = self.upload(self.create())
        self.service.analyze("parent-a", submission["id"], {"revision": submission["revision"]})
        return submission

    def call(self):
        return self.db.execute("SELECT * FROM homework_provider_calls").fetchone()

    def saved(self):
        call = self.call()
        receipt = json.loads(call["receipt_json"])
        reference = receipt["receivedResponse"]
        body = self.store.read(reference["storageKey"])
        self.assertEqual(hashlib.sha256(body).hexdigest(), reference["sha256"])
        return call, receipt, reference, json.loads(body)

    def expire_lease(self):
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='terminated-worker'")
        self.db.raw.commit()

    def crash_after_save(self):
        submission = self.queued()
        with patch.object(self.service, "_materialize_recognition_response", side_effect=RuntimeError("fixture crash")):
            with self.assertRaisesRegex(RuntimeError, "fixture crash"):
                self.service.process_next()
        self.assertEqual(self.call()["status"], "dispatched")
        self.assertTrue(self.saved()[1]["responseReceived"])
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()
        return submission

    def test_numeric_null_and_invalid_region_preserve_reliable_siblings_in_real_pipeline(self):
        self.returned(items=[{**self.raw, "studentAnswer": 4},
            {**self.raw, "prompt": "4+2", "studentAnswer": None},
            {**self.raw, "prompt": "2+2", "studentAnswer": "3", "region": {"x": 0.9, "y": 0.1, "width": 0.5, "height": 0.2}},
            {**self.raw, "prompt": "1+1", "studentAnswer": "2"}])
        submission = self.queued()
        outcome = self.service.process_next()
        self.assertTrue(outcome["ok"])
        detail = self.service.get("parent-a", submission["id"])["submission"]
        self.assertEqual(detail["status"], "needs_confirmation")
        self.assertEqual(detail["pages"][0]["status"], "needs_confirmation")
        self.assertEqual([item["status"] for item in detail["items"]], ["incorrect", "pending", "pending", "correct"])
        self.assertEqual(detail["items"][0]["studentAnswer"], "4")
        self.assertEqual(detail["items"][1]["studentAnswer"], "")
        self.assertIsNone(detail["items"][2]["region"])
        self.assertEqual(len(self.events()), 2)
        self.assertEqual(self.transport.call_count, 5)
        self.provider.analyze_image.assert_called_once()
        diagnostics = self.saved()[1]["parserDiagnostics"]
        self.assertEqual(diagnostics["confirmationRequiredItems"], 2)
        self.assertEqual(diagnostics["numericAnswersNormalized"], 1)
        self.assertEqual(diagnostics["issueCounts"], {"answer_invalid": 1, "region_invalid": 1})
        student = self.service.student_detail("student-a", submission["id"])["submission"]
        self.assertEqual(student["originalSummary"]["pending"], 2)
        self.assertEqual(len(student["items"]), 1)

    def test_exit_after_file_fsync_before_database_link_replays_private_journal_only(self):
        self.returned()
        self.queued()
        original_put=self.store.put_response
        original_current=self.service._current
        state={}
        def put(data,*,namespace):
            key=original_put(data,namespace=namespace)
            state['written']=True
            return key
        def current(conn,job):
            if state.get('written') and not state.get('exited'):
                state['exited']=True
                raise SystemExit('isolated hard-exit window')
            return original_current(conn,job)
        with patch.object(self.store,'put_response',side_effect=put),patch.object(self.service,'_current',side_effect=current):
            with self.assertRaises(SystemExit):
                self.service.process_next()
        self.assertEqual(self.call()['status'],'dispatched')
        self.assertNotIn('receivedResponse',json.loads(self.call()['receipt_json']))
        self.expire_lease()
        self.assertTrue(self.service.process_next()['ok'])
        self.assertTrue(self.saved()[1]['recoveredDatabaseLink'])
        self.provider.analyze_image.assert_called_once()
        self.assertEqual(self.transport.call_count,5)

    def test_invalid_json_is_saved_exactly_and_local_retry_never_replays_http(self):
        response = self.returned(text='{"pageReadable":true,"items":[')
        submission = self.queued()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_invalid_json")
        call, receipt, reference, saved = self.saved()
        self.assertEqual(call["status"], "returned_invalid")
        self.assertEqual(saved["text"], response.text)
        self.assertEqual(base64.b64decode(saved["responseEnvelopeBase64"]), response.raw_response)
        self.assertEqual(receipt["parseError"], "homework_recognition_invalid_json")
        # The lease recovery path reads the same private source bytes, not a
        # new visual model result. Invalid syntax remains an explicit failure.
        self.expire_lease()
        with patch("services.homework_service.parse_recognition_response", wraps=parse_recognition_response) as local_parser:
            self.assertEqual(self.service.process_next()["error"], "homework_recognition_invalid_json")
        self.assertEqual(local_parser.call_args.args[0], response.text)
        self.assertEqual(self.saved()[2], reference)
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()
        self.assertFalse(self.service.get("parent-a", submission["id"])["submission"]["retryAllowed"])

    def test_local_parser_repair_recovers_saved_result_without_new_provider_call(self):
        response = self.returned()
        submission = self.queued()
        with patch("services.homework_service.parse_recognition_response", side_effect=RecognitionParseError("invalid_schema")):
            self.assertEqual(self.service.process_next()["error"], "homework_recognition_invalid_schema")
        reference = self.saved()[2]
        self.expire_lease()
        with patch("services.homework_service.parse_recognition_response", wraps=parse_recognition_response) as local_parser:
            self.assertTrue(self.service.process_next()["ok"])
        self.assertEqual(local_parser.call_args.args[0], response.text)
        self.assertEqual(self.saved()[2], reference)
        self.assertEqual(self.call()["status"], "succeeded")
        self.assertNotIn("parseError", self.saved()[1])
        self.assertEqual(self.service.get("parent-a", submission["id"])["submission"]["status"], "ready")
        self.provider.analyze_image.assert_called_once()
        self.assertEqual(self.transport.call_count, 5)

    def test_worker_crash_after_durable_save_resumes_without_second_dispatch(self):
        self.returned()
        submission = self.crash_after_save()
        reference = self.saved()[2]
        self.expire_lease()
        self.assertTrue(self.service.process_next()["ok"])
        self.assertEqual(self.saved()[2], reference)
        self.assertEqual(self.call()["status"], "succeeded")
        self.assertEqual(self.service.get("parent-a", submission["id"])["submission"]["status"], "ready")
        self.provider.analyze_image.assert_called_once()
        self.assertEqual(self.transport.call_count, 5)

    def test_length_finish_reason_preserves_receipt_with_precise_error(self):
        self.returned(finish_reason="length")
        submission = self.queued()
        with patch("services.homework_service.parse_recognition_response", side_effect=AssertionError("truncated output must not be graded")):
            self.assertEqual(self.service.process_next()["error"], "homework_recognition_truncated")
        self.assertEqual(self.call()["status"], "returned_invalid")
        self.assertEqual(self.saved()[1]["finishReason"], "length")
        self.assertEqual(self.saved()[1]["usage"]["providerBilledTokens"], 50)
        self.assertEqual(self.service.get("parent-a", submission["id"])["submission"]["status"], "failed")
        self.assertEqual(self.events(), [])
        self.transport.assert_not_called()

    def test_oversized_received_prefix_is_truncated_never_graded(self):
        self.returned(response_error="response_too_large")
        self.queued()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_truncated")
        self.assertEqual(self.saved()[3]["responseError"], "response_too_large")
        self.assertEqual(self.events(), [])
        self.transport.assert_not_called()

    def test_tampered_saved_bytes_fail_closed_without_provider_replay(self):
        self.returned()
        self.crash_after_save()
        reference = self.saved()[2]
        self.store._path(reference["storageKey"]).write_bytes(b'{"tampered":true}')
        self.expire_lease()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_storage_failed")
        self.assertEqual(self.call()["error_code"], "homework_recognition_storage_failed")
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()
        self.assertEqual(self.events(), [])

    def test_valid_hash_with_changed_scope_is_rejected(self):
        self.returned()
        self.crash_after_save()
        call, receipt, reference, saved = self.saved()
        saved["childId"] = "child-b"
        data = canonical(saved).encode()
        self.store._path(reference["storageKey"]).write_bytes(data)
        receipt["receivedResponse"]["sha256"] = hashlib.sha256(data).hexdigest()
        self.db.execute("UPDATE homework_provider_calls SET receipt_json=? WHERE id=?", (canonical(receipt), call["id"]))
        self.db.raw.commit()
        self.expire_lease()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_storage_failed")
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()

    def test_changed_request_reference_is_rejected_before_local_parsing(self):
        self.returned()
        self.crash_after_save()
        call, receipt, _, _ = self.saved()
        receipt["receivedResponse"]["requestSha256"] = "0" * 64
        self.db.execute("UPDATE homework_provider_calls SET receipt_json=? WHERE id=?", (canonical(receipt), call["id"]))
        self.db.raw.commit()
        self.expire_lease()
        with patch("services.homework_service.parse_recognition_response", side_effect=AssertionError("wrong receipt must not be parsed")):
            self.assertEqual(self.service.process_next()["error"], "homework_recognition_storage_failed")
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()

    def test_changed_saved_revision_cannot_be_materialized_for_current_job(self):
        self.returned()
        self.crash_after_save()
        call, receipt, reference, saved = self.saved()
        saved["analysisRevision"] += 1
        data = canonical(saved).encode()
        self.store._path(reference["storageKey"]).write_bytes(data)
        receipt["receivedResponse"]["sha256"] = hashlib.sha256(data).hexdigest()
        self.db.execute("UPDATE homework_provider_calls SET receipt_json=? WHERE id=?", (canonical(receipt), call["id"]))
        self.db.raw.commit()
        self.expire_lease()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_storage_failed")
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()

    def test_same_image_in_new_submission_does_not_recharge_returned_invalid_result(self):
        self.returned(text="invalid JSON")
        first = self.queued()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_invalid_json")
        first_reference = self.saved()[2]
        second = self.upload(self.create("another-submission"))
        self.service.analyze("parent-a", second["id"], {"revision": second["revision"]})
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_invalid_json")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM homework_provider_calls").fetchone()["n"], 1)
        self.assertEqual(self.saved()[2], first_reference)
        self.provider.analyze_image.assert_called_once()
        self.transport.assert_not_called()

    def test_private_receipt_and_raw_envelope_are_never_exposed_by_read_apis(self):
        response = self.returned()
        submission = self.queued()
        self.assertTrue(self.service.process_next()["ok"])
        reference = self.saved()[2]
        views = [self.service.get("parent-a", submission["id"]),
            self.service.student_detail("student-a", submission["id"]), self.service.list_student("student-a")]
        for view in views:
            exposed = json.dumps(view)
            self.assertNotIn(reference["storageKey"], exposed)
            for key in ("receivedResponse", "responseEnvelopeBase64", "providerRequestId", "parserDiagnostics", "requestSha256"):
                self.assertNotIn(key, exposed)
            self.assertNotIn(base64.b64encode(response.raw_response).decode(), exposed)

    def test_delete_purges_original_audio_and_received_response_assets(self):
        self.returned()
        submission = self.queued()
        self.assertTrue(self.service.process_next()["ok"])
        self.assertTrue(list(Path(self.tmp.name).rglob("*.json")))
        self.assertTrue(list(Path(self.tmp.name).rglob("*.png")))
        self.assertTrue(list(Path(self.tmp.name).rglob("*.wav")))
        self.service.delete("parent-a", submission["id"], {"revision": submission["revision"]})
        self.assertEqual([path for path in Path(self.tmp.name).rglob("*") if path.is_file()], [])
        self.assertEqual(self.call()["status"], "deleted")
        self.assertIsNone(self.call()["receipt_json"])
        self.assertIsNone(self.call()["result_json"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM homework_file_deletions").fetchone()["n"], 0)

    def test_delete_failed_response_removes_saved_raw_body_and_cancels_recovery(self):
        self.returned(text="invalid JSON")
        submission = self.queued()
        self.assertEqual(self.service.process_next()["error"], "homework_recognition_invalid_json")
        self.assertTrue(self.saved()[2])
        self.service.delete("parent-a", submission["id"], {"revision": submission["revision"]})
        self.assertEqual([path for path in Path(self.tmp.name).rglob("*") if path.is_file()], [])
        self.assertFalse(self.service.process_next()["processed"])
        self.provider.analyze_image.assert_called_once()
        self.assertIsNone(self.call()["receipt_json"])


if __name__ == "__main__":
    unittest.main()
