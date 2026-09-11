"""No provider, network, subprocess or shared test DB is used by these cases."""
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from integrations.openmaic_question_adapter import OpenMaicQuestionPhaseAdapter, PreparedQuestionPhase, QuestionPhaseCommand
from tests.test_formal_qwen_audio_client import _Client


class PaidBudgetHooksTest(unittest.TestCase):
    def prepared(self):
        command = QuestionPhaseCommand("item-a", 1, "outline", 1, "request-a", "primary_1", "math", "zh-CN", "zh-CN", {"skillId": "addition_subtraction_20"}, {})
        return PreparedQuestionPhase(command, {}, '{"frozen":true}', 'a' * 64, {}, '{}', 'b' * 64)

    def test_phase_binding_is_private_environment_and_does_not_change_frozen_input(self):
        captured = []
        def runner(_args, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(returncode=0, stdout='{}', stderr='')
        binding = json.dumps({"schemaVersion": "mira.learning.paid-budget-binding.v1", "required": True, "authorizationId": "a" * 64})
        adapter = OpenMaicQuestionPhaseAdapter(process_runner=runner,
            paid_budget_environment=lambda _command: {"MIRA_PAID_BUDGET_BINDING": binding})
        with patch.dict(os.environ, {"MIRA_PAID_BUDGET_BINDING": "forged", "MIRA_PAID_BUDGET_INTERNAL_TOKEN": "stale"}):
            adapter.execute_phase(self.prepared())
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["input"], '{"frozen":true}')
        self.assertEqual(captured[0]["env"]["MIRA_PAID_BUDGET_BINDING"], binding)
        self.assertNotIn("MIRA_PAID_BUDGET_INTERNAL_TOKEN", captured[0]["env"])

    def test_unavailable_production_grant_prevents_child_process_start(self):
        calls = []
        def denied(_command):
            raise ValueError("synthetic unavailable grant")
        adapter = OpenMaicQuestionPhaseAdapter(process_runner=lambda *a, **kw: calls.append(kw), paid_budget_environment=denied)
        result = adapter.execute_phase(self.prepared())
        self.assertEqual(result.outcome, "failed_safe")
        self.assertEqual(result.safe_error_code, "provider_unavailable")
        self.assertEqual(calls, [])

    def test_formal_audio_delegates_binding_headers_without_mutating_payload(self):
        client = _Client()
        payload = {"requestId": "tts-a", "immutable": "payload"}
        binding = {"schemaVersion": "mira.learning.paid-budget-binding.v1", "required": True, "authorizationId": "a" * 64}
        client._request_formal_audio_json("POST", "/api/mira/formal-audio/tts", payload, paid_budget=binding)
        self.assertEqual(client.calls[0][2], payload)
        self.assertEqual(client.calls[0][3]["X-Mira-Paid-Budget-Required"], "1")
        self.assertEqual(client.calls[0][3]["X-Mira-Paid-Budget-Authorization"], "a" * 64)


if __name__ == '__main__':
    unittest.main()
