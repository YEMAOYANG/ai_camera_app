"""Repair selected ASR-failed lines while retaining successful audio and evidence.

prepare is provider-free. Execution records each dispatch before contacting TTS;
unknown calls are never resent. Original inputs, receipts and audit are archived
immutably; original WAVs and the top-level audio plan are never overwritten.
"""
from copy import deepcopy
import fcntl
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import wave

from content.textbook_catalog import canonical, digest
from content.textbook_asr_source_reuse import (
    SCHEMA as ASR_ORIGIN_AUDIT_SCHEMA,
    validate_audit as validate_asr_origin_audit,
)
from content.textbook_preview_audio_contract import (audit_contract_identity, check_receipt_language_policy,
    check_receipt_pronunciation, pronunciation_client_options, resolve_audio_contract,
    revision_audio_plan, tts_request_id, validate_v2_audit_segment,
    policy_revision_plan, audit_segment_plan)
from content.textbook_pinyin_pronunciation import (PLAN_SCHEMA as PINYIN_SCHEMA, validate_receipt_wav,
    policy_for_plan, provider_body, ZCS_V2_POLICY_VERSION)
from content.textbook_interactive_narration import interactive_cues, without_audio_helper
from content.textbook_preview import cue_speech, preview_checks
from core.errors import ApiError
from services.textbook_preview_revision_transaction import PreviewRevisionTransaction
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_preview_audio import atomic_json, bind_cue_audio, core_content
from services.textbook_preview_visual_revision import immutable, json_bytes, persisted, sha_bytes, verify_audio
from services.course_file_store import course_bytes, course_exists, course_text

SCHEMA = 'mira.textbook.preview-narration-revision.v1'
SCHEMA_V2 = 'mira.textbook.preview-narration-revision.v2'
SCHEMA_V3 = 'mira.textbook.preview-narration-revision.v3'
FEEDBACK_ADDITION_SCHEMA = 'mira.textbook.preview-feedback-addition.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')


def fail(message):
    raise ApiError('textbook_preview_narration_revision_conflict', message, 409)


def validate_patch(patch):
    if isinstance(patch, dict) and patch.get('schemaVersion') == FEEDBACK_ADDITION_SCHEMA:
        from content.textbook_feedback_addition import validate_patch as validate_addition
        validate_addition(patch)
        return
    v3 = isinstance(patch, dict) and patch.get('schemaVersion') == SCHEMA_V3
    v2 = isinstance(patch, dict) and patch.get('schemaVersion') in (SCHEMA_V2, SCHEMA_V3)
    feedback = isinstance(patch, dict) and patch.get('schemaVersion') == SCHEMA_V2 and 'feedbackChanges' in patch
    if (not isinstance(patch, dict) or set(patch) != {
            'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'} | ({'policyVersion'} if v3 else {'questionChanges'} if v2 else set()) | ({'feedbackChanges'} if feedback else set())
            or patch['schemaVersion'] not in (SCHEMA, SCHEMA_V2, SCHEMA_V3)
            or not SHA.fullmatch(str(patch['expectedSourceSha256']))
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 160):
        fail('需要当前课件摘要、修订说明和指定失败旁白')
    if v3 and patch['policyVersion'] != ZCS_V2_POLICY_VERSION:
        fail('仅允许登记的 ZCS 覆盖删除政策')
    seen = set()
    for change in patch['changes']:
        fields = {'sceneId', 'actionId', 'beforeTextSha256', 'text'} | ({'auditSegmentSha256', 'reason'} if v2 else set())
        if (not isinstance(change, dict) or set(change) != fields
                or any(not isinstance(change[k], str) or not change[k] for k in ('sceneId', 'actionId'))
                or not SHA.fullmatch(str(change['beforeTextSha256']))
                or not isinstance(change['text'], str) or change['text'] != change['text'].strip()
                or not 1 <= len(change['text']) <= 1000
                or (change['sceneId'], change['actionId']) in seen):
            fail('旁白修订编号重复或缺少准确的原文摘要')
        seen.add((change['sceneId'], change['actionId']))
        if v2 and (not SHA.fullmatch(str(change['auditSegmentSha256'])) or change['reason'] != ('asr-pronunciation-policy-mismatch' if v3 else 'asr-lexical-mismatch')):
            fail('新版修订须明确绑定原始 ASR 词句差异，不接受一般文案改写')
    if v2 and not v3:
        if not isinstance(patch['questionChanges'], list) or len(patch['questionChanges']) > len(seen):
            fail('题干联动修订格式无效')
        questions, actions = set(), set()
        for change in patch['questionChanges']:
            if (not isinstance(change, dict) or set(change) != {'sceneId', 'questionId', 'actionId',
                    'beforeQuestionSha256', 'afterQuestionSha256', 'text'}
                    or any(not isinstance(change[k], str) or not change[k] for k in ('sceneId', 'questionId', 'actionId'))
                    or any(not SHA.fullmatch(str(change[k])) for k in ('beforeQuestionSha256', 'afterQuestionSha256'))
                    or not isinstance(change['text'], str) or change['text'] != change['text'].strip()
                    or not 1 <= len(change['text']) <= 1000
                    or (change['sceneId'], change['questionId']) in questions
                    or (change['sceneId'], change['actionId']) in actions
                    or (change['sceneId'], change['actionId']) not in seen):
                fail('题干联动须有唯一题目、对应旁白及完整前后题目摘要')
            questions.add((change['sceneId'], change['questionId']))
            actions.add((change['sceneId'], change['actionId']))
        links = patch.get('feedbackChanges', [])
        if not isinstance(links, list) or len(links) > len(seen):
            fail('选项反馈联动清单无效')
        for change in links:
            if (not isinstance(change, dict) or set(change) != {'sceneId', 'questionId', 'optionValue', 'actionId',
                    'beforeQuestionSha256', 'afterQuestionSha256', 'text'}
                    or any(not isinstance(change[k], str) or not change[k] for k in ('sceneId', 'questionId', 'optionValue', 'actionId', 'text'))
                    or any(not SHA.fullmatch(str(change[k])) for k in ('beforeQuestionSha256', 'afterQuestionSha256'))
                    or (change['sceneId'], change['questionId']) in questions
                    or (change['sceneId'], change['actionId']) in actions
                    or (change['sceneId'], change['actionId']) not in seen):
                fail('选项反馈须唯一对应完整原题、具体选项和受审旁白；不能与题干重复修订')
            questions.add((change['sceneId'], change['questionId']))
            actions.add((change['sceneId'], change['actionId']))


