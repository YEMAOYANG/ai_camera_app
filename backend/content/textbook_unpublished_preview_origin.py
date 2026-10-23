"""Audio provenance for an audited, unpublished operator preview.

No publication/build is synthesized. A failed source ASR segment is retained in
the evidence but never returned as inheritable audio. Disk bytes and the live
database snapshot must also be checked by the registration adapter.
"""
from copy import deepcopy
from urllib.parse import urlparse

from content.textbook_catalog import digest, identifier, lesson_by_id
from content.textbook_operator_revision import fail, parse, sha_text, speech_index, _source_attempt, SHA
from content.textbook_preview_audio_contract import (
    SCHEMA, asr_request_id, audit_contract_identity, check_receipt_language_policy,
    compare_transcript, resolve_audio_contract, validate_v2_audit_segment,
)
from content.textbook_release import MEDIA


SOURCE_KIND = 'audited-unpublished-preview'


def validate_preview_parent(parent):
    """Return only exact, successfully audited segments of the saved source."""
    try:
        return _validate_preview_parent(parent)
    except (KeyError, TypeError, ValueError, AttributeError):
        fail('未发布预览的来源结构或审核证据无效')


def _validate_preview_parent(parent):
    if not isinstance(parent, dict) or set(parent) != {'manifest', 'preview', 'plan', 'receipts', 'audit'}:
        fail('未发布来源必须保留目录、预览、原计划、原收据与完整审核，不能伪造发布')
    manifest, preview, plan = parent['manifest'], parent['preview'], parent['plan']
    source, frozen, result = [parse(preview[k]) for k in ('classroom_json', 'input_json', 'result_json')]
    key, cid = preview['preview_key'], preview['classroom_id']
    expected = {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
                'manifestSha256': digest(manifest), 'nodeId': preview['node_id'],
                'gradeCode': manifest['gradeCode'], 'subject': manifest['subject']}
    lesson_by_id(manifest, preview['node_id'])
    authoring = frozen.get('authoring', {})
    if (not SHA.fullmatch(key) or not identifier(cid) or preview['status'] != 'preview_ready'
            or preview['edition_id'] != expected['editionId'] or preview['revision_id'] != expected['alignmentRevisionId']
            or any(frozen.get(k) != v for k, v in expected.items())
            or frozen.get('previewKey') != key
            or digest({k: v for k, v in frozen.items() if k not in {'previewKey', 'requirement'}}) != key
            or frozen.get('executionPolicy') != 'operator-authored-saved-classroom.v1'
            or authoring.get('mode') != 'openmaic_pro_workbench'
            or authoring.get('stageId') != cid or not identifier(authoring.get('sessionId'))
            or 'operatorRevision' in frozen or 'operatorParent' in frozen
            or source.get('id') != cid or source.get('stage', {}).get('id') != cid
            or digest(source) != preview['classroom_sha256']
            or result.get('audioStopCode') or result.get('audioPartial') is True
            or result.get('narrationRevisions') or result.get('visualRevisions')):
        fail('未发布原预览身份、冻结输入或完整配音状态不一致')
    contract = resolve_audio_contract(plan, frozen)
    receipts, audit = parent['receipts'], parent['audit']
    if (plan.get('schemaVersion') != SCHEMA or 'revisionId' in plan
            or plan['previewKey'] != key or plan['classroomSha256'] != frozen.get('sourceSha256')
            or not isinstance(receipts, list) or not receipts or len(receipts) > 1000
            or receipts != result.get('audioReceipts')):
        fail('未发布来源需要原 v2 配音计划和全部真实回执')
    by_request = {r['requestId']: r for r in receipts}
    actions = speech_index(source)
    entries = {(e['sceneId'], e['actionId']): e for e in audit.get('segments', [])}
    if (len(by_request) != len(receipts) or len(entries) != len(audit['segments'])
            or set(entries) != set(actions) or audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('previewKey') != key or audit.get('sourceSha256') != digest(source)
            or audit.get('contract') != audit_contract_identity(plan)
            or audit.get('sha256') != digest({k: v for k, v in audit.items() if k != 'sha256'})):
        fail('原 ASR 审核必须完整覆盖该预览并保留原摘要')
    assets = frozen.get('originalMedia', {}).get('assets', [])
    if (not assets or len({a.get('mediaPath') for a in assets}) != len(assets)
            or any(not SHA.fullmatch(str(a.get('sha256'))) or not MEDIA.fullmatch(a.get('mediaPath', ''))
                   or MEDIA.fullmatch(a['mediaPath'])[1] != cid for a in assets)):
        fail('未发布原图片缺少同课身份或原字节摘要')
    metadata = {'providerId': contract['teacher']['tts']['providerId'],
                'modelId': contract['teacher']['tts']['modelId'],
                'voiceId': contract['teacher']['voiceId'], 'fallbackUsed': False}
    segments, rejected = [], []
    for identity, (scene, action) in actions.items():
        receipt, entry = by_request.get(action.get('audioId'), {}), entries[identity]
        text = action['text'].strip()
        attempt = _source_attempt(plan, scene, action, by_request)
        if (receipt.get('status') != 'succeeded' or not SHA.fullmatch(str(receipt.get('audioSha256')))
                or receipt.get('narrationRevisionId') is not None
                or receipt.get('previewAudioIdentity') != {'planSha256': digest(plan), 'attempt': attempt}
                or any(action.get('audioMetadata', {}).get(k) != v for k, v in metadata.items())
                or urlparse(action.get('audioUrl', '')).path != f'/api/classroom-media/{cid}/audio/{action["audioId"]}.wav'):
            fail('原音频不符合原教师、原请求身份或成功回执')
        check_receipt_language_policy(plan, receipt)
        if (entry.get('text') != text or entry.get('textSha256') != sha_text(text)
                or entry.get('ttsRequestId') != action['audioId'] or entry.get('audioSha256') != receipt['audioSha256']
                or entry.get('asr', {}).get('status') != 'succeeded'
                or entry['asr'].get('requestId') != asr_request_id(plan, action['audioId'], receipt['audioSha256'])
                or entry.get('transcript') != entry['asr'].get('transcript')
                or entry['asr'].get('transcriptSha256') != sha_text(entry.get('transcript', ''))
                or entry.get('comparison') != compare_transcript(plan, text, entry['transcript'])
                or entry.get('similarityBps') != entry['comparison']['similarityBps']):
            fail('原 ASR 请求、原文、音频或逐句比较已改变')
        if not validate_v2_audit_segment(plan, action, entry, scene_id=scene['id']):
            rejected.append({'sceneId': scene['id'], 'actionId': action['id'],
                             'asrEntrySha256': digest(entry), 'reason': 'source_asr_not_passed'})
            continue
        segments.append({'sceneId': scene['id'], 'actionId': action['id'], 'textSha256': sha_text(text),
                         'ttsRequestId': action['audioId'], 'attempt': attempt, 'audioSha256': receipt['audioSha256'],
                         'ttsReceiptSha256': digest(receipt), 'asrRequestId': entry['asr']['requestId'],
                         'asrEntrySha256': digest(entry)})
    if audit.get('passed') is not (not rejected):
        fail('原审核总状态与逐句证据不符')
    return {'sourceKind': SOURCE_KIND, 'sourceIdentitySha256': digest(parent),
            'sourceAuditPassed': audit['passed'], 'rejectedSegments': rejected,
            'previewKey': key, 'classroomId': cid, 'classroomSha256': digest(source),
            'planSha256': digest(plan), 'receiptsSha256': digest(receipts), 'auditSha256': audit['sha256'],
            'sourceEvidenceSha256': digest(parent), 'binding': expected,
            'teacher': deepcopy(contract['teacher']), 'segments': segments,
            'originalMedia': deepcopy(frozen['originalMedia'])}
