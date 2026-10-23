"""Literal, completed v1 narration-amendment evidence for visual inheritance."""
from copy import deepcopy
import hashlib
import json
import re

from content.textbook_catalog import digest
from content.textbook_preview_audio_contract import resolve_audio_contract, revision_audio_plan, tts_request_id
from core.errors import ApiError

BASE_FILES = {'source.json', 'source-row.json', 'target-text.json', 'original-plan.json',
              'original-receipts.json', 'failed-audit.json', 'plan.json'}
EVIDENCE_FILES = BASE_FILES | {'intent.json', 'amendment.json', 'saved.json', 'target.json', 'receipts.json'}


def fail(message):
    raise ApiError('textbook_operator_revision_conflict', message, 409)


def validate_legacy_narration_evidence(parent, *, allow_v2=False):
    """Return request plans only after reconstructing the complete old repair."""
    try:
        return _validate_legacy_narration_evidence(parent, allow_v2=allow_v2)
    except (KeyError, TypeError, ValueError) as exc:
        fail('原旁白修订证据结构无效：' + str(exc))


def _validate_legacy_narration_evidence(parent, *, allow_v2=False):
    from services.textbook_preview_audio import bind_cue_audio, core_content
    from services.textbook_preview_narration_revision import (SCHEMA, SCHEMA_V2, text_candidate,
        validate_patch, speeches, bind_revised_question_audio, bind_revised_feedback_audio)
    from services.textbook_preview_visual_revision import persisted
    items = parent.get('sourceNarrationRevisions')
    preview = parent['preview']
    frozen, result = json.loads(preview['input_json']), json.loads(preview['result_json'])
    revisions = result.get('narrationRevisions', [])
    if ((not resolve_audio_contract(parent['plan'])['legacy'] and not allow_v2) or not isinstance(items, list)
            or not 1 <= len(items) <= 20 or len(items) != len(revisions)):
        fail('普通旧旁白继承必须有完整且有界的原修订归档')
    plans, seen = {}, set()
    current_receipts = {r['requestId']: r for r in parent['receipts']}
    for item, amendment in zip(items, revisions):
        if (not isinstance(item, dict) or set(item) != {'revisionId', 'files'}
                or not re.fullmatch(r'[a-f0-9]{64}', str(item['revisionId']))
                or item['revisionId'] in seen or not isinstance(item['files'], dict)
                or set(item['files']) != EVIDENCE_FILES or any(not isinstance(raw, str) for raw in item['files'].values())):
            fail('原旁白修订归档编号或文件清单无效')
        files, rid = item['files'], item['revisionId']
        try:
            docs = {name: json.loads(raw) for name, raw in files.items()}
        except ValueError as exc:
            fail('原旁白归档 JSON 无效：' + str(exc))
        intent, patch = docs['intent.json'], docs['intent.json']['patch']
        validate_patch(patch)
        raw_sha = lambda name: hashlib.sha256(files[name].encode('utf-8')).hexdigest()
        if (patch['schemaVersion'] not in ({SCHEMA, SCHEMA_V2} if allow_v2 else {SCHEMA}) or intent.get('schemaVersion') != 'mira.textbook.preview-narration-intent.v1'
                or set(intent.get('files', {})) != BASE_FILES
                or any(intent['files'][name] != raw_sha(name) for name in BASE_FILES)
                or intent.get('sha256') != digest({k: v for k, v in intent.items() if k != 'sha256'})
                or intent.get('revisionId') != rid or intent.get('previewKey') != preview['preview_key']
                or intent.get('classroomId') != preview['classroom_id']
                or digest({'previewKey': preview['preview_key'], 'patch': patch,
                           'failedAuditSha256': raw_sha('failed-audit.json')}) != rid
                or docs['amendment.json'] != amendment):
            fail('原旁白修订意图、文件摘要或完成回执不一致')
        source, source_row, base = docs['source.json'], docs['source-row.json'], docs['original-plan.json']
        original_receipts, receipts = docs['original-receipts.json'], docs['receipts.json']
        if (source_row['input_json'] != preview['input_json'] or source_row['preview_key'] != preview['preview_key']
                or source_row['classroom_id'] != preview['classroom_id']
                or source_row['classroom_sha256'] != digest(source) or json.loads(source_row['classroom_json']) != source
                or json.loads(source_row['result_json'])['audioReceipts'] != original_receipts
                or base != parent['plan'] or any(current_receipts.get(r['requestId']) != r for r in receipts)
                or receipts[:len(original_receipts)] != original_receipts
                or len({r['requestId'] for r in receipts}) != len(receipts)):
            fail('原旁白修订没有保留原始冻结输入和配音收据')
        by_original = {r['requestId']: r for r in original_receipts}
        if any(e.get('audioSha256') != by_original.get(e.get('ttsRequestId'), {}).get('audioSha256')
               for e in docs['failed-audit.json'].get('segments', [])):
            fail('原失败审核没有绑定实际原音频字节')
        rebuilt = text_candidate(source, patch, docs['failed-audit.json'], base)
        plan = revision_audio_plan(base, revision_id=rid, classroom_sha256=digest(rebuilt),
            core_sha256=digest(core_content(rebuilt)), frozen_input=frozen)
        if docs['target-text.json'] != rebuilt or docs['plan.json'] != plan:
            fail('原旁白文字目标或子请求计划无法严格重建')
        target = deepcopy(rebuilt)
        target_actions, old_actions, delivered = speeches(target), speeches(source), speeches(docs['target.json'])
        if set(delivered) != set(target_actions):
            fail('原旁白修订改变了语音段落身份')
        selected = {(c['sceneId'], c['actionId']) for c in patch['changes']}
        added = {r['requestId']: r for r in receipts[len(original_receipts):]}
        consumed = set()
        for identity in selected:
            scene, action = target_actions[identity]
            saved_action = delivered[identity][1]
            receipt = added.get(saved_action.get('audioId'), {})
            found = False
            for attempt in range(1, len(added) + 2):
                request = tts_request_id(plan, *identity, action['text'], attempt=attempt)
                consumed.add(request)
                if request == saved_action.get('audioId'):
                    found = True
                    break
                if added.get(request, {}).get('status') not in {'failed', 'ambiguous'}:
                    break
            if (not found or receipt.get('status') != 'succeeded' or receipt.get('narrationRevisionId') != rid
                    or receipt.get('classroomContentSha256') != plan['classroomSha256']
                    or receipt.get('textSha256') != hashlib.sha256(action['text'].encode()).hexdigest()):
                fail('原修订音频不能由完整子请求计划和失败尝试验证')
            action.update(audioId=saved_action['audioId'],
                audioUrl=f"{preview['runtime_origin']}/api/classroom-media/{preview['classroom_id']}/audio/{saved_action['audioId']}.wav")
        if consumed != set(added):
            fail('原修订归档包含未对应受审旁白的音频请求')
        bind_cue_audio({'scenes': [s for s in target['scenes'] if any(k[0] == s['id'] for k in selected)]}, preview['classroom_id'])
        question_changes = bind_revised_question_audio(target, patch) if patch['schemaVersion'] == SCHEMA_V2 else None
        feedback_changes = bind_revised_feedback_audio(target, patch) if 'feedbackChanges' in patch else None
        saved = docs['saved.json']
        if docs['target.json'] != target or persisted(saved) != persisted(target):
            fail('原旁白修订不止改变了获准文字和相应音频')
        expected = {'schemaVersion': 'mira.textbook.preview-narration-amendment.v1', 'revisionId': rid,
            'intentSha256': intent['sha256'], 'previewKey': preview['preview_key'], 'classroomId': preview['classroom_id'],
            'sourceSha256': digest(source), 'targetSha256': digest(saved), 'audioIdentityClassroomSha256': plan['classroomSha256'],
            'audioPlanSha256': raw_sha('plan.json'), 'failedAuditSha256': raw_sha('failed-audit.json'),
            'supersededTtsRequestIds': [old_actions[(c['sceneId'], c['actionId'])][1]['audioId'] for c in patch['changes']],
            'changedActions': [{'sceneId': c['sceneId'], 'actionId': c['actionId']} for c in patch['changes']],
            'newTtsRequestIds': [target_actions[(c['sceneId'], c['actionId'])][1]['audioId'] for c in patch['changes']],
            'reviewer': patch['reviewer'], 'basis': patch['basis'], 'generationDispatched': False, 'asrDispatched': False,
            'publicationAllowed': False, 'requiresNewAudioAudit': True}
        if patch['schemaVersion'] == SCHEMA_V2:
            expected.update(schemaVersion='mira.textbook.preview-narration-amendment.v2', questionChanges=question_changes)
            if 'feedbackChanges' in patch:
                expected['feedbackChanges'] = feedback_changes
        expected['sha256'] = digest(expected)
        if amendment != expected:
            fail('原旁白完成回执不能从归档精确重建')
        plans[rid] = plan
        seen.add(rid)
    return plans
