"""Exact quiz-stem audio restoration from an already verified operator parent.

This is a separate recorded amendment, not a new TTS/ASR receipt and not a
retroactive change to the original v4 candidate or its inherited-segment list.
"""
from copy import deepcopy
from urllib.parse import urlparse

from content.textbook_catalog import digest
from content.textbook_operator_revision import AUDIO_FIELDS, fail, parse, sha_text, speech_index
from content.textbook_preview_audio_contract import compare_transcript, resolve_audio_contract

PATCH_SCHEMA = 'mira.textbook.preview-parent-audio-restoration-patch.v1'
RECEIPT_SCHEMA = 'mira.textbook.preview-parent-audio-restoration.v1'
EVIDENCE_FILES = {'source.json', 'patch.json', 'saved.json', 'amendment.json'}


def validate_restoration_evidence(context, plan, items):
    """Rebuild the same restoration from portable original archive documents."""
    from services.textbook_preview_visual_revision import persisted
    if not isinstance(items, list) or len(items) > 1:
        fail('原音频恢复证据必须明确且有界')
    receipts, segments = [], {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {'revisionId', 'documents'} or set(item['documents']) != EVIDENCE_FILES:
            fail('原音频恢复归档文件不完整')
        docs = item['documents']
        source, patch, saved, receipt = (docs[k] for k in ('source.json', 'patch.json', 'saved.json', 'amendment.json'))
        target, restored = restoration_candidate(context, source, patch, plan)
        expected = restoration_receipt(context, source, saved, patch, plan, restored)
        if persisted(target) != persisted(saved) or receipt != expected or item['revisionId'] != receipt['revisionId']:
            fail('原音频恢复归档不能从原文及原父凭证准确重建')
        receipts.append(receipt)
        for segment in restored:
            key = (segment['sceneId'], segment['actionId'])
            if key in segments:
                fail('原音频恢复包含重复段落')
            segments[key] = (segment, receipt)
    return {**context, 'restorations': receipts, 'restoredSegments': segments}


def restoration_candidate(context, source, patch, plan):
    if (not isinstance(patch, dict) or set(patch) != {
            'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'}
            or patch.get('schemaVersion') != PATCH_SCHEMA or patch['expectedSourceSha256'] != digest(source)
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 16
            or not context or not context['candidate'].get('completeSceneEvidence')
            or 'build' not in context['parent']
            or resolve_audio_contract(plan)['teacher'] != context['candidate']['parent']['teacher']):
        fail('原音频恢复需要明确的当前完整场景修订和同一已发布父版')
    parent = context['parent']
    source_actions = speech_index(parse(parent['preview']['classroom_json']))
    approved = {(s['sceneId'], s['actionId']): s for s in context['candidate']['parent']['segments']}
    original_inherited = {(s['sceneId'], s['actionId']) for s in context['candidate']['inheritedSegments']}
    target = deepcopy(source)
    actions = speech_index(target)
    segments, seen = [], set()
    for change in patch['changes']:
        if not isinstance(change, dict) or set(change) != {'sceneId', 'actionId', 'questionId', 'beforeQuestionSha256', 'beforeAudioId'}:
            fail('原音频恢复只允许明确的逐字测验题干')
        key = (change['sceneId'], change['actionId'])
        if key in seen or key in original_inherited or key not in approved or key not in actions:
            fail('恢复段落重复、已经继承或没有通过原始审核')
        seen.add(key)
        scene, action = actions[key]
        old = source_actions[key][1]
        questions = [q for q in scene.get('content', {}).get('questions', []) if q.get('id') == change['questionId']]
        if (scene.get('type') != 'quiz' or len(questions) != 1
                or digest(questions[0]) != change['beforeQuestionSha256']
                or action.get('audioId') != change['beforeAudioId'] or action.get('audioId') == old.get('audioId')
                or action['text'] != old['text'] or questions[0].get('question') != action['text']
                or sum(a.get('type') == 'speech' and a.get('text') == action['text'] for a in scene['actions']) != 1):
            fail('恢复必须保持同一动作、逐字题干、唯一声音绑定和实际音频变更')
        segment = approved[key]
        entry = next(e for e in parent['audit']['segments'] if (e['sceneId'], e['actionId']) == key)
        if not compare_transcript(plan, action['text'], entry['transcript'])['passed']:
            fail('父音频没有通过当前冻结的英语审核策略')
        for field in AUDIO_FIELDS:
            action[field] = deepcopy(old[field])
        action['audioUrl'] = f"/api/classroom-media/{source['id']}/audio/{segment['ttsRequestId']}.wav"
        question = questions[0]
        question['questionAudioUrl'] = action['audioUrl']
        question['questionAudioBinding'] = {'schemaVersion': 'mira.learning.question-narration-binding.v1',
            'sceneId': scene['id'], 'actionId': action['id'], 'sourceTextSha256': sha_text(action['text'].strip()),
            'ttsRequestId': action['audioId']}
        segments.append(deepcopy(segment))
    return target, segments


def restoration_receipt(context, source, target, patch, plan, segments):
    value = {'schemaVersion': RECEIPT_SCHEMA,
        'revisionId': digest({'previewKey': plan['previewKey'], 'patch': patch}),
        'previewKey': plan['previewKey'], 'classroomId': source['id'],
        'sourceSha256': digest(source), 'targetSha256': digest(target),
        'parentProvenanceSha256': context['provenance']['sha256'],
        'parentEvidenceSha256': digest(context['parent']), 'targetPlanSha256': digest(plan),
        'patchSha256': digest(patch), 'restoredSegments': deepcopy(segments),
        'providerCalls': 0, 'publicationAllowed': False}
    return {**value, 'sha256': digest(value)}


def restored_entry(context, plan, scene, action, receipt):
    item = context.get('restoredSegments', {}).get((scene['id'], action['id']))
    if item is None:
        return None
    segment, amendment = item
    parent = context['parent']
    old = speech_index(parse(parent['preview']['classroom_json']))[(scene['id'], action['id'])][1]
    if (action['text'] != old['text'] or action.get('audioId') != segment['ttsRequestId']
            or action.get('audioMetadata') != old.get('audioMetadata')
            or urlparse(action.get('audioUrl', '')).path != f"/api/classroom-media/{context['candidate']['classroom']['id']}/audio/{segment['ttsRequestId']}.wav"
            or digest(receipt) != segment['ttsReceiptSha256'] or receipt.get('audioSha256') != segment['audioSha256']):
        fail('恢复音频与精确父句、教师、原始回执或字节不同')
    entry = next(e for e in parent['audit']['segments'] if (e['sceneId'], e['actionId']) == (scene['id'], action['id']))
    comparison = compare_transcript(plan, action['text'], entry['transcript'])
    if not comparison['passed'] or digest(entry) != segment['asrEntrySha256']:
        fail('恢复音频的原始 ASR 或当前策略未通过')
    return {**deepcopy(entry), 'comparison': comparison, 'similarityBps': comparison['similarityBps'],
        'operatorParent': {'provenanceSha256': context['provenance']['sha256'],
            'sourceEntrySha256': segment['asrEntrySha256'], 'restorationSha256': amendment['sha256']}}


def validate_published_restorations(frozen, release):
    amendments = frozen.get('operatorParentAudioRestorations')
    if amendments is None:
        if 'operatorParentAudioRestorationsSha256' in release['audioAudit']:
            fail('恢复音频交付缺少明确原始凭证')
        return
    proof, plan = frozen['operatorParent'], frozen['audioContract']
    if not isinstance(amendments, list) or len(amendments) != 1 or release['audioAudit'].get('operatorParentAudioRestorationsSha256') != digest(amendments):
        fail('恢复音频交付凭证无效')
    parent_segments = {(s['sceneId'], s['actionId']): s for s in proof['parent']['segments']}
    inherited = {(s['sceneId'], s['actionId']) for s in proof['inheritedSegments']}
    actions, media = speech_index(release['classroom']), {m['path']: m for m in release['media']}
    fields = {'schemaVersion', 'revisionId', 'previewKey', 'classroomId', 'sourceSha256', 'targetSha256',
        'parentProvenanceSha256', 'parentEvidenceSha256', 'targetPlanSha256', 'patchSha256',
        'restoredSegments', 'providerCalls', 'publicationAllowed', 'sha256'}
    seen = set()
    for amendment in amendments:
        if (set(amendment) != fields or amendment['schemaVersion'] != RECEIPT_SCHEMA
                or amendment['sha256'] != digest({k: v for k, v in amendment.items() if k != 'sha256'})
                or amendment['parentProvenanceSha256'] != proof['sha256']
                or amendment['parentEvidenceSha256'] != proof['parent']['sourceEvidenceSha256']
                or amendment['targetPlanSha256'] != digest(plan) or amendment['previewKey'] != plan['previewKey']
                or amendment['classroomId'] != proof['targetClassroomId']
                or amendment['providerCalls'] != 0 or amendment['publicationAllowed'] is not False
                or not amendment['restoredSegments']):
            fail('恢复音频交付的父来源或目标合同不同')
        for segment in amendment['restoredSegments']:
            key = (segment['sceneId'], segment['actionId'])
            if key in seen or key in inherited or parent_segments.get(key) != segment or key not in actions:
                fail('恢复交付只能包含不同于原继承列表的已通过父段落')
            seen.add(key)
            scene, action = actions[key]
            asset = media.get(action.get('audioUrl'), {})
            if (scene['type'] != 'quiz' or action.get('audioId') != segment['ttsRequestId']
                    or sha_text(action['text'].strip()) != segment['textSha256']
                    or asset.get('sourceSha256', asset.get('sha256')) != segment['audioSha256']):
                fail('恢复音频交付改变了原文或音频')
