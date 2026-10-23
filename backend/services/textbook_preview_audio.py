"""Local operator adapter: saved content first, durable server TTS per segment.

Reuses the private, idempotent audio transport. Its receipt is not a formal
course release or ASR approval. A failed/ambiguous segment is never re-created.
"""
from copy import deepcopy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import wave

from content.textbook_preview_audio_contract import (MAX_SPEECH_ACTIONS, check_receipt_language_policy, check_receipt_pronunciation, new_audio_plan,
    pronunciation_client_options, resolve_audio_contract, tts_request_id, valid_tts_request_id, validate_child_request_plan)
from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import CUE_SCRIPT, bind_interactive_audio
from content.textbook_preview import cue_speech, preview_checks
from content.textbook_pinyin_pronunciation import PLAN_SCHEMA as PINYIN_SCHEMA, policy_for_plan, pronunciation_identity, validate_receipt_wav
from content import textbook_pinyin_pronunciation as pronunciation_registry
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError


def core_content(classroom):
    result = deepcopy(classroom)
    result.pop("createdAt", None)
    for scene in result["scenes"]:
        for action in scene.get("actions", []):
            if action.get("type") == "speech":
                for field in ("audioId", "audioUrl", "audioMetadata"):
                    action.pop(field, None)
    return result


def bind_question_audio(classroom, *, inheritance=None):
    """Bind quiz stems and selected feedback only to a unique verbatim speech.

    Missing clips are normal while a saved audio plan is incomplete. Ambiguous
    speech or a conflicting existing binding must never select a clip by order.
    """
    for scene in classroom["scenes"]:
        if scene.get("type") != "quiz":
            continue
        speeches = [(index, action) for index, action in enumerate(scene.get("actions", []))
                    if action.get("type") == "speech"]
        feedback_texts = [feedback.get("text")
                          for question in scene.get("content", {}).get("questions", [])
                          for feedback in (question.get("optionFeedback") or {}).values()]

        def bind(target, text, url_key, binding_key, question_id, option_value=None,
                 after_index=None, emit_binding=True):
            matches = [(index, action) for index, action in speeches
                       if isinstance(text, str) and text.strip() and action.get("text") == text]
            if len(matches) > 1:
                raise ApiError('textbook_preview_audio_binding_conflict', '题干或反馈不能唯一匹配已保存旁白', 409)
            if not matches or not matches[0][1].get("audioUrl"):
                if target.get(url_key) or target.get(binding_key):
                    raise ApiError('textbook_preview_audio_binding_conflict', '已有听题或反馈录音缺少唯一原文旁白', 409)
                return
            index, action = matches[0]
            if option_value is not None and (after_index is None or index <= after_index
                                              or feedback_texts.count(text) != 1):
                raise ApiError('textbook_preview_audio_binding_conflict', '选项反馈旁白必须位于对应题干之后', 409)
            clip = urlparse(action["audioUrl"]).path
            if not action.get("audioId") or not clip:
                raise ApiError('textbook_preview_audio_binding_conflict', '听题或反馈录音缺少正式旁白身份', 409)
            binding = {
                "schemaVersion": ("mira.learning.quiz-feedback-audio-binding.v1" if option_value is not None
                                  else "mira.learning.question-narration-binding.v1"),
                "sceneId": scene["id"],
                "ttsRequestId": action["audioId"],
                "sourceTextSha256": hashlib.sha256(text.strip().encode("utf-8")).hexdigest(),
            }
            if option_value is not None:
                binding["questionId"] = question_id
                binding["optionValue"] = option_value
            else:
                binding["actionId"] = action["id"]
            if ((target.get(url_key) and urlparse(target[url_key]).path != clip)
                    or (target.get(binding_key) and target[binding_key] != binding)):
                raise ApiError('textbook_preview_audio_binding_conflict', '已有听题或反馈录音与当前原文旁白不一致', 409)
            target[url_key] = clip
            if emit_binding:
                target[binding_key] = binding

        for question in scene.get("content", {}).get("questions", []):
            text = question.get("question")
            # A v3 visual-only revision can carry an audited historical
            # question alias whose spoken line also includes option labels.
            # Keep that literal approved binding; never derive a new one.
            preserved = False
            if inheritance and question.get('questionAudioUrl'):
                from content.textbook_operator_revision import VISUAL_PATCH_SCHEMA
                candidate = inheritance['candidate']
                old = [q for s in candidate['classroom']['scenes'] if s['id'] == scene['id']
                       for q in s.get('content', {}).get('questions', []) if q['id'] == question['id']]
                preserved = (candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA
                    and len(old) == 1 and old[0] == question)
            if not preserved:
                # The old atomic-quiz revision freezes its question payload
                # without this newer metadata field. Its own provenance still
                # verifies the exact stem, action and original receipt.
                legacy_quiz_shape = inheritance and inheritance['candidate']['patch']['schemaVersion'] == 'mira.textbook.published-operator-patch.v2'
                bind(question, text, "questionAudioUrl", "questionAudioBinding", question["id"],
                     emit_binding=not legacy_quiz_shape)
            stem_indices = [index for index, action in speeches if action.get("text") == text]
            for value, feedback in (question.get("optionFeedback") or {}).items():
                bind(feedback, feedback.get("text"), "audioUrl", "audioBinding", question["id"],
                     value, stem_indices[0] if len(stem_indices) == 1 else None)


