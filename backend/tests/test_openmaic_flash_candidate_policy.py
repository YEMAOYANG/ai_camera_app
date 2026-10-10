from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient as Client, OpenMaicFullRuntimeError, _canonical_sha256
from integrations.openmaic_formal_media import (FLASH_CANDIDATE_PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
    compatible_preparation_targets, professional_policy, professional_scene_learning_fields)
from tests.test_formal_provider_readiness_client import _request, _response, _sha

POLICY_ID = "deepseek-v4.1-flash-candidate-v1"


class FlashFormalPolicyTest(unittest.TestCase):
    def test_default_legacy_literal_and_hash_remain_frozen(self):
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": "", "MIRA_FORMAL_PLAYFUL_REQUIRE_3D": ""}):
            self.assertEqual(_canonical_sha256(Client.FORMAL_PROFESSIONAL_MODEL_POLICY), "ea231a83dcd2c22d3a29197d2f6edc0a80c1ca58a0d8707fa4d3f4218168daff")
            self.assertEqual(Client.selected_professional_model_policy(), Client.FORMAL_PROFESSIONAL_MODEL_POLICY)
            self.assertEqual(Client.selected_professional_creation_policy(), PLAYFUL_PROFESSIONAL_POLICY)
            selected = Client.selected_professional_model_policy()
            selected["agentDriver"]["modelId"] = "changed"
            self.assertEqual(Client.FORMAL_PROFESSIONAL_MODEL_POLICY["agentDriver"]["modelId"], "deepseek-v4-pro")

    def test_explicit_candidate_wins_and_unknown_selection_fails(self):
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": POLICY_ID}):
            self.assertEqual(Client.selected_professional_model_policy()["policyId"], POLICY_ID)
            self.assertEqual(Client.selected_professional_model_policy("deepseek-v4-pro-flash-v1"), Client.FORMAL_PROFESSIONAL_MODEL_POLICY)
            candidate = Client.selected_professional_model_policy()
            for role in ("agentDriver", "coursewareCreator", "coursewareVerifier", "structuredScene"):
                self.assertEqual(candidate[role]["modelId"], "deepseek-flash")
            self.assertIs(candidate["fallbackAllowed"], False)
            self.assertEqual(Client.selected_professional_creation_policy(), FLASH_CANDIDATE_PROFESSIONAL_POLICY)
        with self.assertRaises(ValueError):
            Client.selected_professional_model_policy("unreviewed-model-policy")
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": "unknown"}), self.assertRaises(ValueError):
            Client.selected_professional_creation_policy()

    def test_registry_and_scene_policy_are_exact_and_not_an_arbitrary_runtime_flag(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / "content" / "openmaic_formal_flash_candidate.v1.json").read_text())
        self.assertEqual(registry["modelPolicy"], Client.FLASH_CANDIDATE_PROFESSIONAL_MODEL_POLICY)
        self.assertEqual(registry["sceneLearningPolicy"], FLASH_CANDIDATE_PROFESSIONAL_POLICY["sceneLearningPolicy"])
        self.assertEqual(professional_policy(FLASH_CANDIDATE_PROFESSIONAL_POLICY), FLASH_CANDIDATE_PROFESSIONAL_POLICY)
        changed = deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY)
        changed["sceneLearningPolicy"]["noMasteryClaims"] = False
        with self.assertRaises(ValueError): professional_policy(changed)
        changed["sceneLearningPolicy"]["noMasteryClaims"] = 1
        with self.assertRaises(ValueError): professional_policy(changed)

    def test_candidate_target_only_matches_its_frozen_model_and_creation_pair(self):
        target = {"schemaVersion": "mira.learning.preparation-target.v1", "formalRuntimePolicy": {
            "professionalCreationPolicy": deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY),
            "professionalModelPolicy": deepcopy(Client.FLASH_CANDIDATE_PROFESSIONAL_MODEL_POLICY)}}
        self.assertEqual(compatible_preparation_targets(target), (target,))
        hybrid = deepcopy(target)
        hybrid["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(PLAYFUL_PROFESSIONAL_POLICY)
        with self.assertRaises(ValueError): compatible_preparation_targets(hybrid)
        for invalid in (Client.FORMAL_PROFESSIONAL_MODEL_POLICY,
            {**deepcopy(Client.FLASH_CANDIDATE_PROFESSIONAL_MODEL_POLICY), "fallbackAllowed": True}):
            changed = deepcopy(target)
            changed["formalRuntimePolicy"]["professionalModelPolicy"] = invalid
            with self.assertRaises(ValueError): compatible_preparation_targets(changed)

    def test_creation_receipt_requires_both_new_fields_and_exact_contract(self):
        fields = {key: deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY[key]) for key in ("modelPolicyId", "sceneLearningPolicy")}
        contract = {"professionalCreationPolicy": deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY)}
        self.assertEqual(professional_scene_learning_fields(fields, generation_contract=contract), fields)
        with self.assertRaises(ValueError): professional_scene_learning_fields({}, generation_contract=contract)
        with self.assertRaises(ValueError): professional_scene_learning_fields({"modelPolicyId": POLICY_ID})
        with self.assertRaises(ValueError): professional_scene_learning_fields(fields,
            generation_contract={"professionalCreationPolicy": PLAYFUL_PROFESSIONAL_POLICY})
        self.assertEqual(professional_scene_learning_fields({}), {})

    def test_canary_follows_selected_creator_and_never_tests_pro_for_flash(self):
        client = Client("http://127.0.0.1:3100")
        client._request_json = Mock(return_value={"success": True, "message": "Connection successful", "response": "READY"})
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": POLICY_ID}):
            self.assertEqual(client.formal_generation_provider_canary()["modelId"], "deepseek-flash")
        client._request_json.assert_called_once_with("POST", "/api/verify-model", {"model": "deepseek:deepseek-flash"})

    def candidate_receipt(self):
        request = _request()
        request["modelPolicyId"] = POLICY_ID
        response = _response(request)
        response["modelPolicyId"] = POLICY_ID
        response["calls"][0]["modelId"] = "deepseek-flash"
        response["providerProof"]["calls"][0]["modelId"] = "deepseek-flash"
        unsigned = {k: v for k, v in response["providerProof"].items() if k != "receiptSha256"}
        response["providerProof"]["receiptSha256"] = _sha(unsigned)
        return request, response

    def test_candidate_readiness_is_bound_and_historical_receipts_still_readable(self):
        request, response = self.candidate_receipt()
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": ""}):
            result = Client._validate_formal_provider_readiness_response(response,
                request_id=request["requestId"], expected_request_sha256=_sha(request))
        self.assertEqual(result["calls"][0]["modelId"], "deepseek-flash")
        self.assertEqual(result["modelPolicyId"], POLICY_ID)
        old_request = _request()
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": POLICY_ID}):
            old = Client._validate_formal_provider_readiness_response(_response(old_request),
                request_id=old_request["requestId"], expected_request_sha256=_sha(old_request))
        self.assertEqual(old["calls"][0]["modelId"], "deepseek-v4-pro")
        self.assertNotIn("modelPolicyId", old)

    def test_candidate_readiness_rejects_wrong_model_or_missing_policy_binding(self):
        request, response = self.candidate_receipt()
        for invalid in ("deepseek-v4-pro", "deepseek-v4-flash"):
            changed = deepcopy(response)
            changed["calls"][0]["modelId"] = invalid
            with self.assertRaises(OpenMaicFullRuntimeError):
                Client._validate_formal_provider_readiness_response(changed,
                    request_id=request["requestId"], expected_request_sha256=_sha(request))
        changed = deepcopy(response)
        changed.pop("modelPolicyId")
        with self.assertRaises(OpenMaicFullRuntimeError):
            Client._validate_formal_provider_readiness_response(changed,
                request_id=request["requestId"], expected_request_sha256=None)

    def test_start_readiness_attaches_policy_only_for_candidate(self):
        client = Client("http://127.0.0.1:3100")
        request, response = self.candidate_receipt()
        client._request_formal_audio_json = Mock(return_value=response)
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": POLICY_ID}):
            client.start_formal_provider_readiness(**_request())
        self.assertEqual(client._request_formal_audio_json.call_args.args[2], request)

    def test_candidate_generation_health_requires_the_actual_matching_creation_policy(self):
        client = Client("http://127.0.0.1:3100")
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": POLICY_ID}):
            policy = client.selected_formal_generation_policy()
            self.assertEqual(policy["professionalCreation"], FLASH_CANDIDATE_PROFESSIONAL_POLICY)
            healthy = {"success": True, "status": "ok", "version": client.FORMAL_RUNTIME_VERSION,
                "capabilities": {"formalGeneration": True, "professionalAgent": True, "webSearch": True, "speechAudioGeneration": True},
                "runtimePolicy": {"formalGeneration": policy,
                    "formalGenerationSupportedProfessionalPolicies": [deepcopy(FLASH_CANDIDATE_PROFESSIONAL_POLICY)],
                    "professionalResearch": deepcopy(client.FORMAL_PROFESSIONAL_RESEARCH_POLICY),
                    "modelPolicy": client.selected_professional_model_policy(),
                    "webSearch": {"schemaVersion": "mira.openmaic.web-search-production-config.v1", "providerId": "baidu",
                        "productionMode": "baidu_api", "formalProductionConfigured": True, "verification": "configuration_only"}}}
            client._request_json = Mock(return_value=healthy)
            self.assertTrue(client.formal_generation_readiness()["ready"])
            for field, changed in (("formalGeneration", client.FORMAL_GENERATION_POLICY),
                                   ("modelPolicy", client.FORMAL_PROFESSIONAL_MODEL_POLICY),
                                   ("formalGenerationSupportedProfessionalPolicies", [])):
                invalid = deepcopy(healthy)
                invalid["runtimePolicy"][field] = deepcopy(changed)
                client._request_json = Mock(return_value=invalid)
                self.assertFalse(client.formal_generation_readiness()["ready"])
        with patch.dict("os.environ", {"MIRA_FORMAL_MODEL_POLICY": ""}):
            self.assertEqual(client.selected_formal_generation_policy(), client.FORMAL_GENERATION_POLICY)