def speeches(classroom):
    return {(s['id'], a['id']): (s, a) for s in classroom['scenes']
            for a in s.get('actions', []) if a.get('type') == 'speech'}


def preserve_source_preview_freeze(service, root, archive, row, source_row, original):
    """Accept only a verified immutable preview of the unchanged source."""
    before, after = (json.loads(r['result_json']) for r in (source_row, row))
    descriptor = after.get('frozenPreview')
    before.pop('frozenPreview', None)
    after.pop('frozenPreview', None)
    source_sha = digest(original)
    snapshot_id = 'tbprev_' + source_sha[:24]
    if (before != after or not isinstance(descriptor, dict)
            or set(descriptor) != {'classroomId', 'sourceSha256', 'snapshotSha256'}
            or descriptor['classroomId'] != snapshot_id or descriptor['sourceSha256'] != source_sha):
        fail('数据库快照已变化，不能覆盖')

    def replace_identity(value):
        if isinstance(value, dict):
            return {k: replace_identity(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace_identity(v) for v in value]
        return snapshot_id if value == row['classroom_id'] else value

    snapshot = service.runtime.get_classroom(snapshot_id)
    local = json.loads(course_text(root / (snapshot_id + '.json')))
    if (digest(snapshot) != descriptor['snapshotSha256'] or snapshot != local
            or persisted(snapshot) != persisted(replace_identity(original))):
        fail('验收预览快照未精确对应原课件，不能恢复旁白修订')
    # Keep the original intent and paid request IDs unchanged. The independent
    # metadata addition is archived before any retry or new segment dispatch.
    immutable(archive / 'source-preview-freeze.json', json_bytes({
        'schemaVersion': 'mira.textbook.source-preview-freeze.v1',
        'sourceSha256': source_sha, 'frozenPreview': descriptor,
        'sourceResultSha256': digest(json.loads(source_row['result_json'])),
        'currentResultSha256': digest(json.loads(row['result_json'])),
    }))


def text_candidate(source, patch, audit, plan=None):
    """Preserve complete raw ASR; v2 additionally permits explicit lexical drift."""
    validate_patch(patch)
    v3 = patch['schemaVersion'] == SCHEMA_V3
    addition = patch['schemaVersion'] == FEEDBACK_ADDITION_SCHEMA
    v2 = patch['schemaVersion'] in (SCHEMA_V2, SCHEMA_V3) or addition
    legacy = plan is None or resolve_audio_contract(plan)['legacy']
    schema = 'mira.textbook.audio-audit.v1' if legacy else 'mira.textbook.audio-audit.v2'
    origin_audit = (patch['schemaVersion'] == SCHEMA_V2
                    and audit.get('schemaVersion') == ASR_ORIGIN_AUDIT_SCHEMA)
    if origin_audit:
        if legacy:
            fail('原始来源 ASR 审核只能修订完整版本化配音计划')
        # This validator reconstructs the complete origin audit from the actual
        # source, plan, TTS receipt, WAV/PCM bytes and raw ASR histories.  In
        # particular, a shared-PCM origin keeps its original ASR request id;
        # never relabel it as if each target action had made another call.
        origin_entries = validate_asr_origin_audit(
            audit,
            plan=plan,
            classroom=source,
            expected_source_sha256=patch['expectedSourceSha256'],
        )
    else:
        origin_entries = None
        if (audit.get('schemaVersion') != schema
                or (not legacy and audit.get('contract') != audit_contract_identity(plan))
                or audit.get('sourceSha256') != patch['expectedSourceSha256']
                or (type(audit.get('passed')) is not bool if v2 else audit.get('passed') is not False)
                or digest({k: v for k, v in audit.items() if k != 'sha256'}) != audit.get('sha256')):
            fail('需要绑定当前课件、未通过且摘要完整的原始 ASR 审核')
    policy_target = policy_revision_plan(plan, patch['policyVersion']) if v3 else None
    source_actions = speeches(source)
    entries = ({identity: entry for identity, (entry, _) in origin_entries.items()}
               if origin_entries is not None else
               {(s['sceneId'], s['actionId']): s for s in audit.get('segments', [])})
    if len(entries) != len(audit.get('segments', [])) or set(entries) != set(source_actions):
        fail('失败审核必须完整覆盖当前课件的每段旁白')
    passed = []
    if v2 and (digest(source) != patch['expectedSourceSha256']
               or (plan is not None and audit.get('previewKey') != plan['previewKey'])):
        fail('新版修订必须对应当前完整课堂及配音计划')
    for identity, (_, action) in source_actions.items():
        entry = entries[identity]
        if (entry.get('ttsRequestId') != action.get('audioId')
                or entry.get('text') != action['text'].strip()
                or entry.get('textSha256') != sha_bytes(action['text'].strip().encode())
                or entry.get('asr', {}).get('status') != 'succeeded'
                or entry.get('transcript') != entry.get('asr', {}).get('transcript')
                or entry.get('asr', {}).get('transcriptSha256') != sha_bytes(entry.get('transcript', '').encode())
                or (legacy and entry.get('similarityBps') != asr_similarity_bps(action['text'], entry.get('transcript', '')))):
            fail('审核段落与当前原文、音频或真实识别结果不一致')
        if origin_entries is not None:
            # validate_asr_origin_audit already recomputed this comparison from
            # the immutable original receipt.  validate_v2_audit_segment cannot
            # be used here because it intentionally requires a per-action ASR
            # request id, while an origin audit may truthfully reuse one exact
            # source recognition across several equal-text/equal-PCM actions.
            result = entry['comparison']['passed']
        elif not legacy:
            result = validate_v2_audit_segment(plan, action, entry, scene_id=identity[0])
        else:
            result = entry['similarityBps'] >= 8500
        passed.append(result)
        if v2 and (type(entry.get('similarityBps')) is not int or entry['asr'].get('completionUsable') is False
                   or (not legacy and type(entry.get('comparison', {}).get('passed')) is not bool)):
            fail('原始审核的实际识别结果无效')
    if v2 and audit['passed'] is not all(passed):
        fail('原始 ASR 整体通过状态必须与各段真实结果一致')
    if addition:
        if not audit['passed']:
            fail('补充反馈前须完整通过现有全部旁白审核')
        from content.textbook_feedback_addition import text_candidate as add_feedback
        return add_feedback(source, patch)
    if v3:
        selected = {(c['sceneId'], c['actionId']) for c in patch['changes']}
        for identity, (_, action) in source_actions.items():
            actual_plan = audit_segment_plan(plan, action, entries[identity], scene_id=identity[0])
            old_body = provider_body(action['text'], policy_version=policy_for_plan(actual_plan)['policyVersion'])
            new_body = provider_body(action['text'], policy_version=policy_for_plan(policy_target)['policyVersion'])
            if (old_body != new_body) != (identity in selected):
                fail('仅可选择全部且确实改变请求正文的段落；未选音频必须原字节复用')
    target = deepcopy(source)
    target_actions = speeches(target)
    question_changes = {(q['sceneId'], q['actionId']): q for q in patch.get('questionChanges', [])}
    feedback_changes = {(q['sceneId'], q['actionId']): q for q in patch.get('feedbackChanges', [])}
    used_questions = set()
    used_feedback = set()
    for change in patch['changes']:
        identity = (change['sceneId'], change['actionId'])
        if identity not in target_actions:
            fail('指定旁白不存在')
        if v2:
            if (change['auditSegmentSha256'] != digest(entries[identity])
                    or not 0 <= entries[identity]['similarityBps'] < 10000):
                fail('只能修订绑定真实原始 ASR 的明确词句差异，不能改完全匹配的旁白')
        elif (entries[identity]['similarityBps'] >= 8500 if legacy else entries[identity]['comparison']['passed']):
            fail('只能修订明确未通过已冻结审核策略的指定失败旁白')
        scene, action = target_actions[identity]
        old, new = action['text'], change['text']
        if sha_bytes(old.encode()) != change['beforeTextSha256']:
            fail('原旁白摘要不符')
        if (old != new if v3 else old == new):
            fail('政策修订必须保持原文不变' if v3 else '文案修订没有改变原文')
        if v2 and not legacy:
            # Validate every replacement against its fixed language/phoneme
            # policy before any archive execution can dispatch its first call.
            tts_request_id(policy_target or plan, *identity, new)
        if scene.get('type') == 'interactive':
            html = scene['content']['html']
            without_audio_helper(html)
            before_cues = interactive_cues(html)
            changed_ids = {cue for cue, value in cue_speech(scene).items() if value['id'] == action['id']}
            if not changed_ids or old not in html:
                fail('指定旁白没有准确对应的页面语音提示')
            changed = html.replace(old, new)
            expected = [{**cue, 'text': new} if cue['id'] in changed_ids else cue for cue in before_cues]
            try:
                if interactive_cues(changed) != expected:
                    fail('文本替换会改变其他提示或损坏提示 JSON')
            except ValueError as exc:
                fail('新的提示文本无法安全绑定：' + str(exc))
            scene['content']['html'] = changed
        elif scene.get('type') == 'quiz' and identity in feedback_changes:
            linked = feedback_changes[identity]
            questions = scene.get('content', {}).get('questions', [])
            matching = [q for q in questions if q.get('id') == linked['questionId']]
            if len(matching) != 1:
                fail('选项反馈没有对应唯一原题')
            question = matching[0]
            feedback = question.get('optionFeedback', {}).get(linked['optionValue'])
            stems = [i for i, a in enumerate(scene['actions']) if a.get('type') == 'speech' and a.get('text') == question.get('question')]
            lines = [i for i, a in enumerate(scene['actions']) if a.get('type') == 'speech' and a.get('text') == old]
            if (not isinstance(feedback, dict) or feedback.get('text') != old or linked['text'] != new
                    or not any(o.get('value') == linked['optionValue'] for o in question.get('options', []))
                    or len(stems) != 1 or len(lines) != 1 or lines[0] <= stems[0]
                    or sum(f.get('text') == old for q in questions for f in q.get('optionFeedback', {}).values()) != 1
                    or any(a.get('type') == 'speech' and a.get('text') == new for a in scene['actions'])
                    or any(f.get('text') == new for q in questions for f in q.get('optionFeedback', {}).values())
                    or digest(question) != linked['beforeQuestionSha256']):
                fail('反馈修订须位于唯一题干之后，精确匹配唯一选项旁白且不能复用其他反馈')
            replacement = deepcopy(question)
            changed_feedback = replacement['optionFeedback'][linked['optionValue']]
            changed_feedback['text'] = new
            changed_feedback.pop('audioUrl', None)
            changed_feedback.pop('audioBinding', None)
            if digest(replacement) != linked['afterQuestionSha256']:
                fail('反馈修订不能改变题干、答案、选项、图片、分值或其他反馈')
            question.clear(); question.update(replacement)
            used_feedback.add(identity)
        elif scene.get('type') == 'quiz' and not v3:
            if not v2 or identity not in question_changes:
                fail('测验题干需要明确的完整题目联动修订，不能只替换朗读音频')
            linked = question_changes[identity]
            questions = scene.get('content', {}).get('questions', [])
            matching = [q for q in questions if q.get('id') == linked['questionId']]
            # This must be the question's independent verbatim speech, not an
            # explanation or a shared line ambiguously reading several items.
            if (len(matching) != 1 or sum(q.get('question') == old for q in questions) != 1
                    or sum(a.get('type') == 'speech' and a.get('text') == old for a in scene['actions']) != 1):
                fail('题干必须有唯一对应的独立逐字旁白')
            question = matching[0]
            if (question.get('question') != old or linked['text'] != new
                    or digest(question) != linked['beforeQuestionSha256']
                    or digest({**question, 'question': new}) != linked['afterQuestionSha256']):
                fail('原完整题目或新题干摘要不符；不能改答案、选项、图片或分值')
            question['question'] = new
            used_questions.add(identity)
        elif scene.get('type') == 'quiz':
            questions = scene.get('content', {}).get('questions', [])
            if (sum(q.get('question') == old for q in questions) != 1
                    or sum(a.get('type') == 'speech' and a.get('text') == old for a in scene['actions']) != 1):
                fail('政策修订测验音频必须精确对应唯一题干')
        action['text'] = new
        if scene.get('type') == 'interactive':
            cue_speech(scene)
    if used_questions != set(question_changes):
        fail('题干联动清单含未对应实际测验题干的额外条目')
    if used_feedback != set(feedback_changes):
        fail('反馈联动清单含未对应实际测验的额外条目')
    return target


def bind_revised_question_audio(target, patch):
    """Only the explicitly linked question gets its new independently read clip."""
    actions = speeches(target)
    result = []
    for change in patch.get('questionChanges', []):
        scene, action = actions[(change['sceneId'], change['actionId'])]
        question = next(q for q in scene['content']['questions'] if q['id'] == change['questionId'])
        if digest(question) != change['afterQuestionSha256'] or action['text'] != question['question']:
            fail('绑定音频前题目或对应旁白已变化')
        question['questionAudioUrl'] = urlparse(action['audioUrl']).path
        result.append({**change, 'deliveredQuestionSha256': digest(question), 'ttsRequestId': action['audioId']})
    if patch['schemaVersion'] == SCHEMA_V3:
        for change in patch['changes']:
            scene, action = actions[(change['sceneId'], change['actionId'])]
            if scene.get('type') == 'quiz':
                matching = [q for q in scene.get('content', {}).get('questions', []) if q.get('question') == action['text']]
                if len(matching) != 1:
                    fail('政策修订测验音频必须精确对应唯一题干')
                matching[0]['questionAudioUrl'] = urlparse(action['audioUrl']).path
    return result


def bind_revised_feedback_audio(target, patch):
    """Rebind only the explicitly revised option; retain every other question field."""
    from services.textbook_preview_audio import bind_question_audio
    actions = speeches(target)
    result = []
    for change in patch.get('feedbackChanges', []):
        scene, action = actions[(change['sceneId'], change['actionId'])]
        question = next(q for q in scene['content']['questions'] if q['id'] == change['questionId'])
        value = change['optionValue']
        if digest(question) != change['afterQuestionSha256'] or action['text'] != question['optionFeedback'][value]['text']:
            fail('绑定反馈音频前原题或对应旁白已变化')
        copy = deepcopy(scene)
        bind_question_audio({'scenes': [copy]})
        bound = next(q for q in copy['content']['questions'] if q['id'] == change['questionId'])['optionFeedback'][value]
        question['optionFeedback'][value] = bound
        result.append({**change, 'deliveredQuestionSha256': digest(question), 'ttsRequestId': action['audioId']})
    return result


def _check_archive(archive, intent):
    if intent.get('sha256') != digest({k: v for k, v in intent.items() if k != 'sha256'}):
        fail('修订意图摘要已变化')
    for name, sha in intent['files'].items():
        if sha_bytes(course_bytes(archive / name)) != sha:
            fail('已归档的原文、配音记录或失败审核已变化')


def revise_preview_narration(service, key, classroom_directory, patch, failed_audit_path,
                             *, execute=False, retry_recorded_failure=False, progress=lambda value: None):
    validate_patch(patch)
    row = service.get(key)
    cid = row['classroom_id']
    if (urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}
            or not re.fullmatch(r'[A-Za-z0-9_-]+', cid or '')):
        fail('只能修订本机未发布课件的配音')
    root = Path(classroom_directory).resolve()
    folder = root / cid / 'textbook-preview-audio'
    if not course_exists(folder / 'plan.json'):
        fail('原始配音计划不存在')
    audit_raw = course_bytes(Path(failed_audit_path))
    revision_id = digest({'previewKey': key, 'patch': patch, 'failedAuditSha256': sha_bytes(audit_raw)})
    archive = folder / 'narration-revisions' / revision_id
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'operator.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('课件正在配音或修订，请等待已有任务结束')
        with PreviewRevisionTransaction(service.repository, key, fail, root / (cid + '.json')) as conn:
            row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (key,)).fetchone()
            if row['status'] != 'preview_ready' or row['runtime_origin'] != service.runtime.base_url:
                fail('请先完成原课件全部配音和结构检查')
            published = conn.execute("SELECT input_json FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=? AND status='published'",
                                     (row['edition_id'], row['node_id'])).fetchall()
            if any(service.repository.parse(b['input_json']).get('previewKey') == key for b in published):
                fail('已发布课件不能原地替换旁白')
            conn.release(row)
            intent_path = archive / 'intent.json'
            if not course_exists(intent_path):
                source = service.repository.parse(row['classroom_json'])
                result = service.repository.parse(row['result_json'])
                if digest(source) != row['classroom_sha256'] or row['classroom_sha256'] != patch['expectedSourceSha256']:
                    fail('课件已变化，请针对当前版本重新准备修订')
                if (digest(service.runtime.get_classroom(cid)) != digest(source)
                        or digest(json.loads(course_text(root / (cid + '.json')))) != digest(source)):
                    fail('运行课件、本机文件与数据库快照不一致')
                verify_audio(source, result, root, cid)
                audit = json.loads(audit_raw)
                if audit.get('previewKey') != key:
                    fail('失败审核不属于当前预览')
                by_request = {r['requestId']: r for r in result['audioReceipts']}
                if any(s.get('audioSha256') != by_request.get(s.get('ttsRequestId'), {}).get('audioSha256')
                       for s in audit.get('segments', [])):
                    fail('失败审核音频摘要与原收据不一致')
                if audit.get('schemaVersion') == ASR_ORIGIN_AUDIT_SCHEMA and any(
                        s.get('target', {}).get('ttsReceipt') != by_request.get(s.get('ttsRequestId'))
                        for s in audit.get('segments', [])):
                    fail('原始来源审核的完整 TTS 收据与当前课件不一致')
                original_plan = course_bytes(folder / 'plan.json')
                original_receipts = course_bytes(folder / 'receipts.json')
                if json.loads(original_receipts) != result['audioReceipts']:
                    fail('原始音频收据与数据库不一致')
                previous_plan = json.loads(original_plan)
                if previous_plan.get('previewKey') != key:
                    fail('原配音计划不属于当前课件')
                frozen = service.repository.parse(row['input_json'])
                resolve_audio_contract(previous_plan, frozen)
                target = text_candidate(source, patch, audit, previous_plan)
                plan = revision_audio_plan(previous_plan, revision_id=revision_id, classroom_sha256=digest(target),
                    core_sha256=digest(core_content(target)), frozen_input=frozen, policy_version=patch.get('policyVersion'))
                archive.mkdir(parents=True, exist_ok=True)
                files = {'source.json': json_bytes(source), 'source-row.json': json_bytes(row),
                         'target-text.json': json_bytes(target), 'original-plan.json': original_plan,
                         'original-receipts.json': original_receipts, 'failed-audit.json': audit_raw,
                         'plan.json': json_bytes(plan)}
                for name, raw in files.items():
                    immutable(archive / name, raw)
                intent = {'schemaVersion': 'mira.textbook.preview-narration-intent.v1', 'revisionId': revision_id,
                          'previewKey': key, 'classroomId': cid, 'patch': patch,
                          'files': {name: sha_bytes(raw) for name, raw in files.items()}}
                intent['sha256'] = digest(intent)
                immutable(intent_path, json_bytes(intent))
            intent = json.loads(course_text(intent_path))
            _check_archive(archive, intent)
            if (intent.get('revisionId') != revision_id or intent.get('patch') != patch
                    or intent.get('previewKey') != key or intent.get('classroomId') != cid
                    or course_bytes(archive / 'failed-audit.json') != audit_raw):
                fail('修订意图与本次请求不一致')
            original = json.loads(course_text(archive / 'source.json'))
            source_row = json.loads(course_text(archive / 'source-row.json'))
            plan = json.loads(course_text(archive / 'plan.json'))
            resolve_audio_contract(plan, json.loads(source_row['input_json']))
            teacher = plan['teacher']
            target = json.loads(course_text(archive / 'target-text.json'))
            base_plan = json.loads(course_text(archive / 'original-plan.json'))
            rebuilt = text_candidate(original, patch, json.loads(audit_raw), base_plan)
            if target != rebuilt or plan != revision_audio_plan(base_plan, revision_id=revision_id,
                    classroom_sha256=digest(rebuilt), core_sha256=digest(core_content(rebuilt)),
                    frozen_input=json.loads(source_row['input_json']), policy_version=patch.get('policyVersion')):
                fail('归档目标或子计划不再对应严格修订合同')
            result = json.loads(source_row['result_json'])
            verify_audio(original, result, root, cid)
            if course_bytes(folder / 'plan.json') != course_bytes(archive / 'original-plan.json'):
                fail('原始配音计划已变化')
            current = service.runtime.get_classroom(cid)
            if digest(json.loads(course_text(root / (cid + '.json')))) != digest(current):
                fail('本机文件与运行课件不一致')
            committed = [r for r in service.repository.parse(row['result_json']).get('narrationRevisions', [])
                         if r.get('revisionId') == revision_id]
            if committed:
                receipt = committed[-1]
                if (receipt.get('sha256') != digest({k: v for k, v in receipt.items() if k != 'sha256'})
                        or receipt.get('intentSha256') != intent['sha256']
                        or receipt['targetSha256'] != row['classroom_sha256'] or digest(current) != row['classroom_sha256']
                        or json.loads(course_text(folder / 'receipts.json')) != service.repository.parse(row['result_json'])['audioReceipts']):
                    fail('已完成修订的课件或收据又发生变化')
                immutable(archive / 'amendment.json', json_bytes(receipt))
                return receipt
            if row['classroom_json'] != source_row['classroom_json']:
                fail('数据库快照已变化，不能覆盖')
            if row['result_json'] != source_row['result_json']:
                preserve_source_preview_freeze(service, root, archive, row, source_row, original)
            if not execute:
                return {'revisionId': revision_id, 'archive': str(archive), 'prepared': True,
                        'failedAudit': str(archive / 'failed-audit.json'),
                        'segments': len(patch['changes']), 'ttsDispatched': False, 'publicationAllowed': False}
            saved_target_path = archive / 'target.json'
            if not course_exists(saved_target_path) and digest(current) != digest(original):
                fail('课件已变化，停止派发新的配音')
            new_receipts_path = archive / 'new-receipts.json'
            new_receipts = json.loads(course_text(new_receipts_path)) if course_exists(new_receipts_path) else []
            target_actions = speeches(target)
            for index, change in enumerate(patch['changes'], 1):
                scene, action = target_actions[(change['sceneId'], change['actionId'])]
                attempt, dispatched = 1, False
                while True:
                    request = tts_request_id(plan, scene['id'], action['id'], action['text'], attempt=attempt)
                    marker = archive / (request + '.dispatch.json')
                    try:
                        audio_receipt = service.runtime.get_formal_audio_tts(request, **pronunciation_client_options(plan))
                    except OpenMaicFullRuntimeError as exc:
                        if exc.status_code != 404:
                            raise
                        if course_exists(marker):
                            fail('已有派发结果不明且未查到收据，不能自动重发')
                        immutable(marker, json_bytes({'requestId': request, 'attemptedAt': now_ms()}))
                        dispatched = True
                        audio_receipt = service.runtime.start_formal_audio_tts(
                            request_id=request, classroom_id=cid, classroom_content_sha256=plan['classroomSha256'],
                            subject=plan['subject'], teacher_profile_id=teacher['teacherProfile']['id'],
                            teacher_profile_version=teacher['teacherProfile']['version'],
                            teacher_profile_sha256=teacher['teacherProfile']['contentHash'], teacher_gender=teacher['teacherGender'],
                            scene_id=scene['id'], scene_order=scene['order'], action_id=action['id'],
                            narration_segment_id=action['id'], text=action['text'], text_sha256=sha_bytes(action['text'].encode()),
                            **pronunciation_client_options(plan))
                    text_sha = sha_bytes(action['text'].encode())
                    check_receipt_language_policy(plan, audio_receipt)
                    check_receipt_pronunciation(plan, audio_receipt, action['text'])
                    if (audio_receipt.get('requestId') != request
                            or audio_receipt.get('classroomContentSha256', plan['classroomSha256']) != plan['classroomSha256']
                            or audio_receipt.get('textSha256', text_sha) != text_sha):
                        fail('新配音收据的原文或课件身份不一致')
                    # The transport returns status/media fields only. Preserve
                    # the exact deterministic request identity beside its receipt
                    # so later ASR uses this revision's frozen content identity.
                    audio_receipt = {**audio_receipt, 'classroomContentSha256': plan['classroomSha256'],
                                     'textSha256': text_sha, 'narrationRevisionId': revision_id}
                    if not resolve_audio_contract(plan)['legacy']:
                        audio_receipt['previewAudioIdentity'] = {'planSha256': digest(plan), 'attempt': attempt}
                    new_receipts = [r for r in new_receipts if r['requestId'] != request] + [audio_receipt]
                    atomic_json(new_receipts_path, new_receipts)
                    if audio_receipt['status'] == 'succeeded':
                        break
                    if audio_receipt['status'] not in {'failed', 'ambiguous'} or dispatched or not retry_recorded_failure:
                        fail('新配音尚未成功；已保存收据，不会自动重发。仅明确记录的失败可用重试参数另建身份')
                    attempt += 1
                audio_path = root / cid / 'audio' / (request + '.wav')
                if course_exists(audio_path):
                    audio = course_bytes(audio_path)
                    if sha_bytes(audio) != audio_receipt['audioSha256']:
                        fail('已有新配音文件摘要改变，不能覆盖')
                else:
                    audio = service.runtime.download_formal_audio_tts(request, expected_sha256=audio_receipt['audioSha256'])
                    if sha_bytes(audio) != audio_receipt['audioSha256']:
                        fail('下载的新音频摘要不一致')
                    if plan.get('schemaVersion') == PINYIN_SCHEMA:
                        validate_receipt_wav(audio_receipt, audio)
                    immutable(audio_path, audio)
                if plan.get('schemaVersion') == PINYIN_SCHEMA:
                    validate_receipt_wav(audio_receipt, audio)
                with wave.open(io.BytesIO(audio), 'rb') as wav:
                    duration = wav.getnframes() / wav.getframerate()
                    if duration <= 0:
                        fail('新配音没有有效时长')
                audio_receipt = {**audio_receipt, 'durationSeconds': round(duration, 3)}
                new_receipts = [r for r in new_receipts if r['requestId'] != request] + [audio_receipt]
                atomic_json(new_receipts_path, new_receipts)
                action.update(audioId=request, audioUrl=f'{service.runtime.base_url}/api/classroom-media/{cid}/audio/{request}.wav')
                progress({'completedAudio': index, 'totalAudio': len(patch['changes'])})
            changed_scenes = {change['sceneId'] for change in patch['changes']}
            bind_cue_audio({'scenes': [scene for scene in target['scenes'] if scene['id'] in changed_scenes]}, cid)
            revised_questions = bind_revised_question_audio(target, patch)
            if patch['schemaVersion'] == FEEDBACK_ADDITION_SCHEMA:
                from content.textbook_feedback_addition import bind_added_feedback
                revised_feedback = bind_added_feedback(target, original, patch)
            else:
                revised_feedback = bind_revised_feedback_audio(target, patch)
            frozen = json.loads(source_row['input_json'])
            prompt = frozen['previewPrompt']
            checks = preview_checks(target, prompt['expectedSceneCount'], frozen.get('originalMedia'), prompt.get('expectedQuestionCount', 6))
            if checks['issues']:
                fail('修订后课件结构检查未通过：' + '、'.join(checks['issues']))
            immutable(saved_target_path, json_bytes(target))
            combined = result['audioReceipts'] + new_receipts
            if len({r['requestId'] for r in combined}) != len(combined):
                fail('新旧音频收据编号重叠')
            immutable(archive / 'receipts.json', json_bytes(combined))
            current = service.runtime.get_classroom(cid)
            if digest(current) == digest(original):
                marker = archive / 'save-attempt.json'
                if course_exists(marker):
                    fail('上次保存结果不明且未发现目标快照，不能自动重发')
                immutable(marker, json_bytes({'intentSha256': intent['sha256'], 'attemptedAt': now_ms()}))
                service.runtime.save_preview_classroom(target)
                current = service.runtime.get_classroom(cid)
            if persisted(current) != persisted(target) or digest(json.loads(course_text(root / (cid + '.json')))) != digest(current):
                fail('保存结果不符，原始课件和全部配音已保留')
            immutable(archive / 'saved.json', json_bytes(current))
            old_actions = speeches(original)
            receipt = {'schemaVersion': 'mira.textbook.preview-narration-amendment.v1', 'revisionId': revision_id,
                       'intentSha256': intent['sha256'], 'previewKey': key, 'classroomId': cid,
                       'sourceSha256': digest(original), 'targetSha256': digest(current),
                       'audioIdentityClassroomSha256': plan['classroomSha256'], 'audioPlanSha256': intent['files']['plan.json'],
                       'failedAuditSha256': intent['files']['failed-audit.json'],
                       'supersededTtsRequestIds': [old_actions[(c['sceneId'], c['actionId'])][1]['audioId'] for c in patch['changes']
                                                   if (c['sceneId'], c['actionId']) in old_actions],
                       'changedActions': [{'sceneId': c['sceneId'], 'actionId': c['actionId']} for c in patch['changes']],
                       'newTtsRequestIds': [target_actions[(c['sceneId'], c['actionId'])][1]['audioId'] for c in patch['changes']],
                       'reviewer': patch['reviewer'], 'basis': patch['basis'], 'generationDispatched': False,
                       'asrDispatched': False, 'publicationAllowed': False, 'requiresNewAudioAudit': True}
            if patch['schemaVersion'] == SCHEMA_V2:
                receipt['schemaVersion'] = 'mira.textbook.preview-narration-amendment.v2'
                receipt['questionChanges'] = revised_questions
                if 'feedbackChanges' in patch:
                    receipt['feedbackChanges'] = revised_feedback
            if patch['schemaVersion'] == SCHEMA_V3:
                receipt.update(schemaVersion='mira.textbook.preview-narration-amendment.v3',
                    policyVersion=patch['policyVersion'], parentPlanSha256=digest(base_plan),
                    pronunciationPolicySha256=plan['pronunciationPolicySha256'])
            if patch['schemaVersion'] == FEEDBACK_ADDITION_SCHEMA:
                receipt.update(schemaVersion='mira.textbook.preview-feedback-addition-amendment.v1',
                               feedbackAdditions=revised_feedback)
            receipt['sha256'] = digest(receipt)
            updated = {**result, **checks, 'audioReceipts': combined, 'audioStopCode': None,
                       'narrationRevisions': [*result.get('narrationRevisions', []), receipt]}
            updated.pop('frozenPreview', None)
            used = {a['audioId'] for _, a in speeches(current).values()}
            updated.update(audioTotal=len(used), audioCompleted=len(used), audioPartial=False)
            updated['audioSeconds'] = round(sum(r.get('durationSeconds', 0) for r in combined if r['requestId'] in used), 3)
            active_receipts = course_bytes(folder / 'receipts.json')
            if active_receipts not in {course_bytes(archive / 'original-receipts.json'), json_bytes(combined)}:
                fail('活动收据清单被其他任务改变')
            atomic_json(folder / 'receipts.json', combined)
            conn.commit_phase()
            if (json.loads(course_text(root / (cid + '.json'))) != current
                    or course_bytes(folder / 'plan.json') != course_bytes(archive / 'original-plan.json')
                    or course_bytes(folder / 'receipts.json') != json_bytes(combined)):
                fail('提交前运行原稿或配音证据已变化，保留修订断点')
            changed = conn.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=?,result_json=?,updated_at=? WHERE preview_key=? AND classroom_sha256=?',
                                   (canonical(current), digest(current), canonical(updated), now_ms(), key, digest(original))).rowcount
            if changed != 1:
                fail('数据库版本已变化，请核对已保存的修订')
        immutable(archive / 'amendment.json', json_bytes(receipt))
        return receipt