def cue_pages(classroom):
    return [scene for scene in classroom["scenes"] if scene.get("type") == "interactive"
            and CUE_SCRIPT in str(scene.get("content", {}).get("html"))]


def bind_cue_audio(classroom, classroom_id):
    """Give each interactive page the saved clips of the teacher lines its cues replay."""
    for scene in cue_pages(classroom):
        clips = {cue: urlparse(action["audioUrl"]).path for cue, action in cue_speech(scene).items()}
        scene["content"]["html"] = bind_interactive_audio(scene["content"]["html"], clips, classroom_id)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(canonical(value), encoding="utf-8")
    temporary.replace(path)


def assert_no_pending_pronunciation_revision(folder):
    """A profile switch must finish reconciliation before narration can resume."""
    if (folder / 'pronunciation-revision-pending.json').exists():
        raise ApiError('textbook_preview_audio_conflict',
                       '拼音配音版本切换尚未完成，请先恢复已有修订，不能开始配音', 409)


def assert_required_pronunciation_plan(frozen, plan):
    if (pronunciation_registry.initialization_required(frozen)
            and (not isinstance(plan, dict) or plan.get('schemaVersion') != PINYIN_SCHEMA)):
        raise ApiError('textbook_preview_pronunciation_initialization_required',
                       '本课须先冻结已审核的首次拼音配置，不能使用默认配音计划', 409)


def validate_speech_selection(selection, key, classroom):
    """Select exact saved speeches without changing the full lesson's identity."""
    if selection is None:
        return None
    fields = {'schemaVersion', 'previewKey', 'coreSha256', 'speeches'}
    if (not isinstance(selection, dict) or set(selection) != fields
            or selection.get('schemaVersion') != 'mira.textbook.speech-selection.v1'
            or selection.get('previewKey') != key
            or selection.get('coreSha256') != digest(core_content(classroom))
            or not isinstance(selection.get('speeches'), list) or not selection['speeches']):
        raise ApiError('textbook_preview_audio_selection_invalid', '抽样清单必须绑定当前课件及完整内容摘要，并选择非空旁白集合', 409)
    available = [(s.get('id'), a.get('id')) for s in classroom['scenes']
                 for a in s.get('actions', []) if a.get('type') == 'speech']
    selected = set()
    for item in selection['speeches']:
        if (not isinstance(item, dict) or set(item) != {'sceneId', 'actionId'}
                or any(not isinstance(item.get(k), str) or not item[k] for k in ('sceneId', 'actionId'))):
            raise ApiError('textbook_preview_audio_selection_invalid', '抽样条目必须精确指定 sceneId 和 actionId', 409)
        identity = (item['sceneId'], item['actionId'])
        if identity in selected or available.count(identity) != 1:
            raise ApiError('textbook_preview_audio_selection_invalid', '抽样条目重复、缺失或不能唯一匹配已保存旁白', 409)
        selected.add(identity)
    return selected


RETRY_FENCE_FIELDS = {'planSha256', 'coreSha256', 'classroomSha256', 'receiptsSha256'}


def validate_recorded_failure_retry(*, enabled, attempt, fences, selected, selection,
                                    row, plan, plan_path, receipts_path, original):
    """Fence one explicitly authorized next attempt before any runtime call."""
    supplied = enabled or attempt is not None or fences is not None
    if not supplied:
        return None
    if (enabled is not True or type(attempt) is not int or not 2 <= attempt <= 20
            or selected is None or len(selected) != 1
            or not isinstance(fences, dict) or set(fences) != RETRY_FENCE_FIELDS
            or any(re.fullmatch(r'[a-f0-9]{64}', str(fences.get(field))) is None
                   for field in RETRY_FENCE_FIELDS)):
        raise ApiError('textbook_preview_audio_retry_invalid',
                       '失败配音重试必须选择唯一旁白、指定连续的下一次尝试并提供四项摘要', 409)
    if plan is None or not plan_path.is_file() or not receipts_path.is_file():
        raise ApiError('textbook_preview_audio_retry_invalid', '失败配音重试缺少原配音计划或回执', 409)
    actual = {
        'planSha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        'coreSha256': digest(core_content(original)),
        'classroomSha256': row['classroom_sha256'],
        'receiptsSha256': hashlib.sha256(receipts_path.read_bytes()).hexdigest(),
    }
    if (actual != fences or selection.get('coreSha256') != fences['coreSha256']
            or plan.get('coreSha256') != fences['coreSha256'] or digest(plan) != fences['planSha256']):
        raise ApiError('textbook_preview_audio_retry_changed',
                       '失败配音重试的计划、正文、当前课件或历史回执已经变化', 409)
    scene_id, action_id = next(iter(selected))
    action = next(a for s in original['scenes'] if s['id'] == scene_id
                  for a in s.get('actions', []) if a['id'] == action_id)
    historical = json.loads(receipts_path.read_text())
    by_id = {r['requestId']: r for r in historical}
    # A later explicit authorization must not skip a missing, in-flight or
    # successful attempt. Every earlier attempt remains in the receipt chain.
    for prior_attempt in range(1, attempt):
        request = tts_request_id(plan, scene_id, action_id, action['text'].strip(), attempt=prior_attempt)
        if by_id.get(request, {}).get('status') not in {'failed', 'ambiguous'}:
            raise ApiError('textbook_preview_audio_retry_invalid',
                           '前序配音尝试必须连续且全部具有已保存的失败终态', 409)
    return {'attempt': attempt, 'identity': next(iter(selected)), 'fences': deepcopy(fences)}


