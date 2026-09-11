from copy import deepcopy
import unittest
from unittest.mock import Mock

from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError, _canonical_sha256


class FormalSearchProviderReadinessTest(unittest.TestCase):
    def test_research_receipt_accepts_actual_search_count_above_four_with_bound_evidence(self):
        receipt = {'schemaVersion': OpenMaicFullRuntimeClient.FORMAL_RESEARCH_RECEIPT_VERSION,
            'status': 'succeeded', 'runtimeRequestId': 'request-1', 'buildItemId': 'item-1',
            'classroomId': 'classroom-1', 'sessionId': 'session-1', 'providerId': 'baidu',
            'searchCount': 5, 'resultCount': 5, 'fetchedSourceCount': 1, 'citationCount': 1,
            'searches': [{'query': f'教学资料 {index}', 'searchedAt': '2026-09-10T00:00:00Z',
                          'resultCount': 1} for index in range(5)],
            'sources': [{'title': '教学资料', 'url': 'https://example.edu/source', 'textSha256': 'a' * 64}],
            'citations': [{'url': 'https://example.edu/source', 'sceneIds': ['scene-1']}]}
        def read(value):
            return OpenMaicFullRuntimeClient._research_receipt_from_payload(value,
                runtime_request_id='request-1', classroom_id='classroom-1')
        receipt['receiptSha256'] = _canonical_sha256(receipt)
        self.assertEqual(read(receipt), receipt)
        for invalid in (True, 0, -1, 5.0, '5', 6):
            with self.subTest(searchCount=invalid), self.assertRaises(OpenMaicFullRuntimeError):
                changed = {**receipt, 'searchCount': invalid}
                changed.pop('receiptSha256')
                changed['receiptSha256'] = _canonical_sha256(changed)
                read(changed)
        with self.assertRaises(OpenMaicFullRuntimeError):
            read({**receipt, 'receiptSha256': '0' * 64})

    def test_accepts_only_configured_matching_api_pairs_without_a_search_call(self):
        client = OpenMaicFullRuntimeClient('http://127.0.0.1:3100')
        healthy = {'success': True, 'status': 'ok', 'version': client.FORMAL_RUNTIME_VERSION,
            'capabilities': {'formalGeneration': True, 'professionalAgent': True,
                'webSearch': True, 'speechAudioGeneration': True},
            'runtimePolicy': {'formalGeneration': deepcopy(client.FORMAL_GENERATION_POLICY),
                'professionalResearch': deepcopy(client.FORMAL_PROFESSIONAL_RESEARCH_POLICY),
                'modelPolicy': deepcopy(client.FORMAL_PROFESSIONAL_MODEL_POLICY),
                'webSearch': {'schemaVersion': 'mira.openmaic.web-search-production-config.v1',
                    'providerId': 'baidu', 'productionMode': 'baidu_api',
                    'formalProductionConfigured': True, 'verification': 'configuration_only'}}}
        cases = [
            ('baidu', 'baidu_api', True, True), ('brave', 'brave_api', True, True),
            ('baidu', 'brave_api', True, False), ('brave', 'baidu_api', True, False),
            ('baidu', 'public_html', True, False), ('baidu', 'baidu_api', False, False),
            ('baidu', 'baidu_api', 1, False), (['baidu'], 'baidu_api', True, False),
        ]
        for provider, mode, configured, expected in cases:
            with self.subTest(provider=provider, mode=mode, configured=configured):
                payload = deepcopy(healthy)
                payload['runtimePolicy']['webSearch'].update(providerId=provider,
                    productionMode=mode, formalProductionConfigured=configured)
                client._request_json = Mock(return_value=payload)
                result = client.formal_generation_readiness()
                self.assertIs(result['ready'], expected)
                self.assertIn('未验证实际联网' if expected else '百度搜索', result['reason'])
                client._request_json.assert_called_once_with('GET', '/api/health?scope=formal-generation')
