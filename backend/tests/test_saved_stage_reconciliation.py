from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest

from integrations.openmaic_formal_quality import quality_canonical_json, quality_sha
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from services.learning_saved_stage_reconciliation import validate_saved_stage_completion


class SavedStageReconciliationTest(unittest.TestCase):
    def fixture(self):
        runtime = {'request_id': 'request-1', 'upstream_job_id': 'job-1'}
        formal = {'runtimeRequestId': 'request-1', 'gradeCode': 'primary_6'}
        input_sha = quality_sha(formal)
        session = 'miraformal_' + hashlib.sha256(('request-1\n' + quality_canonical_json(formal)).encode()).hexdigest()
        source = {'id': 'job-1', 'status': 'failed', 'error': 'OUTPUT_TRUNCATED',
            'completedAt': '2026-09-10T00:00:00Z', 'runtimeRequestId': 'request-1',
            'formalInput': formal, 'formalInputSha256': input_sha}
        source_bytes = json.dumps(source).encode()
        identity = {'sourceJobSha256': hashlib.sha256(source_bytes).hexdigest(),
            'sourceSnapshotSha256': 'a' * 64, 'repairSnapshotSha256': 'b' * 64,
            'sessionId': session, 'stageId': 'stage-1'}
        result = {'id': 'stage-1', 'scenesCount': 10, 'speechActionCount': 20,
            'professionalCreation': {'sessionId': session}, 'research': {'sessionId': session},
            'formalAudio': {'receiptSha256': 'c' * 64}}
        completion = {**identity, 'kind': 'operator_saved_stage_repair', 'originalSessionStatus': 'failed',
            'completedAt': '2026-09-10T01:00:00Z', 'recoveryId': 'omsaved_' + quality_sha(identity)[:24],
            'newAgentSessions': 0, 'newSearches': 0, 'result': result}
        completion['receiptSha256'] = quality_sha(completion)
        promoted = {**source, 'status': 'succeeded', 'step': 'completed', 'error': None,
            'completedAt': completion['completedAt'], 'result': {**result, 'classroomId': 'stage-1'},
            'formalSavedStageRecovery': {'originalStatus': 'failed', 'originalError': source['error'],
                'originalCompletedAt': source['completedAt'], **{key: identity[key] for key in
                ('sourceJobSha256', 'sourceSnapshotSha256', 'repairSnapshotSha256')},
                'recoveryId': completion['recoveryId'], 'receiptSha256': completion['receiptSha256']}}
        upstream = SimpleNamespace(status='succeeded', done=True, job_id='job-1', classroom_id='stage-1',
            scenes_count=10, speech_action_count=20, runtime_request_id='request-1',
            formal_contract_version=OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION,
            formal_input_sha256=input_sha, dispatch_ambiguous=False,
            professional_creation=result['professionalCreation'], research=result['research'],
            formal_audio=SimpleNamespace(receipt_sha256='c' * 64))
        return completion, source_bytes, promoted, dict(runtime=runtime, expected_input_sha=input_sha, upstream=upstream)

    def test_completed_original_stage_identity_accepts_without_a_provider_call(self):
        completion, source_bytes, promoted, options = self.fixture()
        self.assertEqual(validate_saved_stage_completion(completion, source_bytes, promoted, **options),
                         completion['receiptSha256'])

    def test_changed_job_session_source_or_unpromoted_completion_is_rejected(self):
        completion, source_bytes, promoted, options = self.fixture()
        for name in ('session', 'source', 'not_promoted', 'upstream', 'new_search'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                changed, current, arguments, original = deepcopy(completion), deepcopy(promoted), deepcopy(options), source_bytes
                if name == 'session': changed['sessionId'] = 'another-session'
                if name == 'source': original += b' '
                if name == 'not_promoted': current['status'] = 'failed'
                if name == 'upstream': arguments['upstream'].job_id = 'another-job'
                if name == 'new_search': changed['newSearches'] = True
                changed.pop('receiptSha256')
                changed['receiptSha256'] = quality_sha(changed)
                validate_saved_stage_completion(changed, original, current, **arguments)