def confirmed_success_transition(plan, prior, receipt, runtime, classroom):
    """Recover only an unresolved claim whose exact request is now successful."""
    if prior.get('status') not in {'unknown', 'running', 'ambiguous'} or receipt.get('status') != 'succeeded':
        return False
    mutable = {'status', 'audioSha256', 'mimeType'}
    if any(prior[k] != receipt[k] and (k not in mutable or (k != 'status' and prior[k] is not None))
           for k in prior.keys() & receipt.keys()):
        return False
    identity = receipt.get('previewAudioIdentity', {})
    attempt = identity.get('attempt')
    if (type(attempt) is not int or attempt < 1
            or identity != {'planSha256': digest(plan), 'attempt': attempt}
            or not any(receipt['requestId'] == tts_request_id(plan, s['id'], a['id'], a['text'], attempt=attempt)
                       for s in classroom['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech')):
        return False
    try:
        actual = runtime.get_formal_audio_tts(receipt['requestId'], **pronunciation_client_options(plan))
    except OpenMaicFullRuntimeError:
        return False
    return (actual.get('requestId') == receipt['requestId'] and actual.get('status') == 'succeeded'
            and re.fullmatch(r'[a-f0-9]{64}', str(actual.get('audioSha256'))) is not None
            and all(receipt.get(k) == value for k, value in actual.items()))


def preserved_receipts(plan, *sources, confirm_transition=None):
    """Merge DB and crash-checkpoint claims, refusing contradictory evidence."""
    by_id = {}
    for source in sources:
        if not isinstance(source, list):
            raise ApiError('textbook_preview_audio_conflict', '已有配音收据格式无效', 409)
        seen = set()
        for receipt in source:
            request = receipt.get('requestId') if isinstance(receipt, dict) else None
            if not valid_tts_request_id(plan, request) or request in seen:
                raise ApiError('textbook_preview_audio_conflict', '已有配音收据编号无效或重复', 409)
            seen.add(request)
            prior = by_id.get(request, {})
            if (any(prior[k] != receipt[k] for k in prior.keys() & receipt.keys())
                    and not (confirm_transition and confirm_transition(prior, receipt))):
                raise ApiError('textbook_preview_audio_conflict', '数据库与本地配音收据冲突，请先恢复原记录', 409)
            by_id[request] = {**deepcopy(prior), **deepcopy(receipt)}
    return by_id


def segment_request_plan(plan, receipt, folder, *, text):
    """Resolve an archived request plan; a receipt's policy label is never authority."""
    revision = receipt.get('narrationRevisionId')
    if resolve_audio_contract(plan)['legacy'] or revision is None:
        return plan
    if not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{64}', revision):
        raise ApiError('textbook_preview_audio_conflict', '旁白修订编号无效', 409)
    child = json.loads((Path(folder) / 'narration-revisions' / revision / 'plan.json').read_text())
    validate_child_request_plan(plan, child, text=text.strip())
    if child['revisionId'] != revision:
        raise ApiError('textbook_preview_audio_conflict', '旁白修订计划编号不符', 409)
    return child


def verify_segment_receipt(plan, receipt, scene, action, folder, *, inheritance=...):
    """Bind v2 audio to its original request or an archived local amendment.

    previewAudioIdentity is local request metadata, not a provider assertion.
    The immutable plan and deterministic request id independently verify it.
    """
    contract = resolve_audio_contract(plan)
    from services.textbook_operator_revision_service import inherited_evidence, load_inheritance
    if inheritance is ...:
        inheritance = load_inheritance(folder, plan)
    inherited = inherited_evidence(inheritance, plan, scene, action, receipt)
    if inherited is not None:
        return inherited
    if contract['legacy']:
        check_receipt_language_policy(plan, receipt)
        return
    segment_plan = segment_request_plan(plan, receipt, folder, text=action['text'])
    check_receipt_language_policy(segment_plan, receipt)
    check_receipt_pronunciation(segment_plan, receipt, action['text'])
    revision_id = receipt.get('narrationRevisionId')
    identity = receipt.get('previewAudioIdentity', {})
    attempt = identity.get('attempt')
    if (type(attempt) is not int or attempt < 1
            or identity != {'planSha256': digest(segment_plan), 'attempt': attempt}
            or receipt.get('requestId') != tts_request_id(segment_plan, scene['id'], action['id'], action['text'], attempt=attempt)
            or (revision_id is not None and receipt.get('classroomContentSha256') != segment_plan['classroomSha256'])):
        raise ApiError('textbook_preview_audio_conflict', '音频收据不属于本段冻结的配音请求', 409)
    metadata = action.get('audioMetadata', {})
    teacher = contract['teacher']
    if any(metadata.get(k) != v for k, v in {'providerId': teacher['tts']['providerId'],
            'modelId': teacher['tts']['modelId'], 'voiceId': teacher['voiceId'], 'fallbackUsed': False}.items()):
        raise ApiError('textbook_preview_audio_conflict', '讲解音频的声音元数据与配音合同不一致', 409)


def store_audio_result(service, row, saved, receipts, stopped, selection):
    frozen = service.repository.parse(row['input_json'])
    checks = {**(service.repository.parse(row['result_json']) or {}),
              **preview_checks(saved, frozen['previewPrompt']['expectedSceneCount'], frozen.get('originalMedia'),
                               frozen['previewPrompt'].get('expectedQuestionCount', 6))}
    checks.pop('frozenPreview', None)
    by_id = {r['requestId']: r for r in receipts}
    speeches = [a for s in saved['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
    checks.update(audioSeconds=round(sum(r.get('durationSeconds', 0) for r in receipts), 3),
                  audioReceipts=receipts, audioStopCode=stopped,
                  audioPartial=selection is not None or stopped is not None,
                  audioSelection=deepcopy(selection), audioTotal=len(speeches),
                  audioCompleted=sum(by_id.get(a.get('audioId'), {}).get('status') == 'succeeded' for a in speeches))
    with service.repository.transaction() as conn:
        changed = conn.execute('UPDATE learning_textbook_course_previews SET status=?,classroom_json=?,classroom_sha256=?,result_json=?,updated_at=? '
                               'WHERE preview_key=? AND classroom_sha256=? AND status=?',
                               ('review_required' if checks['issues'] or checks['audioPartial'] else 'preview_ready',
                                canonical(saved), digest(saved), canonical(checks), now_ms(), row['preview_key'],
                                row['classroom_sha256'], row['status']))
        if changed.rowcount != 1:
            raise ApiError('textbook_preview_changed', '配音保存前课件记录已改变，已保留断点', 409)
    return service.summary(service.get(row['preview_key']))


def recover_completed_audio_save(service, row, root, original):
    """Reconcile a lost full-save response using the existing audio checkpoint.

    Rebuild only deterministic audio bindings from unchanged content and verified
    WAVs. The actual saved classroom must match exactly; never overwrite it.
    """
    runtime, classroom_id = service.runtime, row['classroom_id']
    folder = root / classroom_id / 'textbook-preview-audio'
    assert_no_pending_pronunciation_revision(folder)
    def fail():
        raise ApiError('textbook_preview_storage_mismatch', '课堂不等于已验证音频断点的唯一绑定结果，请先核对原记录', 409)
    if not folder.is_dir():
        fail()
    with (folder / 'operator.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ApiError('textbook_preview_audio_running', '这节课正在配音，请读取已有任务', 409)
        assert_no_pending_pronunciation_revision(folder)
        try:
            plan = json.loads((folder / 'plan.json').read_text())
            target = json.loads((folder / 'checkpoint.json').read_text())
            checkpoint_receipts = json.loads((folder / 'receipts.json').read_text())
        except (OSError, ValueError):
            fail()
        frozen = service.repository.parse(row['input_json'])
        assert_required_pronunciation_plan(frozen, plan)
        contract = resolve_audio_contract(plan, frozen)
        if contract['legacy']:
            fail()
        if (plan.get('previewKey') != row['preview_key'] or plan.get('coreSha256') != digest(core_content(original))
                or core_content(target) != core_content(original)):
            fail()
        prior = (service.repository.parse(row['result_json']) or {}).get('audioReceipts', [])
        by_id = preserved_receipts(plan, prior, checkpoint_receipts,
            confirm_transition=lambda old, new: confirmed_success_transition(plan, old, new, runtime, original))
        speeches = [(s, a) for s in target['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
        if not 1 <= len(speeches) <= MAX_SPEECH_ACTIONS:
            fail()
        for scene, action in speeches:
            receipt = by_id.get(action.get('audioId'), {})
            if receipt.get('status') != 'succeeded':
                fail()
            verify_segment_receipt(plan, receipt, scene, action, folder)
            request = receipt['requestId']
            asset = root / classroom_id / 'audio' / (request + '.wav')
            if (action.get('audioUrl') != f'{runtime.base_url}/api/classroom-media/{classroom_id}/audio/{request}.wav'
                    or not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != receipt.get('audioSha256')):
                fail()
            if plan.get('schemaVersion') == PINYIN_SCHEMA:
                validate_receipt_wav(receipt, asset.read_bytes())
        bind_question_audio(target)
        bind_cue_audio(target, classroom_id)
        # createdAt is assigned by the runtime on save; every other field,
        # including actions and audio bindings, must equal the reconstruction.
        def saved_content(value):
            return {k: v for k, v in value.items() if k != 'createdAt'}
        disk = json.loads((root / (classroom_id + '.json')).read_text())
        if saved_content(disk) != saved_content(target):
            fail()
        actual = runtime.get_classroom(classroom_id)
        if saved_content(actual) != saved_content(target):
            fail()
        return store_audio_result(service, row, actual, list(by_id.values()), None, None)


def narrate_preview(service, key, classroom_directory, *, speech_selection=None,
                    retry_recorded_failure=False, retry_attempt=None, retry_fences=None,
                    progress=lambda value: None):
    row = service.get(key)
    runtime = service.runtime
    classroom_id = row["classroom_id"]
    if row["status"] not in {"preview_ready", "review_required"} or not classroom_id:
        raise ApiError("textbook_preview_content_required", "请先完成并保存课件，再生成配音", 409)
    if urlparse(runtime.base_url).hostname not in {"127.0.0.1", "localhost", "::1"} or not re.fullmatch(r"[A-Za-z0-9_-]+", classroom_id):
        raise ApiError("textbook_preview_audio_local_only", "此媒体保存工具仅支持本机 OpenMAIC", 409)
    root = Path(classroom_directory).resolve()
    # The operator must point at the actual classroom store, not an arbitrary
    # destination. Confirm content identity before creating any files or calls.
    source_file = root / f"{classroom_id}.json"
    if not source_file.is_file():
        raise ApiError("textbook_preview_storage_mismatch", "没有找到对应的本机课件文件", 409)
    folder = root / classroom_id / "textbook-preview-audio"
    assert_no_pending_pronunciation_revision(folder)
    original = service.repository.parse(row["classroom_json"])
    if digest(original) != row['classroom_sha256']:
        raise ApiError('textbook_preview_storage_mismatch', '数据库课件摘要不一致，请先核对原记录', 409)
    speeches = [a for s in original["scenes"] for a in s.get("actions", []) if a.get("type") == "speech"]
    # Check the complete source before selection, saved-audio reuse or recovery.
    if not 1 <= len(speeches) <= MAX_SPEECH_ACTIONS:
        raise ApiError("textbook_preview_audio_workload", "配音数量或文本范围无效", 409)
    selected = validate_speech_selection(speech_selection, key, original)
    frozen = service.repository.parse(row["input_json"])
    plan_path = folder / "plan.json"
    receipts_path = folder / 'receipts.json'
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else None
    assert_required_pronunciation_plan(frozen, plan)
    retry = validate_recorded_failure_retry(enabled=retry_recorded_failure, attempt=retry_attempt,
        fences=retry_fences, selected=selected, selection=speech_selection, row=row, plan=plan,
        plan_path=plan_path, receipts_path=receipts_path, original=original)
    if core_content(json.loads(source_file.read_text())) != core_content(original):
        if selected is None:
            return recover_completed_audio_save(service, row, root, original)
        raise ApiError("textbook_preview_storage_mismatch", "本机课件内容与数据库快照不一致", 409)
    saved_result = service.repository.parse(row["result_json"]) or {}
    receipts = saved_result.get("audioReceipts", [])
    if plan is not None:
        resolve_audio_contract(plan, frozen)
        if plan['previewKey'] != key:
            raise ApiError("textbook_preview_audio_conflict", "配音计划不属于当前课件", 409)
    from services.textbook_operator_revision_service import load_inheritance
    inheritance = load_inheritance(folder, plan, frozen=frozen) if plan is not None else None
    if frozen.get('operatorRevision') and inheritance is None:
        raise ApiError('textbook_preview_audio_conflict', '修订预览必须有独立计划和父来源证据', 409)
    if selected is None and row["status"] == "preview_ready" and receipts:
        if plan is None:
            raise ApiError("textbook_preview_audio_conflict", "已完成配音缺少原始计划", 409)
        by_id = {r["requestId"]: r for r in receipts}
        used = [a.get("audioId") for a in speeches]
        superseded = {request for revision in saved_result.get("narrationRevisions", [])
                      if revision.get("sha256") == digest({k: v for k, v in revision.items() if k != "sha256"})
                      for request in revision.get("supersededTtsRequestIds", [])}
        # A stalled or refused first attempt keeps its receipt beside the attempt that was used.
        if all(u in by_id for u in used) and all(r["status"] in ("ambiguous", "failed") or i in superseded for i, r in by_id.items() if i not in used):
            if any(not valid_tts_request_id(plan, request_id) for request_id in by_id):
                raise ApiError("textbook_preview_audio_invalid", "音频记录编号无效", 409)
            for request_id in used:
                if by_id[request_id]['status'] != 'succeeded':
                    raise ApiError("textbook_preview_audio_invalid", "当前语音未成功", 409)
                asset = root / classroom_id / "audio" / (request_id + ".wav")
                if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != by_id[request_id]["audioSha256"]:
                    raise ApiError("textbook_preview_audio_asset_missing", "已完成的配音文件缺失或变化，请从原音频记录恢复", 409)
                if plan.get('schemaVersion') == PINYIN_SCHEMA:
                    validate_receipt_wav(by_id[request_id], asset.read_bytes())
            for scene in original['scenes']:
                for action in scene.get('actions', []):
                    if action.get('type') == 'speech':
                        verify_segment_receipt(plan, by_id[action['audioId']], scene, action, folder, inheritance=inheritance)
            return service.summary(row)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "operator.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ApiError("textbook_preview_audio_running", "这节课正在配音，请读取已有任务", 409)
        assert_no_pending_pronunciation_revision(folder)
        if retry is not None:
            current_row = service.get(key)
            current_original = service.repository.parse(current_row['classroom_json'])
            validate_recorded_failure_retry(enabled=True, attempt=retry['attempt'], fences=retry['fences'],
                selected=selected, selection=speech_selection, row=current_row, plan=json.loads(plan_path.read_text()),
                plan_path=plan_path, receipts_path=receipts_path, original=current_original)
            if (current_row['status'] != row['status'] or current_row['input_json'] != row['input_json']
                    or current_original != original):
                raise ApiError('textbook_preview_audio_retry_changed',
                               '失败配音重试锁定后课件数据库快照发生变化', 409)
            row = current_row
        classroom = runtime.get_classroom(classroom_id)
        if core_content(classroom) != core_content(original):
            raise ApiError("textbook_preview_changed", "课件已被编辑，请先核对音频任务", 409)
        # A page whose cues cannot be bound must stop before any paid speech.
        for scene in cue_pages(classroom):
            cue_speech(scene)
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            assert_required_pronunciation_plan(frozen, plan)
            resolve_audio_contract(plan, frozen)
            if plan["previewKey"] != key or plan["coreSha256"] != digest(core_content(classroom)):
                raise ApiError("textbook_preview_audio_conflict", "已冻结的配音内容或声音身份不一致", 409)
        else:
            assert_required_pronunciation_plan(frozen, None)
            plan = new_audio_plan(preview_key=key, classroom_sha256=row["classroom_sha256"],
                                  core_sha256=digest(core_content(classroom)), frozen_input=frozen)
            atomic_json(plan_path, plan)
        contract = resolve_audio_contract(plan, frozen)
        client_options = pronunciation_client_options(plan)
        teacher = contract['teacher']
        workload = [(scene, action) for scene in classroom["scenes"] for action in scene.get("actions", []) if action.get("type") == "speech"]
        # Operator lessons also read every in-page cue aloud, one line each.
        if not 1 <= len(workload) <= MAX_SPEECH_ACTIONS or any(not a.get("text", "").strip() or len(a["text"]) > 4000 for _, a in workload):
            raise ApiError("textbook_preview_audio_workload", "配音数量或文本范围无效", 409)
        if plan.get('schemaVersion') == PINYIN_SCHEMA:
            # Validate every future segment before even a selected sample is paid.
            for _, action in workload:
                pronunciation_identity(action['text'].strip(), policy_version=policy_for_plan(plan)['policyVersion'])
        try:
            checkpoint_receipts = json.loads(receipts_path.read_text()) if receipts_path.exists() else []
        except (OSError, ValueError) as exc:
            raise ApiError('textbook_preview_audio_conflict', '无法读取已有配音收据，请先恢复原记录', 409) from exc
        receipt_index = preserved_receipts(plan, receipts, checkpoint_receipts,
            confirm_transition=lambda prior, receipt: confirmed_success_transition(plan, prior, receipt, runtime, classroom))
        receipts, stopped = list(receipt_index.values()), None
        reuse_saved_audio = selected is not None or saved_result.get('audioPartial') is True
        audio_dir = root / classroom_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        retry_target = None
        if retry is not None:
            identity = retry['identity']
            matches = [(scene, action) for scene, action in workload
                       if (scene['id'], action['id']) == identity]
            if len(matches) != 1 or (inheritance and identity in inheritance['segments']):
                raise ApiError('textbook_preview_audio_retry_invalid', '重试旁白不存在、重复或属于继承音频', 409)
            retry_scene, retry_action = matches[0]
            if retry_action.get('audioId'):
                raise ApiError('textbook_preview_audio_retry_invalid', '已有绑定音频的旁白不能再发起失败重试', 409)
            prior_request = tts_request_id(plan, retry_scene['id'], retry_action['id'],
                                           retry_action['text'].strip(), attempt=retry['attempt'] - 1)
            prior = receipt_index.get(prior_request)
            if not isinstance(prior, dict) or prior.get('status') not in {'failed', 'ambiguous'}:
                raise ApiError('textbook_preview_audio_retry_invalid',
                               '前一次配音必须有明确保存的 failed 或 ambiguous 终态', 409)
            request = tts_request_id(plan, retry_scene['id'], retry_action['id'],
                                     retry_action['text'].strip(), attempt=retry['attempt'])
            if request in receipt_index:
                raise ApiError('textbook_preview_audio_retry_invalid', '目标尝试已有本地回执，不能再次派发', 409)
            retry_target = {'requestId': request, 'priorRequestId': prior_request,
                            'priorStatus': prior['status'], 'sceneId': retry_scene['id'],
                            'actionId': retry_action['id'], 'attempt': retry['attempt']}

        def remember(receipt):
            receipt_index[receipt['requestId']] = deepcopy(receipt)
            receipts[:] = receipt_index.values()
            atomic_json(receipts_path, receipts)

        def dispatch_recorded_retry(scene, action, text):
            request_id = retry_target['requestId']
            try:
                runtime.get_formal_audio_tts(request_id, **client_options)
            except OpenMaicFullRuntimeError as exc:
                if exc.status_code != 404:
                    raise
            else:
                raise ApiError('textbook_preview_audio_retry_target_exists',
                               '目标尝试在运行端已经存在，只能先核对，不能再次派发', 409)
            claim_dir = folder / 'retry-claims'
            claim_path = claim_dir / (request_id + '.json')
            if claim_path.exists() or request_id in receipt_index:
                raise ApiError('textbook_preview_audio_retry_invalid', '目标尝试已经声明，不能再次派发', 409)
            identity = {'planSha256': digest(plan), 'attempt': retry['attempt']}
            remember({'requestId': request_id, 'status': 'unknown', 'audioSha256': None,
                      'previewAudioIdentity': identity})
            claim = {'schemaVersion': 'mira.textbook.preview-audio-retry-claim.v1',
                     'previewKey': key, 'classroomId': classroom_id, **retry_target,
                     'textSha256': hashlib.sha256(text.encode()).hexdigest(),
                     'fences': deepcopy(retry['fences']), 'claimedAt': now_ms()}
            claim['sha256'] = digest(claim)
            claim_dir.mkdir(parents=True, exist_ok=True)
            with claim_path.open('x', encoding='utf-8') as handle:
                handle.write(canonical(claim))
            return runtime.start_formal_audio_tts(
                request_id=request_id, classroom_id=classroom_id,
                classroom_content_sha256=plan["classroomSha256"], subject=contract['subject'],
                teacher_profile_id=teacher['teacherProfile']['id'],
                teacher_profile_version=teacher['teacherProfile']['version'],
                teacher_profile_sha256=teacher['teacherProfile']['contentHash'],
                teacher_gender=teacher['teacherGender'], scene_id=scene['id'], scene_order=scene['order'],
                action_id=action['id'], narration_segment_id=action['id'], text=text,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(), **client_options), True

        def speak(request_id, scene, action, text):
            """The durable receipt for one request id, and whether this call created it."""
            try:
                return runtime.get_formal_audio_tts(request_id, **client_options), False
            except OpenMaicFullRuntimeError as exc:
                if exc.status_code != 404:
                    raise
            # A missing server record does not make a locally claimed request
            # safe to dispatch again, including unknown/crash outcomes.
            if request_id in receipt_index:
                return deepcopy(receipt_index[request_id]), False
            # Keep an explicit local claim before dispatch. A transport timeout
            # can hide a paid provider outcome; a later 404 must not erase it.
            remember({'requestId': request_id, 'status': 'unknown', 'audioSha256': None})
            return runtime.start_formal_audio_tts(
                request_id=request_id, classroom_id=classroom_id,
                classroom_content_sha256=plan["classroomSha256"], subject=contract['subject'],
                teacher_profile_id=teacher['teacherProfile']['id'], teacher_profile_version=teacher['teacherProfile']['version'],
                teacher_profile_sha256=teacher['teacherProfile']['contentHash'], teacher_gender=teacher['teacherGender'],
                scene_id=scene["id"], scene_order=scene["order"], action_id=action["id"],
                narration_segment_id=action["id"], text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                **client_options), True

        for index, (scene, action) in enumerate(workload, 1):
            if selected is not None and (scene['id'], action['id']) not in selected:
                continue
            text = action["text"].strip()
            request_id = tts_request_id(plan, scene['id'], action['id'], text)
            try:
                if inheritance and (scene['id'], action['id']) in inheritance['segments']:
                    saved = inheritance['segments'][(scene['id'], action['id'])]
                    receipt = next(r for r in inheritance['parent']['receipts'] if r['requestId'] == saved['ttsRequestId'])
                    verify_segment_receipt(plan, receipt, scene, action, folder, inheritance=inheritance)
                    asset = audio_dir / (saved['ttsRequestId'] + '.wav')
                    if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != saved['audioSha256']:
                        raise ApiError('textbook_preview_audio_asset_missing', '继承的原音频副本缺失或变化', 409)
                    if plan.get('schemaVersion') == PINYIN_SCHEMA:
                        validate_receipt_wav(receipt, asset.read_bytes())
                    # Keep the original receipt byte-equivalent. The separate
                    # provenance binds it; no provider call or relabelled id.
                    remember(receipt)
                    atomic_json(folder / 'checkpoint.json', classroom)
                    progress({'completedAudio': index, 'totalAudio': len(workload), 'inherited': True})
                    continue
                if retry is not None:
                    request_id = retry_target['requestId']
                    attempt = retry['attempt']
                    receipt, created = dispatch_recorded_retry(scene, action, text)
                else:
                    prior = receipt_index.get(action.get('audioId') or request_id)
                    if reuse_saved_audio and prior and prior.get('status') == 'succeeded':
                        receipt, created = deepcopy(prior), False
                        request_id = receipt['requestId']
                        attempt = receipt.get('previewAudioIdentity', {}).get('attempt', 1)
                        if action.get('audioId'):
                            verify_segment_receipt(plan, receipt, scene, action, folder, inheritance=inheritance)
                    else:
                        receipt, created = speak(request_id, scene, action, text)
                        attempt = 1
                calls = int(created)
                # A stalled or refused provider call is never sent again under
                # its own id: the next attempt gets a new, recorded id. Earlier
                # attempts are read back, and one run sends at most two calls
                # for a line, so a provider hiccup (or a lapsed account that is
                # topped up before the next run) does not stop a whole lesson.
                # The pinyin lane requires explicit reconciliation after any
                # failure; changing its id must not silently pay a second time.
                while (plan.get('schemaVersion') != PINYIN_SCHEMA and selected is None
                       and not (inheritance and inheritance['candidate'].get('completeSceneEvidence'))
                       and receipt["status"] in ("ambiguous", "failed") and calls < 2):
                    remember(receipt)
                    attempt += 1
                    request_id = tts_request_id(plan, scene['id'], action['id'], text, attempt=attempt)
                    receipt, created = speak(request_id, scene, action, text)
                    calls += created
                if receipt["status"] != "succeeded":
                    remember(receipt)
                    stopped = "textbook_preview_audio_" + receipt["status"]
                    break
                check_receipt_language_policy(plan, receipt)
                if not contract['legacy']:
                    receipt = {**receipt, 'previewAudioIdentity': receipt.get('previewAudioIdentity') or
                               {'planSha256': digest(plan), 'attempt': attempt}}
                # Persist provider success before a download or save can fail.
                remember(receipt)
                filename = request_id + ".wav"
                target = audio_dir / filename
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == receipt["audioSha256"]:
                    audio = target.read_bytes()
                else:
                    audio = runtime.download_formal_audio_tts(request_id, expected_sha256=receipt["audioSha256"])
                if plan.get('schemaVersion') == PINYIN_SCHEMA:
                    validate_receipt_wav(receipt, audio)
                with wave.open(io.BytesIO(audio), "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate()
                    if duration <= 0:
                        raise ValueError("Empty audio")
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(audio)
                temporary.replace(target)
                action.update(audioId=request_id, audioUrl=f"{runtime.base_url}/api/classroom-media/{classroom_id}/audio/{filename}",
                              audioMetadata={"schemaVersion": "mira.openmaic.speech-audio.v1", "providerId": teacher['tts']['providerId'],
                                             "modelId": teacher['tts']['modelId'], "voiceId": teacher['voiceId'], "fallbackUsed": False})
                verify_segment_receipt(plan, receipt, scene, action, folder, inheritance=inheritance)
                remember({**receipt, "durationSeconds": round(duration, 3)})
                atomic_json(folder / "checkpoint.json", classroom)
                progress({"completedAudio": index, "totalAudio": len(workload)})
            except (OpenMaicFullRuntimeError, OSError, ValueError) as exc:
                stopped = getattr(exc, "code", "textbook_preview_audio_invalid")
                break
        # Do not overwrite an independently edited classroom. A lost publish
        # response is reconciled against content on the next operator run.
        current = runtime.get_classroom(classroom_id)
        if core_content(current) != core_content(classroom):
            raise ApiError("textbook_preview_changed", "配音过程中课件被编辑，已保留音频且停止覆盖", 409)
        if not stopped and selected is None:
            bind_question_audio(classroom, inheritance=inheritance)
            bind_cue_audio(classroom, classroom_id)
        runtime.save_preview_classroom(classroom)
        saved = runtime.get_classroom(classroom_id)
        if core_content(saved) != core_content(classroom):
            raise ApiError("textbook_preview_changed", "保存后的课件内容不一致", 409)
        return store_audio_result(service, row, saved, receipts, stopped, speech_selection)
