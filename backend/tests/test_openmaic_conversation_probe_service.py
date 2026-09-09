from __future__ import annotations

from contextlib import contextmanager
import unittest

from core.security import hash_value
from services.openmaic_conversation_probe_service import (
    OpenMaicConversationProbeError,
    OpenMaicConversationProbeService,
)


class _ProbeRepository:
    def __init__(self):
        self.runtime = {
            "id": "runtime-1", "status": "ready", "quality_status": "approved",
            "retired_at": None, "upstream_classroom_id": "classroom-1",
        }
        self.row = None

    @contextmanager
    def transaction(self):
        yield object()

    def get_runtime_classroom(self, _conn, *, runtime_id, for_update):
        return self.runtime if runtime_id == self.runtime["id"] and for_update else None

    def create_conversation_probe(self, _conn, **values):
        self.row = {**values, "id": values["probe_id"], "consumed_at": None, "revoked_at": None, "finalized_at": None,
                    "runtime_token_hash": None, "runtime_session_id": None}

    def get_conversation_probe_by_ticket_for_update(self, _conn, *, ticket_hash):
        return self.row if self.row and self.row["ticket_hash"] == ticket_hash else None

    def get_conversation_probe_by_runtime_token_for_update(self, _conn, *, runtime_token_hash):
        return self.row if self.row and self.row["runtime_token_hash"] == runtime_token_hash else None

    def get_conversation_probe_by_id_for_update(self, _conn, *, probe_id):
        return self.row if self.row and self.row["probe_id"] == probe_id else None

    def get_conversation_probe_by_runtime_classroom_for_update(self, _conn, *, runtime_classroom_id):
        return self.row if self.row and self.row["runtime_classroom_id"] == runtime_classroom_id else None

    def consume_conversation_probe_ticket(self, _conn, *, probe_id, runtime_token_hash, runtime_session_id, now):
        if not self.row or self.row["probe_id"] != probe_id or self.row["consumed_at"] is not None:
            return False
        self.row.update(consumed_at=now, runtime_token_hash=runtime_token_hash, runtime_session_id=runtime_session_id)
        return True

    def finalize_conversation_probe(self, _conn, *, probe_id, chat_receipt, transcription_receipt, now):
        if not self.row or self.row["probe_id"] != probe_id or self.row["revoked_at"] is not None:
            return False
        self.row.update(chat_receipt_json=chat_receipt, transcription_receipt_json=transcription_receipt,
                        finalized_at=now, revoked_at=now)
        return True


class OpenMaicConversationProbeServiceTest(unittest.TestCase):
    def test_exchange_proof_finalize_is_one_time_and_revoked(self):
        repo = _ProbeRepository()
        service = OpenMaicConversationProbeService(enabled=True, repository=repo)
        issued = service.issue_probe("runtime-1")
        exchanged = service.exchange_ticket(issued["ticket"])
        self.assertEqual(exchanged["purpose"], "conversation_probe")
        self.assertEqual(service.validate_runtime_token(exchanged["runtimeToken"])["purpose"], "conversation_probe")

        base_proof = {
            "schemaVersion": "mira.openmaic.conversation-proof.v1",
            "challenge": issued["challenge"],
            "runtimeSessionId": exchanged["runtimeSessionId"],
            "classroomId": issued["classroomId"],
            "providerCall": False,
        }
        finalized = service.finalize_probe(
            issued["probeId"],
            chat_receipt={"verified": True, "noCookieStatus": 401, "exchangeStatus": 204,
                          "cookieHttpOnly": True, "wrongStageStatus": 403, "chatStatus": 200,
                          "proof": base_proof},
            transcription_receipt={"verified": True, "overrideStatus": 400, "cleanStatus": 200,
                                   "proof": {**base_proof, "asrPolicy": {"providerId": "qwen-asr",
                                       "modelId": "qwen3-asr-flash", "fallbackAllowed": False}}},
        )
        self.assertTrue(finalized["revoked"])
        self.assertIsNotNone(repo.row["revoked_at"])
        with self.assertRaisesRegex(OpenMaicConversationProbeError, "已撤销"):
            service.validate_runtime_token(exchanged["runtimeToken"])
        with self.assertRaisesRegex(OpenMaicConversationProbeError, "已撤销"):
            service.exchange_ticket(issued["ticket"])

    def test_candidate_path_is_service_only_and_requires_attempt_three(self):
        repo = _ProbeRepository()
        repo.runtime.update(
            status="generating", quality_status="pending_review", attempt_ordinal=3,
            upstream_job_id="job-3", upstream_classroom_id=None,
        )
        service = OpenMaicConversationProbeService(enabled=True, repository=repo)
        with self.assertRaisesRegex(OpenMaicConversationProbeError, "尚未通过"):
            service.issue_probe("runtime-1")
        issued = service.issue_generation_candidate("runtime-1", "classroom-candidate")
        self.assertTrue(issued["candidate"])
        with self.assertRaisesRegex(OpenMaicConversationProbeError, "已创建"):
            service.issue_generation_candidate("runtime-1", "classroom-candidate")
        repo.runtime["attempt_ordinal"] = 2
        with self.assertRaisesRegex(OpenMaicConversationProbeError, "不允许"):
            service.issue_generation_candidate("runtime-1", "classroom-other")


if __name__ == "__main__":
    unittest.main()
