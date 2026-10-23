"""One traceable ASR recovery of a terminal rejection, never a score waiver.

The original failed receipt is retained in full. The new request recognizes the
same WAV with the same provider policy; it must pass the original comparator.
Running, unknown, ambiguous and successful requests cannot use this recovery.
"""
from copy import deepcopy
import hashlib

from content.textbook_catalog import digest
from core.errors import ApiError

SCHEMA = 'mira.textbook.asr-terminal-recovery.v1'


def reject():
    raise ApiError('textbook_asr_terminal_recovery_invalid',
                   '识别恢复必须绑定同一音频的原始终止失败回执，且只能执行一次', 409)


def request_id(original):
    # The runtime reserves exact English namespaces to enforce automatic
    # language detection. Keep that policy on a separately named ASR request.
    if original.startswith('tbbasr2_'):
        return 'tbbreasr2_' + digest({'schemaVersion': SCHEMA,
                                     'originalRequestId': original, 'attempt': 1})
    return original + '_terminal1'


def evidence(original, *, plan_sha256, action, scene_id, expected_request_id, audio_sha256):
    response = original.get('asr', {})
    text = action['text'].strip()
    if (response.get('requestId') != expected_request_id
            or response.get('status') != 'failed'
            or response.get('completionUsable') is not False
            or response.get('transcript') is not None
            or response.get('transcriptSha256') is not None
            or original.get('transcript') is not None
            or original.get('sceneId') != scene_id
            or original.get('actionId') != action['id']
            or original.get('ttsRequestId') != action['audioId']
            or original.get('text') != text
            or original.get('textSha256') != hashlib.sha256(text.encode()).hexdigest()
            or original.get('audioSha256') != audio_sha256
            or 'asrTerminalRecovery' in original):
        reject()
    value = {'schemaVersion': SCHEMA, 'planSha256': plan_sha256,
             'originalEntry': deepcopy(original), 'originalEntrySha256': digest(original),
             'requestId': request_id(expected_request_id), 'maximumProviderCalls': 1}
    value['sha256'] = digest(value)
    return value


def validate(entry, *, plan_sha256, action, scene_id, expected_request_id):
    value = entry.get('asrTerminalRecovery')
    if not isinstance(value, dict) or not isinstance(value.get('originalEntry'), dict):
        reject()
    expected = evidence(value['originalEntry'], plan_sha256=plan_sha256,
        action=action, scene_id=scene_id, expected_request_id=expected_request_id,
        audio_sha256=entry.get('audioSha256'))
    if value != expected:
        reject()
    return expected['requestId']
