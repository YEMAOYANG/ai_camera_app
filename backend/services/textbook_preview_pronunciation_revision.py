"""Provider-free, recoverable audio-profile rotation of an unpublished partial preview.

Old successful provider receipts remain successful. The amendment rejects their
pronunciation for this lesson, archives their bytes, and starts an empty plan.
It never imports probe audio as formal audio or invokes a provider.
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
from content.textbook_interactive_narration import AUDIO_SCRIPT
from content.textbook_preview_audio_contract import MAX_SPEECH_ACTIONS, resolve_audio_contract, tts_request_id
from core.errors import ApiError
from services.textbook_preview_revision_transaction import PreviewRevisionTransaction
from services.course_file_store import course_bytes, course_exists
from core.security import now_ms
from services.textbook_preview_audio import (atomic_json, bind_cue_audio, bind_question_audio,
    core_content, verify_segment_receipt)
from services.textbook_preview_visual_revision import immutable, json_bytes, persisted, sha_bytes

SCHEMA = 'mira.textbook.preview-pronunciation-revision.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')
PENDING = 'pronunciation-revision-pending.json'
AUDIO_FIELDS = ('audioId', 'audioUrl', 'audioMetadata')
PROBES = {'e-base': 'e1', 'a-tone-2': 'a2', 'o-tone-2': 'o2', 'e-tone-2': 'e2'}


def fail(message):
    raise ApiError('textbook_preview_pronunciation_revision_conflict', message, 409)


def _json(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        fail('修订证据不是有效 JSON')


def validate_patch(patch):
    fields = {'schemaVersion', 'expectedSourceSha256', 'parentPlanSha256', 'reviewer', 'basis',
              'humanFeedback', 'approvedProbeEvidence'}
    if (not isinstance(patch, dict) or set(patch) != fields or patch['schemaVersion'] != SCHEMA
            or any(not SHA.fullmatch(str(patch[k])) for k in ('expectedSourceSha256', 'parentPlanSha256'))
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))):
        fail('需要原课件与配音计划摘要、审核人、依据和两份真实听验证据')
    for key in ('humanFeedback', 'approvedProbeEvidence'):
        item = patch[key]
        if (not isinstance(item, dict) or set(item) != {'path', 'sha256'}
                or not isinstance(item['path'], str) or not item['path']
                or not SHA.fullmatch(str(item['sha256']))):
            fail('听验证据必须指定文件及原字节摘要')


def _read_evidence(item):
    raw = course_bytes(Path(item['path']))
    if sha_bytes(raw) != item['sha256']:
        fail('听验证据原字节已变化')
    return raw, _json(raw)


def _speech(source):
    result = {}
    for scene in source['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') == 'speech':
                key = (scene['id'], action['id'])
                if key in result:
                    fail('旁白身份重复')
                result[key] = (scene, action)
    if not 1 <= len(result) <= MAX_SPEECH_ACTIONS:
        fail('旁白数量无效')
    return result


def _pcm(raw):
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            frames = wav.readframes(wav.getnframes())
            if (not frames or wav.getcomptype() != 'NONE' or wav.getframerate() <= 0
                    or len(frames) % (wav.getnchannels() * wav.getsampwidth())):
                fail('音频没有有效 PCM 数据')
            return (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), frames
    except (wave.Error, EOFError):
        fail('原音频不是有效 WAV')


def _evidence(patch, key, source, receipts, *, source_files=None):
    """Validate the two existing human-feedback schemas without rewriting them."""
    if source_files is None:
        reject_raw, rejected = _read_evidence(patch['humanFeedback'])
        approve_raw, approved = _read_evidence(patch['approvedProbeEvidence'])
    else:
        reject_raw, approve_raw = (source_files[name] for name in ('human-feedback.json', 'approved-probes.json'))
        if (sha_bytes(reject_raw) != patch['humanFeedback']['sha256']
                or sha_bytes(approve_raw) != patch['approvedProbeEvidence']['sha256']):
            fail('归档听验证据原字节已变化')
        rejected, approved = _json(reject_raw), _json(approve_raw)
    if (rejected.get('schemaVersion') != 'mira.textbook.phonetic-human-feedback.v1'
            or rejected.get('previewKey') != key or rejected.get('publicationAllowed') is not False
            or rejected.get('fullNarrationOnHold') is not True or not rejected.get('reviewer')
            or not rejected.get('receivedAt') or not rejected.get('statements') or not rejected.get('scope')
            or not isinstance(rejected.get('samples'), list) or not rejected['samples']):
        fail('需要绑定本课的明确人工发音拒绝证据')
    actions, by_id, seen = _speech(source), {r['requestId']: r for r in receipts}, set()
    for sample in rejected['samples']:
        identity = (sample.get('sceneId'), sample.get('actionId'))
        if identity not in actions or identity in seen:
            fail('人工拒绝样本不能唯一对应本课旁白')
        seen.add(identity)
        action = actions[identity][1]
        receipt = by_id.get(sample.get('receiptRequestId'), {})
        if (action.get('audioId') != sample.get('receiptRequestId')
                or sample.get('audioSha256') != receipt.get('audioSha256')
                or not isinstance(sample.get('findings'), list) or not sample['findings']
                or any(not isinstance(v, str) or not v.strip() for v in sample['findings'])):
            fail('人工拒绝证据与原成功音频不一致')
    if (approved.get('schemaVersion') != 'mira.operator.phonetic-human-feedback.v1'
            or approved.get('result') != 'four_ssml_probes_pronunciation_approved'
            or approved.get('model') != 'cosyvoice-v3-flash' or approved.get('voice') != 'longanwen_v3'
            or approved.get('formalUseAllowed') is not False or not approved.get('reviewer')
            or not approved.get('receivedAt') or not isinstance(approved.get('samples'), list)
            or len(approved['samples']) != 4
            or {s.get('label') for s in approved['samples']} != set(PROBES)):
        fail('需要四个固定 SSML 小样的人工认可证据，不能当作正式音频通过')
    files = {'human-feedback.json': reject_raw, 'approved-probes.json': approve_raw}
    base = Path(patch['approvedProbeEvidence']['path']).resolve().parent
    for sample in approved['samples']:
        label = sample['label']
        raws = {name: (course_bytes(base / label / name) if source_files is None
                       else source_files[f'probes/{label}/{name}']) for name in
                ('request.json', 'intent.json', 'receipt.json', 'playback-validation.json', 'audio.wav', 'playback.wav')}
        request, intent, receipt, validation = (_json(raws[n]) for n in
                ('request.json', 'intent.json', 'receipt.json', 'playback-validation.json'))
        if (sample.get('result') != 'approved_by_human_listening' or sample.get('phoneme') != PROBES[label]
                or sha_bytes(raws['request.json']) != sample.get('requestSha256')
                or request.get('model') != approved['model'] or request.get('input', {}).get('voice') != approved['voice']
                or request['input'].get('enable_ssml') is not True
                or f'ph="{PROBES[label]}"' not in request['input'].get('text', '')
                or intent.get('requestSha256') != sample.get('requestSha256')
                or intent.get('formalUseAllowed') is not False or receipt.get('formalUseAllowed') is not False
                or receipt.get('status') != 'succeeded' or receipt.get('model') != approved['model']
                or receipt.get('voice') != approved['voice'] or receipt.get('phoneme') != PROBES[label]
                or any(receipt.get(k) != sample.get(k) for k in ('requestSha256', 'providerRequestId', 'pcmSha256'))
                or not sample.get('providerRequestId')
                or sha_bytes(raws['audio.wav']) != sample.get('providerAudioSha256')
                or receipt.get('audioSha256') != sample.get('providerAudioSha256')
                or sha_bytes(raws['playback.wav']) != sample.get('playbackSha256')
                or validation.get('schemaVersion') != 'mira.operator.audio-container-validation.v1'
                or validation.get('pcmChanged') is not False or validation.get('formalUseAllowed') is not False
                or any(validation.get(k) != sample.get(k) for k in ('providerAudioSha256', 'playbackSha256', 'pcmSha256'))):
            fail('认可小样的请求、回执或音频身份不一致')
        original_format, original_pcm = _pcm(raws['audio.wav'])
        playback_format, playback_pcm = _pcm(raws['playback.wav'])
        if (original_format != playback_format or original_pcm != playback_pcm
                or sha_bytes(original_pcm) != sample['pcmSha256']):
            fail('认可小样的原始及播放 PCM 不一致')
        files.update({f'probes/{label}/{name}': raw for name, raw in raws.items()})
    return files


def _unpublished(service, conn, row, key):
    builds = conn.execute("SELECT input_json FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=? AND status='published'",
                          (row['edition_id'], row['node_id'])).fetchall()
    if any(service.repository.parse(b['input_json']).get('previewKey') == key for b in builds):
        fail('已发布预览不能旋转音频计划')


def _verify_parent(source, result, plan, folder, root, cid):
    if (result.get('audioPartial') is not True or result.get('audioStopCode')
            or resolve_audio_contract(plan)['legacy'] or plan.get('subject') != 'chinese'):
        fail('仅支持没有未决调用的中文部分配音预览')
    for scene in source['scenes']:
        if AUDIO_SCRIPT in str(scene.get('content', {}).get('html', '')):
            fail('首版不旋转已绑定互动音频的课件')
        if any('questionAudioUrl' in q for q in scene.get('content', {}).get('questions', [])):
            fail('首版不旋转已绑定测验音频的课件')
    receipts = result.get('audioReceipts')
    if (not isinstance(receipts, list) or not receipts
            or len({r.get('requestId') for r in receipts}) != len(receipts)
            or any(r.get('status') != 'succeeded' for r in receipts)):
        fail('所有已有配音回执必须明确成功；失败、未知或冲突记录须先恢复')
    actions = _speech(source)
    used = {a.get('audioId'): (s, a) for s, a in actions.values() if a.get('audioId')}
    if (len(used) >= len(actions) or len(used) != sum(bool(a.get('audioId')) for _, a in actions.values())
            or set(used) != {r['requestId'] for r in receipts}):
        fail('仅支持所有已成功回执均准确绑定的部分配音')
    wavs = {}
    for receipt in receipts:
        request = receipt['requestId']
        scene, action = used[request]
        verify_segment_receipt(plan, receipt, scene, action, folder)
        if urlparse(action.get('audioUrl', '')).path != f'/api/classroom-media/{cid}/audio/{request}.wav':
            fail('原音频绑定路径不一致')
        raw = course_bytes(root / cid / 'audio' / (request + '.wav'))
        if sha_bytes(raw) != receipt.get('audioSha256'):
            fail('原成功 WAV 摘要变化')
        _pcm(raw)
        wavs[request + '.wav'] = sha_bytes(raw)
    return wavs


def _archive_verify(archive, intent, root, cid):
    if intent.get('sha256') != digest({k: v for k, v in intent.items() if k != 'sha256'}):
        fail('修订意图摘要变化')
    for name, sha in intent['files'].items():
        if sha_bytes(course_bytes(archive / name)) != sha:
            fail('不可变归档内容变化')
    for name, sha in intent['parentWavs'].items():
        if sha_bytes(course_bytes(root / cid / 'audio' / name)) != sha:
            fail('原 WAV 缺失或变化')


def _completed(service, row, folder, root, cid, target, plan, amendment):
    """A rerun may observe later narration, but must never reset it."""
    result = service.repository.parse(row['result_json'])
    matches = [v for v in result.get('pronunciationRevisions', []) if v.get('revisionId') == amendment['revisionId']]
    if not matches:
        return False
    if matches != [amendment] or _json(course_bytes(folder / 'plan.json')) != plan:
        fail('已完成修订的来源或活动计划变化')
    current = service.runtime.get_classroom(cid)
    if (digest(current) != row['classroom_sha256'] or current != service.repository.parse(row['classroom_json'])
            or _json(course_bytes(root / (cid + '.json'))) != current):
        fail('已完成修订的运行、文件和数据库快照不一致')
    receipts = result.get('audioReceipts', [])
    if _json(course_bytes(folder / 'receipts.json')) != receipts:
        fail('已完成修订的活动回执不一致')
    by_id = {v['requestId']: v for v in receipts}
    if len(by_id) != len(receipts):
        fail('活动回执重复')
    rebuilt = deepcopy(target)
    actions = _speech(current)
    for item in receipts:
        identity = item.get('previewAudioIdentity', {})
        attempt = identity.get('attempt', 1)
        if (type(attempt) is not int or attempt < 1
                or item.get('status') not in {'succeeded', 'unknown', 'failed', 'ambiguous'}
                or (identity and identity != {'planSha256': digest(plan), 'attempt': attempt})
                or not any(item['requestId'] == tts_request_id(plan, s['id'], a['id'], a['text'], attempt=attempt)
                           for s, a in actions.values())):
            fail('新版本回执不属于当前冻结计划')
    for identity, (scene, action) in _speech(rebuilt).items():
        actual = actions.get(identity, ({}, {}))[1]
        for field in AUDIO_FIELDS:
            if field in actual:
                action[field] = deepcopy(actual[field])
        if action.get('audioId'):
            receipt = by_id.get(action['audioId'], {})
            if receipt.get('status') != 'succeeded':
                fail('新版本音频绑定缺少成功回执')
            verify_segment_receipt(plan, receipt, scene, action, folder)
            asset = root / cid / 'audio' / (action['audioId'] + '.wav')
            if (action.get('audioUrl') != f'{service.runtime.base_url}/api/classroom-media/{cid}/audio/{action["audioId"]}.wav'
                    or sha_bytes(course_bytes(asset)) != receipt.get('audioSha256')):
                fail('新版本 WAV 摘要变化')
            from content.textbook_pinyin_pronunciation import validate_receipt_wav
            validate_receipt_wav(receipt, course_bytes(asset))
    if persisted(_json(course_bytes(folder / 'checkpoint.json'))) != persisted(rebuilt):
        fail('新版本断点与已保存的音频绑定不一致')
    if any(AUDIO_SCRIPT in str(s.get('content', {}).get('html', '')) for s in current['scenes']):
        bind_question_audio(rebuilt)
        bind_cue_audio(rebuilt, cid)
    if persisted(rebuilt) != persisted(current):
        fail('修订后的课件包含非音频内容差异')
    return True


def revise_preview_pronunciation(service, key, classroom_directory, patch, *, execute=False):
    validate_patch(patch)
    row = service.get(key)
    cid, root = row['classroom_id'], Path(classroom_directory).resolve()
    if (urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}
            or not re.fullmatch(r'[A-Za-z0-9_-]+', cid or '')):
        fail('只支持本机已保存的未发布预览')
    folder = root / cid / 'textbook-preview-audio'
    revision_id = digest({'previewKey': key, 'patch': patch})
    archive = folder / 'pronunciation-revisions' / revision_id
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'operator.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('课件正在配音或修订')
        with PreviewRevisionTransaction(service.repository, key, fail, root / (cid + '.json')) as conn:
            row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (key,)).fetchone()
            if row['classroom_id'] != cid or row['runtime_origin'] != service.runtime.base_url:
                fail('预览运行身份变化')
            _unpublished(service, conn, row, key)
            conn.release(row)
            intent_path = archive / 'intent.json'
            if not course_exists(intent_path):
                if course_exists(folder / PENDING):
                    fail('另一个音频版本修订尚未完成')
                source = service.repository.parse(row['classroom_json'])
                result = service.repository.parse(row['result_json'])
                frozen = service.repository.parse(row['input_json'])
                raw_plan = course_bytes(folder / 'plan.json')
                plan = _json(raw_plan)
                resolve_audio_contract(plan, frozen)
                if (row['status'] != 'review_required' or digest(source) != patch['expectedSourceSha256']
                        or row['classroom_sha256'] != digest(source) or digest(plan) != patch['parentPlanSha256']
                        or plan['previewKey'] != key or plan['coreSha256'] != digest(core_content(source))):
                    fail('原预览或计划摘要已变化')
                original_file = course_bytes(root / (cid + '.json'))
                checkpoint = course_bytes(folder / 'checkpoint.json')
                raw_receipts = course_bytes(folder / 'receipts.json')
                if (service.runtime.get_classroom(cid) != source or _json(original_file) != source
                        or persisted(_json(checkpoint)) != persisted(source)
                        or _json(raw_receipts) != result.get('audioReceipts')):
                    fail('原运行、断点、回执、文件和数据库未同步')
                wavs = _verify_parent(source, result, plan, folder, root, cid)
                evidence = _evidence(patch, key, source, result['audioReceipts'])
                target = deepcopy(source)
                for _, action in _speech(target).values():
                    for field in AUDIO_FIELDS:
                        action.pop(field, None)
                from content.textbook_preview_audio_contract import new_pinyin_audio_plan
                new_plan = new_pinyin_audio_plan(preview_key=key, classroom_sha256=digest(target),
                    core_sha256=digest(core_content(target)), frozen_input=frozen, parent_plan=plan, revision_id=revision_id)
                files = {'parent/plan.json': raw_plan, 'parent/receipts.json': raw_receipts,
                         'parent/checkpoint.json': checkpoint, 'parent/classroom-file.json': original_file,
                         'parent/row.json': json_bytes(row), 'parent/classroom.json': row['classroom_json'].encode(),
                         'parent/result.json': row['result_json'].encode(), 'parent/input.json': row['input_json'].encode(),
                         'target.json': json_bytes(target), 'plan.json': json_bytes(new_plan),
                         **{'parent/' + name: raw for name, raw in evidence.items()}}
                for name, raw in files.items():
                    path = archive / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    immutable(path, raw)
                intent = {'schemaVersion': SCHEMA, 'revisionId': revision_id, 'previewKey': key,
                          'classroomId': cid, 'patch': patch, 'files': {n: sha_bytes(v) for n, v in files.items()},
                          'parentWavs': wavs}
                intent['sha256'] = digest(intent)
                immutable(intent_path, json_bytes(intent))
            intent = _json(course_bytes(intent_path))
            if intent.get('patch') != patch or intent.get('revisionId') != revision_id or intent.get('previewKey') != key:
                fail('修订意图身份不一致')
            _archive_verify(archive, intent, root, cid)
            source_row = _json(course_bytes(archive / 'parent/row.json'))
            if any(row[k] != source_row[k] for k in ('input_json', 'edition_id', 'revision_id', 'node_id')):
                fail('教材或冻结输入已改变')
            source = _json(course_bytes(archive / 'parent/classroom.json'))
            target, plan = (_json(course_bytes(archive / name)) for name in ('target.json', 'plan.json'))
            pending = json_bytes({'revisionId': revision_id, 'intentSha256': intent['sha256']})
            pending_path = folder / PENDING
            if course_exists(pending_path) and course_bytes(pending_path) != pending:
                fail('另一个音频版本修订尚未完成')
            commit_path = archive / 'amendment.json'
            amendment = _json(course_bytes(commit_path)) if course_exists(commit_path) else None
            if amendment and (amendment.get('sha256') != digest({k: v for k, v in amendment.items() if k != 'sha256'})
                    or amendment.get('intentSha256') != intent['sha256']
                    or amendment.get('revisionId') != revision_id or amendment.get('previewKey') != key
                    or amendment.get('audioPlanSha256') != digest(plan)
                    or amendment.get('sourceSha256') != patch['expectedSourceSha256']
                    or amendment.get('parentPlanSha256') != patch['parentPlanSha256']):
                fail('修订完成凭据摘要或身份变化')
            if amendment and _completed(service, row, folder, root, cid, target, plan, amendment):
                if execute and pending_path.exists():
                    pending_path.unlink()
                return amendment
            if any(row[k] != source_row[k] for k in ('classroom_json', 'classroom_sha256', 'result_json', 'input_json', 'status', 'updated_at')):
                fail('数据库已被其他任务修改，不能覆盖')
            current = service.runtime.get_classroom(cid)
            disk = _json(course_bytes(root / (cid + '.json')))
            if current != disk or (current != source and persisted(current) != persisted(target)):
                fail('运行课件存在无关变化')
            # Check all mutable files before the first save, not after it. Only
            # this intent's pending marker permits a partially completed swap.
            for name, new_raw in {'plan.json': course_bytes(archive / 'plan.json'),
                                  'receipts.json': json_bytes([]), 'checkpoint.json': json_bytes(current)}.items():
                allowed = {course_bytes(archive / 'parent' / name)}
                if course_exists(pending_path):
                    allowed.add(new_raw)
                if course_bytes(folder / name) not in allowed:
                    fail('活动计划、回执或断点已由其他任务改变')
            if not execute:
                return {'prepared': True, 'revisionId': revision_id, 'archive': str(archive),
                        'parentAudioCount': len(intent['parentWavs']), 'generationDispatched': False}
            immutable(pending_path, pending)
            marker = archive / 'save-attempt.json'
            if current == source:
                if course_exists(marker):
                    fail('保存结果未知且未读到唯一目标，禁止自动重发')
                immutable(marker, json_bytes({'intentSha256': intent['sha256'], 'attemptedAt': now_ms()}))
                service.runtime.save_preview_classroom(target)
                current = service.runtime.get_classroom(cid)
            elif not course_exists(marker):
                fail('没有本修订保存意图，不能接纳外部目标快照')
            if persisted(current) != persisted(target) or _json(course_bytes(root / (cid + '.json'))) != current:
                fail('保存后读回不等于唯一音频清空目标')
            immutable(archive / 'saved.json', json_bytes(current))
            replacements = {'plan.json': course_bytes(archive / 'plan.json'),
                            'receipts.json': json_bytes([]), 'checkpoint.json': json_bytes(current)}
            for name, raw in replacements.items():
                if course_bytes(folder / name) not in {course_bytes(archive / 'parent' / name), raw}:
                    fail('活动计划、回执或断点被其他任务修改')
            for name, raw in replacements.items():
                if not course_exists(folder / name) or course_bytes(folder / name) != raw:
                    atomic_json(folder / name, _json(raw))
            amendment = {'schemaVersion': 'mira.textbook.preview-pronunciation-amendment.v1',
                'revisionId': revision_id, 'intentSha256': intent['sha256'], 'previewKey': key, 'classroomId': cid,
                'sourceSha256': digest(source), 'targetSha256': digest(current), 'parentPlanSha256': patch['parentPlanSha256'],
                'audioPlanSha256': digest(plan), 'coreSha256': digest(core_content(target)),
                'humanFeedbackSha256': patch['humanFeedback']['sha256'],
                'approvedProbeEvidenceSha256': patch['approvedProbeEvidence']['sha256'],
                'supersededTtsRequestIds': [n.removesuffix('.wav') for n in intent['parentWavs']],
                'reviewer': patch['reviewer'], 'basis': patch['basis'], 'generationDispatched': False,
                'publicationAllowed': False, 'requiresNewAudioAudit': True, 'requiresHumanListening': True}
            amendment['sha256'] = digest(amendment)
            immutable(commit_path, json_bytes(amendment))
            result = _json(course_bytes(archive / 'parent/result.json'))
            for field in ('frozenPreview', 'audioAudit', 'audioReview', 'publicationReview'):
                result.pop(field, None)
            result.update(audioReceipts=[], audioStopCode=None, audioPartial=True, audioSelection=None,
                          audioSeconds=0, audioCompleted=0, audioTotal=len(_speech(target)),
                          pronunciationRevisions=[*result.get('pronunciationRevisions', []), amendment])
            # Reacquire only after every remote/file write. The immutable
            # parent and pending marker reconcile partial saves on a rerun.
            conn.commit_phase()
            if (_json(course_bytes(root / (cid + '.json'))) != current
                    or any(course_bytes(folder / name) != raw for name, raw in replacements.items())):
                fail('提交前运行原稿或配音证据已变化，保留修订断点')
            changed = conn.execute('UPDATE learning_textbook_course_previews SET status=?,classroom_json=?,classroom_sha256=?,result_json=?,updated_at=? '
                'WHERE preview_key=? AND classroom_sha256=? AND status=? AND updated_at=?',
                ('review_required', canonical(current), digest(current), canonical(result), now_ms(), key,
                 source_row['classroom_sha256'], source_row['status'], source_row['updated_at'])).rowcount
            if changed != 1:
                fail('数据库比较更新失败，保留修订断点')
        # Only a confirmed commit removes the guard. A lost commit response is
        # reconciled against immutable lineage on the next invocation.
        if pending_path.exists():
            if pending_path.read_bytes() != pending:
                fail('修订完成标记变化')
            pending_path.unlink()
        return amendment
