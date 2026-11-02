from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from scripts import verify_tal_homework as smoke


def event(kind, value):
    return b"event: " + kind.encode() + b"\ndata: " + smoke.encoded(value) + b"\n\n"


class TalSmokeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "private"
        self.args = ["--output-dir", str(self.folder), "--image-url", "https://example.com/sample.jpg"]
        self.calls = []

    def run_main(self, *, execute=True, replies=(), transport=None, extra=()):
        def fake(path, headers, body, timeout):
            # This assertion runs at the first actual network operation.
            state = json.loads((self.folder / "state.json").read_bytes())
            self.assertEqual(state["status"], "dispatching")
            self.assertEqual(state["submitCount"], 1)
            self.calls.append((path, headers, body, timeout))
            for reply in replies:
                if isinstance(reply, BaseException):
                    raise reply
                yield reply
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(smoke, "credentials", return_value=("fixture-id", "fixture-secret")) as load, \
                redirect_stdout(output), redirect_stderr(errors):
            code = smoke.main([*self.args, *(["--execute"] if execute else []), *extra], transport=transport or fake)
        return code, json.loads(output.getvalue()), errors.getvalue(), load

    def state(self):
        return json.loads((self.folder / "state.json").read_bytes())

    def test_signature_independent_known_vector_and_single_url_encoding(self):
        # Independently calculated by OpenSSL HMAC-SHA1, not the production function.
        query = {"access_key_id": "fixture-id", "timestamp": "1700000000000",
                 "signature_nonce": "00000000-0000-4000-8000-000000000000"}
        body = b'{"image_url_list":[{"image_url":"https://example.org/test.jpg"}]}'
        self.assertEqual(smoke.signature(query, body, "fixture-secret"), "G4shO/GwqFmuJflgeITlKVWwcXM=")
        code, result, _, _ = self.run_main(replies=[(200, event("end", {"execute_result": 0, "results": [{"index": 0, "correct_result": 1}]}))])
        self.assertEqual(code, 0)
        path, headers, sent, timeout = self.calls[0]
        parsed = parse_qs(urlsplit(path).query)
        signature = parsed.pop("signature")[0]
        self.assertEqual(signature, smoke.signature({k: v[0] for k, v in parsed.items()}, sent, "fixture-secret"))
        self.assertEqual(headers["X-TAL-AccountId"], "mira-smoke")
        self.assertEqual(headers["X-TAL-DeviceId"], "mira-smoke")
        self.assertEqual(headers["X-Channel"], "mira-smoke")
        self.assertEqual(sent, smoke.encoded({"image_url_list": [{"image_url": self.args[-1]}]}))
        self.assertRegex(parsed["timestamp"][0], r"^\d{13}$")
        self.assertEqual(result["status"], "completed")

    def test_default_dry_run_never_reads_credentials_or_opens_network(self):
        with patch.object(smoke, "https_stream", side_effect=AssertionError("network forbidden")):
            code, result, _, load = self.run_main(execute=False, extra=["--credentials-file", "/missing/private.json"])
        load.assert_not_called()
        self.assertEqual((code, result["status"]), (0, "prepared"))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.folder.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.folder / "state.json").stat().st_mode & 0o777, 0o600)

    def test_stream_durable_before_parse_and_final_results_merge_without_double_count(self):
        first = event("data", {"results": [{"uuid": "q1", "index": 0, "bbox": [1, 2, 3, 4], "correct_result": 2,
                                              "answers": [{"uuid": "a1", "correct_result": 0, "text": "PRIVATE CHILD TEXT"}]}]})
        last = event("data", {"results": [{"uuid": "q1", "correct_result": 1,
                                             "answers": [{"uuid": "a1", "correct_result": 1}, {"index": 1, "correct_result": 2}]},
                                            {"index": 2, "correct_result": 3}]})
        raw = first + last + event("end", {"execute_result": 0})
        original = smoke.Events.feed
        def check_saved(events, chunk):
            self.assertTrue((self.folder / "response.sse").read_bytes().endswith(chunk))
            return original(events, chunk)
        with patch.object(smoke.Events, "feed", check_saved):
            code, result, errors, _ = self.run_main(replies=[(200, raw[:19]), (200, raw[19:101]), (200, raw[101:])])
        self.assertEqual(code, 0)
        summary = result["summary"]
        self.assertEqual(summary["questionCount"], 2)
        self.assertEqual(summary["answerCount"], 2)
        self.assertEqual([summary[k] for k in ("correctCount", "incorrectCount", "unansweredCount")], [1, 1, 1])
        self.assertTrue(summary["coordinatesPresent"])
        self.assertNotIn("PRIVATE CHILD TEXT", json.dumps(result) + errors)
        self.assertEqual((self.folder / "response.sse").read_bytes(), raw)
        self.assertEqual((self.folder / "response.sse").stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.state()["responseSha256"], hashlib.sha256(raw).hexdigest())

    def test_only_sse_end_without_error_completes(self):
        cases = [(event("end", {"event": "check_image", "execute_result": 1004}), "provider_error"),
                 (event("data", {"execute_result": 1}) + event("end", {"execute_result": 0}), "provider_error"),
                 (event("data", {"event": "end", "execute_result": 0}), "incomplete"),
                 (event("end", {"execute_result": 0}), "no_results"),
                 (b"data: [DONE]\n\n", "submission_unknown"),
                 (event("end", {"error": "fixture-secret"}), "provider_error")]
        for index, (raw, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                self.folder = Path(self.temp.name) / str(index)
                self.args[1] = str(self.folder)
                code, result, errors, _ = self.run_main(replies=[(200, raw)])
                self.assertEqual((code, result["status"]), (2, expected))
                self.assertNotIn("fixture-secret", json.dumps(result) + errors)

    def test_finished_answer_snapshot_replaces_bbox_placeholder(self):
        reducer = smoke.Events()
        reducer.feed(event("bbox", {"results": [{"uuid": "question-1", "is_finish": 0,
                                                  "answers": [{"uuid": "placeholder", "correct_result": 0}]}]}))
        final = [{"uuid": f"answer-{index}", "correct_result": 1 if index < 5 else 2} for index in range(12)]
        reducer.feed(event("end", {"results": [{"uuid": "question-1", "is_finish": 1, "answers": final}]}))
        summary = reducer.summary()
        self.assertEqual([summary[key] for key in ("questionCount", "answerCount", "correctCount", "incorrectCount", "ungradedCount")],
                         [1, 12, 5, 7, 0])
        self.assertTrue(reducer.ended)

    def test_finished_snapshot_keeps_genuinely_ungraded_answer(self):
        reducer = smoke.Events()
        reducer.feed(event("bbox", {"results": [{"uuid": "question-1", "is_finish": 0,
                                                  "answers": [{"uuid": "placeholder", "correct_result": 0}]}]}))
        reducer.feed(event("end", {"results": [{"uuid": "question-1", "is_finish": 1,
                                                 "answers": [{"uuid": "final-ungraded", "correct_result": 0},
                                                             {"uuid": "final-correct", "correct_result": 1}]}]}))
        summary = reducer.summary()
        self.assertEqual([summary[key] for key in ("questionCount", "answerCount", "ungradedCount", "correctCount")], [1, 2, 1, 1])

    def test_partial_timeout_is_preserved_and_never_replayed_after_restart(self):
        raw = event("data", {"execute_result": 0})
        _, result, _, _ = self.run_main(replies=[(200, raw), TimeoutError("fixture-secret")])
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual((self.folder / "response.sse").read_bytes(), raw)
        self.assertEqual(len(self.calls), 1)
        code, result, _, load = self.run_main(replies=[(200, event("end", {}))])
        self.assertEqual((code, result["status"]), (2, "replay_blocked"))
        self.assertEqual(len(self.calls), 1)
        load.assert_not_called()

    def test_redirect_and_interrupt_do_not_retry_or_leak_secrets(self):
        for index, replies in enumerate(([(302, b"fixture-secret")], [KeyboardInterrupt("fixture-secret")])):
            with self.subTest(index=index):
                self.folder = Path(self.temp.name) / str(index)
                self.args[1] = str(self.folder)
                before = len(self.calls)
                code, result, errors, _ = self.run_main(replies=replies)
                self.assertEqual(code, 2)
                self.assertEqual(result["status"], "http_rejected" if index == 0 else "submission_unknown")
                self.assertEqual(len(self.calls), before + 1)
                self.assertNotIn("fixture-secret", json.dumps(result) + errors)

    def test_real_transport_path_saves_http_rejection_body_without_retry_or_leak(self):
        raw = b'{"error":"invalid signature fixture-secret"}'
        response = Mock(status=401)
        response.read1.side_effect = [raw[:13], raw[13:], b""]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch.object(smoke.http.client, "HTTPSConnection", return_value=connection) as factory, \
                patch.object(smoke.Events, "feed", side_effect=AssertionError("rejection is not SSE")):
            code, result, errors, _ = self.run_main(transport=smoke.https_stream)
        self.assertEqual((code, result["status"]), (2, "http_rejected"))
        self.assertEqual(factory.call_args.args, (smoke.HOST,))
        self.assertEqual(connection.request.call_count, 1)
        self.assertEqual(connection.request.call_args.args[0], "POST")
        self.assertEqual(response.read1.call_count, 3)
        connection.close.assert_called_once()
        self.assertEqual((self.folder / "response.sse").read_bytes(), raw)
        state = self.state()
        self.assertEqual(state["httpStatus"], 401)
        self.assertEqual(state["responseBytes"], len(raw))
        self.assertEqual(state["responseSha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(state["responseComplete"])
        self.assertNotIn("fixture-secret", json.dumps(result) + errors)
        _, replay, _, load = self.run_main()
        self.assertEqual(replay["status"], "replay_blocked")
        load.assert_not_called()

    def test_real_transport_path_bounds_and_preserves_partial_rejection_body(self):
        raw = b'{"error":"fixture-secret"}'
        response = Mock(status=401)
        response.read1.side_effect = [raw, b""]
        connection = Mock()
        connection.getresponse.return_value = response
        with patch.object(smoke.http.client, "HTTPSConnection", return_value=connection), patch.object(smoke, "MAX_BYTES", 12):
            code, result, errors, _ = self.run_main(transport=smoke.https_stream)
        self.assertEqual((code, result["status"]), (2, "http_rejected"))
        self.assertEqual((self.folder / "response.sse").read_bytes(), raw[:12])
        self.assertEqual(self.state()["responseBytes"], 12)
        self.assertFalse(self.state()["responseComplete"])
        self.assertEqual(response.read1.call_count, 1)
        connection.request.assert_called_once()
        connection.close.assert_called_once()
        self.assertNotIn("fixture-secret", json.dumps(result) + errors)

    def test_explicit_private_credentials_and_output_lock(self):
        file = Path(self.temp.name) / "credentials.json"
        file.write_text(json.dumps({"access_key_id": "fixture-id", "access_key_secret": "fixture-secret"}))
        file.chmod(0o600)
        self.assertEqual(smoke.credentials(str(file)), ("fixture-id", "fixture-secret"))
        file.chmod(0o644)
        with self.assertRaises(ValueError):
            smoke.credentials(str(file))
        self.run_main(execute=False)
        descriptor = os.open(self.folder / "run.lock", os.O_RDWR)
        try:
            smoke.fcntl.flock(descriptor, smoke.fcntl.LOCK_EX | smoke.fcntl.LOCK_NB)
            code, result, _, load = self.run_main()
            self.assertEqual((code, result["status"]), (2, "local_preflight_failed"))
            load.assert_not_called()
            self.assertEqual(self.calls, [])
        finally:
            os.close(descriptor)

    def test_prepared_image_binding_is_not_silently_replaced(self):
        self.run_main(execute=False)
        self.args[-1] = "https://example.com/changed.jpg"
        code, result, _, load = self.run_main()
        self.assertEqual((code, result["status"]), (2, "local_preflight_failed"))
        load.assert_not_called()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
