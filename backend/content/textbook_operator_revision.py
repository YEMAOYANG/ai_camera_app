"""Pure contract for a new operator revision of one published textbook lesson.

This does not mutate a publication, authorize a provider call, or manufacture a
receipt. Parent evidence is supplied intact; the execution adapter must archive
its original bytes and verify every returned asset hash before registration.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import re
from urllib.parse import urlparse

from content.textbook_catalog import canonical, digest, identifier, lesson_by_id
from content.textbook_interactive_narration import AUDIO_BLOCK, interactive_cues, without_audio_helper
from content.textbook_preview import cue_speech
from content.textbook_preview_audio_contract import (
    MAX_SPEECH_ACTIONS, asr_request_id, audit_contract_identity, check_receipt_language_policy,
    compare_transcript, resolve_audio_contract, tts_request_id, check_receipt_pronunciation,
    validate_v2_audit_segment,
)
from content.textbook_pinyin_pronunciation import PLAN_SCHEMA as PINYIN_SCHEMA
from content.textbook_release import INPUT_SCHEMA, MEDIA, validate_release
from core.errors import ApiError
from services.learning_media_materialization_service import asr_similarity_bps

PATCH_SCHEMA = 'mira.textbook.published-operator-patch.v1'
PROVENANCE_SCHEMA = 'mira.textbook.operator-parent-provenance.v1'
QUIZ_PATCH_SCHEMA = 'mira.textbook.published-operator-patch.v2'
QUIZ_PROVENANCE_SCHEMA = 'mira.textbook.operator-parent-provenance.v2'
VISUAL_PATCH_SCHEMA = 'mira.textbook.published-operator-visual-patch.v3'
VISUAL_PROVENANCE_SCHEMA = 'mira.textbook.operator-parent-visual-provenance.v3'
VISUAL_AUDIO_SCHEMA = 'mira.textbook.unchanged-published-pinyin-audio.v1'
CROP_VERSION = 'rgb-crop-png.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')
CUE_BLOCK = re.compile(r'(<script\b[^>]*\bid=["\x27]mira-narration-cues["\x27][^>]*>)([\s\S]*?)(</script>)')
AUDIO_FIELDS = ('audioId', 'audioUrl', 'audioMetadata')


def fail(message):
    raise ApiError('textbook_operator_revision_conflict', message, 409)


def sha_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def parse(value):
    return json.loads(value) if isinstance(value, str) else value


def speech_index(classroom):
    items = [(scene, action) for scene in classroom['scenes']
             for action in scene.get('actions', []) if action.get('type') == 'speech']
    if (not items or len(items) > MAX_SPEECH_ACTIONS or len({a['id'] for _, a in items}) != len(items)
            or len({s['id'] for s in classroom['scenes']}) != len(classroom['scenes'])):
        fail('父课件的页面或旁白编号无效')
    return {(s['id'], a['id']): (s, a) for s, a in items}


def _source_attempt(plan, scene, action, receipts):
    """Older receipts do not contain an attempt field; verify the whole chain."""
    for attempt in range(1, len(receipts) + 2):
        request = tts_request_id(plan, scene['id'], action['id'], action['text'], attempt=attempt)
        if request == action['audioId']:
            return attempt
        if receipts.get(request, {}).get('status') not in {'failed', 'ambiguous'}:
            break
    fail('父音频编号不能由原计划和已保存的失败尝试验证')


def validated_question_audio_aliases(source, release, segments):
    """An old quiz alias must carry the bytes of its exact audited narration."""
    known = {f"/api/classroom-media/{source['id']}/audio/{s['ttsRequestId']}.wav" for s in segments}
    segment_index = {(s['sceneId'], s['actionId']): s for s in segments}
    published = {s['id']: s for s in release['classroom']['scenes']}
    media = {a['path']: a for a in release['media']}
    aliases = {}
    for scene in source['scenes']:
        if scene.get('type') != 'quiz':
            continue
        questions = scene.get('content', {}).get('questions', [])
        delivered = {q['id']: q for q in published.get(scene['id'], {}).get('content', {}).get('questions', [])}
        for number, question in enumerate(questions, 1):
            path = urlparse(question.get('questionAudioUrl', '')).path
            if not path or path in known:
                continue
            match = MEDIA.fullmatch(path)
            if (question.get('questionAudioUrl') != path or not match or match[1] != source['id']
                    or not re.fullmatch(r'audio/[A-Za-z0-9_-]+\.wav', match[2])):
                fail('旧测验音频别名必须是本课 WAV')
            texts = {question['question']}
            if len(question.get('options', [])) == 3:
                texts.add(f"第{number}题。{question['question']}。三个字分别是：" +
                          '，'.join(o['label'] for o in question['options']) + '。请选一选。')
            actions = [a for a in scene.get('actions', []) if a.get('type') == 'speech' and a.get('text') in texts]
            if len(actions) != 1:
                fail('旧测验音频别名没有唯一、逐字对应的已审读题旁白')
            action = actions[0]
            segment = segment_index.get((scene['id'], action['id']), {})
            target = delivered.get(question['id'], {})
            asset = media.get(target.get('questionAudioUrl'), {})
            if (not segment or target.get('question') != question['question']
                    or asset.get('sourceSha256', asset.get('sha256')) != segment['audioSha256']
                    or path in aliases):
                fail('旧别名不是该题已审核音频的原发布交付副本')
            aliases[path] = {'sceneId': scene['id'], 'questionId': question['id'], 'actionId': action['id'],
                'questionTextSha256': sha_text(question['question']), 'sourcePath': path,
                'audioSha256': segment['audioSha256'], 'ttsRequestId': segment['ttsRequestId']}
    return list(aliases.values())


def validate_parent(parent, *, allow_saved_preview=False, allow_visual_ancestry=False, allow_complete_scene=False):
    """Cache only pure v3 evidence validation; disk/DB/WAV checks stay live.

    The complete canonical evidence is the key, not a caller-supplied digest.
    Detached results prevent callers from poisoning a later verification.
    """
    if allow_visual_ancestry or allow_complete_scene:
        return deepcopy(_validated_visual_parent(canonical(parent), allow_saved_preview, allow_visual_ancestry, allow_complete_scene))
    return _validate_parent(parent, allow_saved_preview=allow_saved_preview,
                            allow_visual_ancestry=allow_visual_ancestry, allow_complete_scene=allow_complete_scene)


@lru_cache(maxsize=4)
def _validated_visual_parent(serialized, allow_saved_preview, allow_visual_ancestry, allow_complete_scene=False):
    return _validate_parent(json.loads(serialized), allow_saved_preview=allow_saved_preview,
                            allow_visual_ancestry=allow_visual_ancestry, allow_complete_scene=allow_complete_scene)


def _validate_parent(parent, *, allow_saved_preview=False, allow_visual_ancestry=False, allow_complete_scene=False):
    """Validate a complete published operator source without changing any input.

Return source segment identities and asset hashes for the filesystem adapter.
Legacy v1/v2 callers keep the original-plan-only contract. Explicit visual v3
callers may supply complete immutable ancestry and approved pinyin evidence.
"""
    required = {'build', 'manifest', 'preview', 'plan', 'receipts', 'audit'}
    optional = ({'sourceManifest'} if allow_saved_preview else set()) | ({'sourceInheritance', 'sourceRequestPlans', 'sourceNarrationRevisions', 'sourceAudioRestorations'} if allow_visual_ancestry else set())
    if allow_complete_scene:
        optional.add('sourceNarrationRevisions')
    if not required <= set(parent) or set(parent) - required - optional:
        fail('需要完整父发布、预览、计划、收据和审核证据')
    if allow_visual_ancestry:
        cursor, depth = parent, 0
        while 'sourceInheritance' in cursor:
            depth += 1
            if depth > 8:
                fail('视觉修订继承链超过可核验深度')
            link = cursor['sourceInheritance']
            if not isinstance(link, dict) or set(link) != {'parent', 'candidate', 'input', 'provenance'}:
                fail('继承来源结构不完整')
            cursor = link['parent']
    build, manifest, preview = parent['build'], parent['manifest'], parent['preview']
    frozen = parse(build['input_json'])
    from content.textbook_complete_scene_revision import PROVENANCE_SCHEMA as COMPLETE_PROVENANCE_SCHEMA
    complete_ancestry = allow_visual_ancestry and frozen.get('operatorParent', {}).get('schemaVersion') == COMPLETE_PROVENANCE_SCHEMA
    if frozen.get('schemaVersion') != INPUT_SCHEMA or ('operatorParent' in frozen and not allow_visual_ancestry):
        fail('首版只支持未继承的已发布 operator 课件')
    release = validate_release(build, manifest)
    if release is None:
        fail('父课件不是有效的 operator 发布')
    source, source_input = parse(preview['classroom_json']), parse(preview['input_json'])
    result = parse(preview['result_json'])
    pinyin = allow_visual_ancestry and parent['plan'].get('schemaVersion') == PINYIN_SCHEMA
    legacy_revisions = {}
    if 'sourceNarrationRevisions' in parent:
        from content.textbook_legacy_narration_evidence import validate_legacy_narration_evidence
        if not (allow_visual_ancestry or allow_complete_scene) or pinyin:
            fail('普通旧旁白修订证据只适用于纯视觉继承')
        legacy_revisions = validate_legacy_narration_evidence(parent, allow_v2=allow_complete_scene or complete_ancestry)
    approved = {}
    if pinyin:
        if frozen.get('audioContract') != parent['plan']:
            fail('拼音父计划必须是已发布的原冻结合同')
        operator_review = release['audioAudit'].get('pronunciationReview')
        if operator_review is not None:
            from content.textbook_pinyin_operator_review import validate_operator_review
            from core.security import now_ms
            approved = validate_operator_review(operator_review, plan=parent['plan'], classroom=source,
                audit=parent['audit'], expected_source_sha256=digest(source), now_ms=now_ms())
        elif not any(k in release['audioAudit'] for k in ('visualAudioInheritance', 'listeningReview')):
            fail('纯视觉拼音继承需要可验证的原发布审核证据')
    request_plans = {digest(parent['plan']): parent['plan']}
    source_plans = parent.get('sourceRequestPlans', [])
    if 'sourceRequestPlans' in parent:
        if not pinyin or approved or not isinstance(source_plans, list) or not source_plans:
            fail('额外旁白请求计划只适用于原人审拼音来源')
        used_revisions = {r['narrationRevisionId'] for r in parent['receipts'] if r.get('narrationRevisionId')
                          and r.get('requestId') in {a.get('audioId') for _, a in speech_index(source).values()}}
        if len(source_plans) != len(used_revisions) or {p.get('revisionId') for p in source_plans} != used_revisions:
            fail('原人审请求计划必须精确覆盖当前音频修订')
        for request_plan in source_plans:
            resolve_audio_contract(request_plan, parent['plan']['binding'])
            if (request_plan.get('parentPlanSha256') != digest(parent['plan'])
                    or request_plan.get('previewKey') != parent['plan']['previewKey']
                    or request_plan.get('pronunciationPolicy') != parent['plan']['pronunciationPolicy']):
                fail('原人审旁白请求计划没有继承父合同')
            request_plans[digest(request_plan)] = request_plan
    ancestry = parent.get('sourceInheritance')
    if ('operatorParent' in frozen) != (ancestry is not None):
        fail('继承来源必须包含完整且准确的父归档')
    if ancestry is not None:
        rebuilt = revision_candidate(ancestry['parent'], ancestry['candidate']['patch'],
            ancestry['candidate'].get('visualPatch'), derived_assets=ancestry['candidate'].get('derivedImages'),
            complete_scene_evidence=ancestry['candidate'].get('completeSceneEvidence'))
        if (rebuilt != ancestry['candidate'] or ancestry['input'] != source_input
                or inheritance_provenance(rebuilt, parent['plan']) != ancestry['provenance']
                or ancestry['provenance'] != frozen['operatorParent']
                or source_input.get('operatorRevision', {}).get('candidateSha256') != digest(rebuilt)):
            fail('父发布的完整继承来源、候选或合同不一致')
    restoration_context = None
    if 'sourceAudioRestorations' in parent:
        if not complete_ancestry or not ancestry:
            fail('原音频恢复来源必须包含完整场景修订的逐级归档')
        from content.textbook_parent_audio_restoration import validate_restoration_evidence
        restoration_context = validate_restoration_evidence(ancestry, parent['plan'], parent['sourceAudioRestorations'])
        if (not restoration_context['restorations']
                or restoration_context['restorations'] != result.get('parentAudioRestorations')
                or restoration_context['restorations'] != frozen.get('operatorParentAudioRestorations')):
            fail('原音频恢复证据与父发布及原预览不同')
    elif frozen.get('operatorParentAudioRestorations') or result.get('parentAudioRestorations'):
        fail('父发布的原音频恢复必须携带完整修订归档')
    binding = frozen['textbookBinding']
    expected = {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
                'manifestSha256': digest(manifest), 'nodeId': build['node_id'],
                'gradeCode': manifest['gradeCode'], 'subject': manifest['subject']}
    saved_preview = (allow_saved_preview and source_input.get('executionPolicy') == 'persist-content-before-segment-audio.v2'
                     and source_input.get('schemaVersion') == 'mira.learning.textbook-private-preview.v1'
                     and 'authoring' not in source_input and 'sourceSha256' not in source_input)
    if 'sourceManifest' in parent and not saved_preview:
        fail('额外原目录证据仅适用于旧保存预览来源')
    source_expected = expected
    if saved_preview:
        original_manifest = parent.get('sourceManifest')
        if not isinstance(original_manifest, dict):
            fail('旧保存课件必须保留原预览目录证据')
        source_expected = {**expected, 'alignmentRevisionId': original_manifest['revisionId'],
                           'manifestSha256': digest(original_manifest)}
        _, old_lesson = lesson_by_id(original_manifest, build['node_id'])
        _, published_lesson = lesson_by_id(manifest, build['node_id'])
        if (any(original_manifest.get(k) != manifest.get(k) for k in ('editionId', 'gradeCode', 'subject'))
                or old_lesson['title'] != published_lesson['title']
                or {k: v for k, v in old_lesson['brief'].items() if k != 'status'} !=
                   {k: v for k, v in published_lesson['brief'].items() if k != 'status'}
                or source_input.get('knowledgeBrief') != old_lesson['brief']):
            fail('旧预览与已发布教材课次的教学范围不一致')
    if ((not saved_preview and not ancestry and (source_input.get('executionPolicy') != 'operator-authored-saved-classroom.v1'
            or source_input.get('authoring', {}).get('mode') != 'openmaic_pro_workbench'))
            or ('operatorRevision' in source_input and not ancestry)
            or (ancestry and source_input.get('executionPolicy') != 'operator-published-revision.v1')
            or any(source_input.get(k) != v for k, v in source_expected.items())
            or preview['status'] != 'preview_ready' or result.get('audioStopCode')
            or (result.get('narrationRevisions') and not pinyin and not legacy_revisions) or frozen['previewKey'] != preview['preview_key']
            or source_input.get('previewKey') != preview['preview_key']
            or digest({k: v for k, v in source_input.items() if k not in {'previewKey', 'requirement'}}) != preview['preview_key']
            or frozen['sourceSha256'] != preview['classroom_sha256']
            or digest(source) != preview['classroom_sha256']
            or preview['edition_id'] != binding['editionId'] or preview['node_id'] != binding['nodeId']
            or preview['revision_id'] != source_expected['alignmentRevisionId']
            or source.get('id') != preview['classroom_id']
            or source.get('stage', {}).get('id') != preview['classroom_id']):
        fail('父预览与已发布的冻结来源不一致')
    plan, receipts, audit = parent['plan'], parent['receipts'], parent['audit']
    contract = resolve_audio_contract(plan, source_input)
    if (plan['previewKey'] != preview['preview_key'] or ('revisionId' in plan and not pinyin)
            or (not saved_preview and not ancestry and not pinyin and plan['classroomSha256'] != source_input.get('sourceSha256'))
            or (saved_preview and not contract['legacy'])
            or receipts != result.get('audioReceipts') or not isinstance(receipts, list)
            or len(receipts) > 1000):
        fail('父音频计划或收据不是原始来源')
    by_request = {r['requestId']: r for r in receipts}
    if len(by_request) != len(receipts):
        fail('父音频收据编号重复')
    actions = speech_index(source)
    entries = {(e['sceneId'], e['actionId']): e for e in audit.get('segments', [])}
    if ((audit.get('passed') is not True and not pinyin) or audit.get('previewKey') != preview['preview_key']
            or audit.get('sourceSha256') != digest(source)
            or digest({k: v for k, v in audit.items() if k != 'sha256'}) != audit.get('sha256')
            or audit['sha256'] != release['audioAudit']['sha256']
            or set(entries) != set(actions) or len(entries) != len(audit['segments'])
            or release['audioAudit']['segments'] != len(actions)):
        fail('需要完整且与已发布版本完全相同的通过审核')
    if not contract['legacy'] and (audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('contract') != audit_contract_identity(plan)):
        fail('父审核缺少冻结的 v2 配音合同')
    published = speech_index(release['classroom'])
    if set(published) != set(actions):
        fail('父发布的旁白身份与原始预览不一致')
    published_media = {m['path']: m for m in release['media']}
    assets = source_input.get('originalMedia', {}).get('assets', [])
    if (not assets or len({a.get('mediaPath') for a in assets}) != len(assets)
            or any(not SHA.fullmatch(str(a.get('sha256'))) for a in assets)):
        fail('父课件缺少唯一且有摘要的原始插画')
    expected_metadata = {'providerId': contract['teacher']['tts']['providerId'],
                         'modelId': contract['teacher']['tts']['modelId'],
                         'voiceId': contract['teacher']['voiceId'], 'fallbackUsed': False}
    segments = []
    for identity, (scene, action) in actions.items():
        receipt, entry = by_request.get(action.get('audioId'), {}), entries[identity]
        text = action['text'].strip()
        inherited = next((s for s in ancestry['candidate']['inheritedSegments']
            if (s['sceneId'], s['actionId']) == identity), None) if ancestry else None
        restored = restoration_context['restoredSegments'].get(identity) if restoration_context else None
        approved_item = approved.get(identity)
        segment_plan = plan
        if legacy_revisions and receipt.get('narrationRevisionId') is not None and not inherited and not restored:
            segment_plan = legacy_revisions.get(receipt['narrationRevisionId'])
            if segment_plan is None or receipt.get('classroomContentSha256') != segment_plan['classroomSha256']:
                fail('普通旧旁白没有完整的原修订归档')
        if pinyin and receipt.get('narrationRevisionId') is not None and not inherited and not approved_item:
            segment_plan = request_plans.get(receipt.get('previewAudioIdentity', {}).get('planSha256'))
            if (segment_plan is None or segment_plan.get('revisionId') != receipt['narrationRevisionId']
                    or receipt.get('classroomContentSha256') != segment_plan['classroomSha256']):
                fail('原人审旁白没有准确的修订请求计划')
        if approved_item:
            review_plans = {digest(p): p for p in [plan, *operator_review['requestPlans']]}
            segment_plan = review_plans[approved_item['requestPlanSha256']]
            if approved_item['ttsReceipt'] != receipt:
                fail('原拼音审核收据与本机来源不同')
        attempt = inherited['attempt'] if inherited else restored[0]['attempt'] if restored else _source_attempt(segment_plan, scene, action, by_request)
        if restored:
            from content.textbook_parent_audio_restoration import restored_entry
            if entry != restored_entry(restoration_context, plan, scene, action, receipt):
                fail('父恢复音频的原始审核证据不同')
        if inherited:
            proof = verify_inherited_segment(ancestry['parent'], ancestry['candidate'], plan,
                ancestry['provenance'], scene, action, receipt)
            inherited_entry = {**proof['sourceEntry'], 'comparison': proof['comparison'],
                'similarityBps': proof['comparison']['similarityBps'],
                'operatorParent': {'provenanceSha256': ancestry['provenance']['sha256'],
                                   'sourceEntrySha256': inherited['asrEntrySha256']}}
            if entry != inherited_entry:
                fail('父继承段落不符合原始审核证据')
        if (receipt.get('status') != 'succeeded' or not SHA.fullmatch(str(receipt.get('audioSha256')))
                or (receipt.get('narrationRevisionId') is not None and not (approved_item or inherited or restored or
                    ((pinyin or legacy_revisions) and segment_plan is not plan)))
                or any(action.get('audioMetadata', {}).get(k) != v for k, v in expected_metadata.items())
                or urlparse(action.get('audioUrl', '')).path !=
                   f"/api/classroom-media/{preview['classroom_id']}/audio/{action['audioId']}.wav"):
            fail('父旁白必须绑定原教师和已成功的原 WAV')
        if not inherited and not restored and not contract['legacy'] and receipt.get('previewAudioIdentity') != {
                'planSha256': digest(segment_plan), 'attempt': attempt}:
            fail('父 v2 音频的计划身份不一致')
        if not inherited and not restored:
            check_receipt_language_policy(segment_plan, receipt)
            if pinyin:
                check_receipt_pronunciation(segment_plan, receipt, text)
        if (entry.get('text') != text or entry.get('textSha256') != sha_text(text)
                or entry.get('ttsRequestId') != action['audioId']
                or entry.get('audioSha256') != receipt['audioSha256']
                or entry.get('asr', {}).get('status') != 'succeeded'
                or entry.get('asr', {}).get('requestId') != asr_request_id(plan, action['audioId'], receipt['audioSha256'])
                or entry.get('transcript') != entry.get('asr', {}).get('transcript')
                or entry.get('asr', {}).get('transcriptSha256') != sha_text(entry.get('transcript', ''))):
            fail('父 ASR 收据与原文或音频不一致')
        if contract['legacy']:
            if (audit.get('schemaVersion') != 'mira.textbook.audio-audit.v1'
                    or entry.get('similarityBps') != asr_similarity_bps(text, entry['transcript'])
                    or entry['similarityBps'] < 8500):
                fail('父语音没有通过原始审核规则')
        elif not inherited and not validate_v2_audit_segment(plan, action, entry, scene_id=scene['id']) and not pinyin:
            fail('父语音没有通过冻结的审核规则')
        delivered = published[identity][1]
        media = published_media.get(delivered.get('audioUrl'), {})
        if (delivered.get('text') != action['text'] or delivered.get('audioId') != action['audioId']
                or media.get('sourceSha256', media.get('sha256')) != receipt['audioSha256']):
            fail('父发布音频不是原审核音频的交付副本')
        segments.append({'sceneId': scene['id'], 'actionId': action['id'], 'textSha256': sha_text(text),
                         'ttsRequestId': action['audioId'], 'attempt': attempt,
                         'audioSha256': receipt['audioSha256'], 'ttsReceiptSha256': digest(receipt),
                         'asrRequestId': entry['asr']['requestId'], 'asrEntrySha256': digest(entry)})
    aliases = validated_question_audio_aliases(source, release, segments) if allow_visual_ancestry else []
    return {'contentKey': build['content_key'], 'releaseSha256': release['sha256'],
            'previewKey': preview['preview_key'], 'classroomId': preview['classroom_id'],
            'classroomSha256': digest(source), 'planSha256': digest(plan),
            'receiptsSha256': digest(receipts), 'auditSha256': audit['sha256'],
            'sourceEvidenceSha256': digest(parent), 'binding': expected,
            'teacher': deepcopy(contract['teacher']), 'segments': segments,
            'originalMedia': deepcopy(source_input['originalMedia']), **({'audioAliases': aliases} if aliases else {})}


def _sync_cue(scene, old, new):
    html = scene['content']['html']
    without_audio_helper(html)
    cues = interactive_cues(html)
    matches = list(CUE_BLOCK.finditer(html))
    if len(matches) != 1 or not any(c['text'] == old for c in cues):
        fail('互动旁白必须有唯一的同页提示清单')
    block = matches[0]
    payload = json.loads(block.group(2))
    payload['cues'] = [{**c, 'text': new} if c['text'] == old else c for c in cues]
    # Only the JSON payload changes. Existing scripts and pictures remain exact.
    html = html[:block.start(2)] + canonical(payload) + html[block.end(2):]
    scene['content']['html'] = AUDIO_BLOCK.sub('', html)


def _visual_candidate(source, origin, patch):
    """The existing visual-patch schema, before any new audio plan is frozen.

    Asset bytes are verified by the adapter. A newly referenced picture must
    already occur in this lesson and in its immutable original-media manifest.
    """
    fields = {'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'}
    if (not isinstance(patch, dict) or set(patch) != fields
            or patch['schemaVersion'] != 'mira.textbook.preview-visual-patch.v1'
            or patch['expectedSourceSha256'] != origin['classroomSha256']
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 60):
        fail('视觉补丁必须基于未修改的父预览')
    allowed = {a['mediaPath'] for a in origin['originalMedia']['assets']}
    used = set(MEDIA.findall(canonical(source)))
    scenes, seen = {s['id']: s for s in source['scenes']}, set()
    for change in patch['changes']:
        if (not isinstance(change, dict) or set(change) != {'sceneId', 'beforeHtmlSha256', 'html'}
                or change['sceneId'] in seen or change['sceneId'] not in scenes):
            fail('视觉补丁页面身份无效或重复')
        seen.add(change['sceneId'])
        scene = scenes[change['sceneId']]
        old, new = scene['content'].get('html'), change['html']
        if (scene['type'] != 'interactive' or not isinstance(old, str) or not isinstance(new, str)
                or not new.strip() or sha_text(old) != change['beforeHtmlSha256'] or old == new):
            fail('视觉补丁必须包含准确的原互动页摘要和实际差异')
        without_audio_helper(old)
        without_audio_helper(new)
        old_media, new_media = set(MEDIA.findall(old)), set(MEDIA.findall(new))
        if (interactive_cues(old) != interactive_cues(new) or AUDIO_BLOCK.findall(old) != AUDIO_BLOCK.findall(new)
                or not old_media <= new_media or any((owner, name) not in used
                    or f'/api/classroom-media/{owner}/{name}' not in allowed or not name.startswith('media/')
                    for owner, name in new_media - old_media)):
            fail('视觉补丁不能改变语音、提示、播放器或替换素材')
        scene['content']['html'] = new
        cue_speech(scene)


def revision_candidate(parent, patch, visual_patch=None, *, derived_assets=None, complete_scene_evidence=None):
    """Apply an explicit, narrow content correction to a separate in-memory copy."""
    from content.textbook_complete_scene_revision import PATCH_SCHEMA as COMPLETE_SCHEMA, PREVIEW_PATCH_SCHEMA, complete_scene_candidate
    from content.textbook_legacy_complete_scene_revision import PATCH_SCHEMA as LEGACY_COMPLETE_SCHEMA, legacy_complete_scene_candidate
    if isinstance(patch, dict) and patch.get('schemaVersion') in {COMPLETE_SCHEMA, PREVIEW_PATCH_SCHEMA, LEGACY_COMPLETE_SCHEMA}:
        if visual_patch is not None or derived_assets is not None:
            fail('完整场景修订不能混用旧修订白名单')
        if patch['schemaVersion'] == LEGACY_COMPLETE_SCHEMA:
            return legacy_complete_scene_candidate(parent, patch, complete_scene_evidence)
        return complete_scene_candidate(parent, patch, complete_scene_evidence)
    if complete_scene_evidence is not None:
        fail('旧修订版本不能带入完整场景证据')
    if isinstance(patch, dict) and patch.get('schemaVersion') == QUIZ_PATCH_SCHEMA:
        if visual_patch is not None:
            fail('小测修订不能同时修改其他互动页面')
        return quiz_revision_candidate(parent, patch, derived_assets=derived_assets)
    visual_only = isinstance(patch, dict) and patch.get('schemaVersion') == VISUAL_PATCH_SCHEMA
    if visual_only and (patch.get('changes') != [] or visual_patch is None or derived_assets):
        fail('v3 仅允许改变互动 HTML，不能改变旁白、测验或图片')
    origin = validate_parent(parent, allow_saved_preview=visual_only, allow_visual_ancestry=visual_only)
    fields = {'schemaVersion', 'parentContentKey', 'expectedSourceSha256', 'teachingRevision',
              'reviewer', 'basis', 'changes'}
    if (not isinstance(patch, dict) or set(patch) != fields or patch['schemaVersion'] not in {PATCH_SCHEMA, VISUAL_PATCH_SCHEMA}
            or patch['parentContentKey'] != origin['contentKey']
            or patch['expectedSourceSha256'] != origin['classroomSha256']
            or not identifier(patch['teachingRevision'])
            or patch['teachingRevision'] == parent['build']['teaching_revision']
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 0 <= len(patch['changes']) <= 160
            or (not patch['changes'] and visual_patch is None)):
        fail('需要父版本摘要、不同的新教学版本和明确修订依据')
    source = parse(parent['preview']['classroom_json'])
    if visual_only:
        allowed_audio = {f"{s['ttsRequestId']}.wav" for s in origin['segments']}
        allowed_audio.update(urlparse(a['sourcePath']).path.rsplit('/', 1)[-1] for a in origin.get('audioAliases', []))
        if any(owner != source['id'] or name.removeprefix('audio/') not in allowed_audio
               for owner, name in MEDIA.findall(canonical(source)) if name.startswith('audio/')):
            fail('纯视觉来源的每个音频引用必须对应准确的已审核段落')
    target = deepcopy(source)
    if visual_patch is not None:
        _visual_candidate(target, origin, visual_patch)
    if not patch['changes']:
        # Pure visual revisions keep every field other than the explicitly
        # validated HTML exact, including all speech and assessment evidence.
        restored = deepcopy(target)
        old_scenes = {s['id']: s for s in source['scenes']}
        changed_html = {c['sceneId'] for c in visual_patch['changes']}
        for scene in restored['scenes']:
            if scene['id'] in changed_html:
                scene['content']['html'] = old_scenes[scene['id']]['content']['html']
        if restored != source:
            fail('纯视觉修订只能改变指定 HTML，全部旁白、测验和其他字段必须保持')
    scenes = {s['id']: s for s in target['scenes']}
    seen, changed = set(), set()
    for change in patch['changes']:
        kind = change.get('kind')
        fields = {'kind', 'sceneId', 'beforeSha256', 'text'}
        fields |= {'actionId'} if kind == 'speech' else {'questionId', 'optionValue'} if kind == 'option_label' else {'elementId'}
        if (kind not in {'speech', 'option_label', 'slide_text'} or set(change) != fields
                or change['sceneId'] not in scenes or not SHA.fullmatch(str(change['beforeSha256']))
                or not isinstance(change['text'], str) or change['text'] != change['text'].strip()
                or not 1 <= len(change['text']) <= 4000):
            fail('只支持指定旁白、选项标签和幻灯片文字的局部修订')
        scene = scenes[change['sceneId']]
        identity = (kind, scene['id'], change.get('actionId'), change.get('questionId'),
                    change.get('optionValue'), change.get('elementId'))
        if identity in seen:
            fail('同一修订字段不能重复')
        seen.add(identity)
        if kind == 'speech':
            candidates = [a for a in scene.get('actions', []) if a.get('type') == 'speech' and a['id'] == change['actionId']]
            if len(candidates) != 1 or scene['type'] == 'quiz':
                fail('首版不能改变测验题干或其读题旁白')
            item, field = candidates[0], 'text'
        elif kind == 'option_label':
            qs = [q for q in scene['content'].get('questions', []) if q['id'] == change['questionId']]
            candidates = [o for q in qs for o in q['options'] if o['value'] == change['optionValue']]
            if scene['type'] != 'quiz' or len(qs) != 1 or len(candidates) != 1:
                fail('选项标签身份不唯一')
            item, field = candidates[0], 'label'
        else:
            candidates = [e for e in scene['content'].get('canvas', {}).get('elements', [])
                          if e.get('id') == change['elementId'] and e.get('type') == 'text']
            if scene['type'] != 'slide' or len(candidates) != 1:
                fail('幻灯片文字元素身份不唯一')
            item, field = candidates[0], 'content'
        old = item.get(field)
        if not isinstance(old, str) or sha_text(old) != change['beforeSha256'] or old == change['text']:
            fail('原文字摘要变化或修订没有实际差异')
        if kind == 'slide_text' and re.findall(r'<[^>]*>', old) != re.findall(r'<[^>]*>', change['text']):
            fail('幻灯片文字修订不能改变标签、样式或引入其他内容')
        item[field] = change['text']
        if kind == 'speech':
            changed.add((scene['id'], item['id']))
            for field in AUDIO_FIELDS:
                item.pop(field, None)
            if scene['type'] == 'interactive':
                _sync_cue(scene, old, change['text'])
                cue_speech(scene)
    revision_id = digest({'parentReleaseSha256': origin['releaseSha256'], 'patch': patch,
                          'visualPatch': visual_patch})
    target_id = 'tbrev_' + revision_id[:24]
    old_id = target['id']
    target['id'] = target_id
    target['stage']['id'] = target_id
    # Images keep their audited source references. WAV bytes are copied into the
    # new classroom namespace without changing their request ids or receipts.
    raw = canonical(target).replace(f'/api/classroom-media/{old_id}/audio/',
                                    f'/api/classroom-media/{target_id}/audio/')
    target = json.loads(raw)
    return {'revisionId': revision_id, 'parent': origin, 'patch': deepcopy(patch), 'visualPatch': deepcopy(visual_patch),
            'classroom': target, 'changedSegments': [list(k) for k in sorted(changed)],
            'inheritedSegments': [s for s in origin['segments']
                                  if (s['sceneId'], s['actionId']) not in changed]}


def quiz_crop_definitions(parent, patch):
    """Only bounded pixel crops of this exact parent's images are accepted."""
    source = parse(parent['preview']['input_json'])
    original = {a['mediaPath']: a for a in source.get('originalMedia', {}).get('assets', [])}
    definitions = patch.get('derivedImages')
    if not isinstance(definitions, list) or not 1 <= len(definitions) <= 30:
        fail('小测需要明确的原图裁切清单')
    seen = set()
    for item in definitions:
        if (not isinstance(item, dict) or set(item) != {'id', 'sourcePath', 'sourceSha256',
                'sourceSize', 'rect', 'transform'} or not identifier(item['id']) or item['id'] in seen
                or item['sourcePath'] not in original
                or item['sourceSha256'] != original[item['sourcePath']]['sha256']
                or item['transform'] != CROP_VERSION):
            fail('裁切必须绑定唯一编号和已审核的父图摘要')
        size, rect = item['sourceSize'], item['rect']
        if (not isinstance(size, list) or len(size) != 2 or not isinstance(rect, list) or len(rect) != 4
                or any(type(n) is not int for n in size + rect)
                or any(n <= 0 or n > 12000 for n in size)
                or rect[0] < 0 or rect[1] < 0 or rect[2] < 32 or rect[3] < 32
                or rect[0] + rect[2] > size[0] or rect[1] + rect[3] > size[1]):
            fail('裁切矩形必须完整位于原图内部')
        seen.add(item['id'])
    return definitions


def quiz_revision_candidate(parent, patch, *, derived_assets):
    """A quiz edit is atomic: private answer, pictures and its own speech slot.

    V1 remains a separate branch. V2 replaces existing quiz speech only; it
    never aliases another action's receipt or adds arbitrary scene JSON.
    """
    origin = validate_parent(parent, allow_saved_preview=True)
    fields = {'schemaVersion', 'parentContentKey', 'expectedSourceSha256', 'teachingRevision',
              'reviewer', 'basis', 'changes', 'derivedImages'}
    if (set(patch) != fields or patch['parentContentKey'] != origin['contentKey']
            or patch['expectedSourceSha256'] != origin['classroomSha256']
            or not identifier(patch['teachingRevision'])
            or patch['teachingRevision'] == parent['build']['teaching_revision']
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 4):
        fail('小测修订需要准确的父版本和独立教学版本')
    definitions = quiz_crop_definitions(parent, patch)
    revision_id = digest({'parentReleaseSha256': origin['releaseSha256'], 'patch': patch, 'visualPatch': None})
    target_id = 'tbrev_' + revision_id[:24]
    if not isinstance(derived_assets, list) or len(derived_assets) != len(definitions):
        fail('需要经过本机像素裁切验证的派生图片')
    for definition, asset in zip(definitions, derived_assets):
        if (set(asset) != {'definition', 'sha256', 'byteSize', 'mediaPath'} or asset['definition'] != definition
                or not SHA.fullmatch(str(asset['sha256'])) or type(asset['byteSize']) is not int
                or not 0 < asset['byteSize'] <= 20_000_000
                or asset['mediaPath'] != f"/api/classroom-media/{target_id}/media/{asset['sha256']}.png"):
            fail('派生图片没有绑定当前修订和裁切定义')
    images = {a['definition']['id']: a['mediaPath'] for a in derived_assets}
    original_images = {a['mediaPath'] for a in origin['originalMedia']['assets']}

    def picture(value, *, main=False):
        if not isinstance(value, dict):
            fail('每个选项都需要有意义的图片')
        if main and value.get('kind') == 'people':
            if set(value) != {'kind', 'members'} or not isinstance(value['members'], list) or len(value['members']) != 3:
                fail('人物情境需要三位固定人物')
            members = value['members']
            if (len({m.get('id') for m in members}) != 3
                    or sorted(m.get('cue', '') for m in members) != ['listening', 'observer', 'speaking']):
                fail('人物情境必须明确一位说话者、一位倾听者和一位旁观者')
            result = []
            for member in members:
                if set(member) != {'id', 'cropId', 'alt', 'cue'} or not identifier(member['id']):
                    fail('人物情境字段无效')
                resolved = picture({'kind': 'image', 'cropId': member['cropId'], 'alt': member['alt']})
                result.append({'id': member['id'], 'src': resolved['src'], 'alt': resolved['alt'], 'cue': member['cue']})
            if len({m['src'] for m in result}) != 3:
                fail('三个角色必须使用可区分的原肖像裁切')
            return {'kind': 'people', 'members': result}
        allowed = {'kind', 'alt', 'sourcePath'} if main and 'sourcePath' in value else {'kind', 'alt', 'cropId'}
        if (set(value) != allowed or value.get('kind') != 'image' or not isinstance(value.get('alt'), str)
                or not 1 <= len(value['alt'].strip()) <= 200):
            fail('图片仅允许审核裁切或主情境原图，不能携带答案样式')
        path = value.get('sourcePath') if 'sourcePath' in value else images.get(value.get('cropId'))
        if not path or ('sourcePath' in value and path not in original_images):
            fail('题图必须来自本课已冻结的图片')
        return {'kind': 'image', 'src': path, 'alt': value['alt']}

    target = deepcopy(parse(parent['preview']['classroom_json']))
    scenes = {s['id']: s for s in target['scenes']}
    changed, seen, bindings = set(), set(), []
    for change in patch['changes']:
        if (not isinstance(change, dict) or set(change) != {'kind', 'sceneId', 'beforeQuestionsSha256',
                'beforeActionsSha256', 'intro', 'questions'} or change['kind'] != 'quiz_scene'
                or change['sceneId'] not in scenes or change['sceneId'] in seen):
            fail('小测页面修订字段或身份无效')
        seen.add(change['sceneId'])
        scene = scenes[change['sceneId']]
        old_questions = scene['content'].get('questions', [])
        if (scene['type'] != 'quiz' or digest(old_questions) != change['beforeQuestionsSha256']
                or digest(scene['actions']) != change['beforeActionsSha256']
                or not isinstance(change['questions'], list)
                or [q.get('questionId') for q in change['questions']] != [q['id'] for q in old_questions]):
            fail('原小测题目、顺序或讲解动作摘要已变化')
        speeches = {a['id']: a for a in scene['actions'] if a.get('type') == 'speech'}
        used = set()
        for number, (old, edit) in enumerate(zip(old_questions, change['questions']), 1):
            if (set(edit) != {'questionId', 'beforeQuestionSha256', 'question', 'options', 'answer',
                    'analysis', 'visual', 'optionVisuals', 'speechActionId'}
                    or digest(old) != edit['beforeQuestionSha256'] or edit['answer'] != old['answer']
                    or not isinstance(edit['options'], list)
                    or [o.get('value') for o in edit['options']] != [o['value'] for o in old['options']]
                    or any(set(o) != {'value', 'label'} or not isinstance(o['label'], str)
                           or not 1 <= len(o['label'].strip()) <= 200 for o in edit['options'])
                    or any(not isinstance(edit[k], str) or edit[k] != edit[k].strip()
                           or not 1 <= len(edit[k]) <= 1000 for k in ('question', 'analysis'))):
                fail('小测修订必须保留题号、选项值、顺序和私有正确答案')
            aid = edit['speechActionId']
            action = speeches.get(aid)
            matching = [a for a in speeches.values() if urlparse(a.get('audioUrl', '')).path ==
                        urlparse(old.get('questionAudioUrl', '')).path]
            if not matching and 'sourceManifest' in parent:
                # Legacy saved previews used a numbered question-file alias.
                # Replace its own fully audited narration; never inherit that
                # alias or infer identity from a title/partial text match.
                legacy_text = (f"第{number}题。{old['question']}。三个字分别是：" +
                               '，'.join(o['label'] for o in old['options']) + '。请选一选。')
                if (len(old['options']) == 3 and old.get('questionAudioUrl') ==
                        f"/api/classroom-media/{origin['classroomId']}/audio/question-{number}.wav"):
                    matching = [a for a in speeches.values() if a['text'] == legacy_text and
                                a['id'] == f'review_question-{number}']
            if action is None or aid in used or matching != [action] or edit['question'] == action['text']:
                fail('新题干必须明确替换本题唯一的原配音动作')
            used.add(aid)
            option_visuals = edit['optionVisuals']
            if not isinstance(option_visuals, dict) or set(option_visuals) != {o['value'] for o in old['options']}:
                fail('图片必须一一对应全部选项值')
            visual = picture(edit['visual'], main=True)
            visuals = {v: picture(p) for v, p in option_visuals.items()}
            if len({v['src'] for v in visuals.values()}) != len(visuals):
                fail('不能用相同图片冒充不同选项')
            if visual['kind'] == 'people' and {v['src'] for v in visuals.values()} != {m['src'] for m in visual['members']}:
                fail('人物选项必须完整复用当前说话、倾听、旁观三位人物')
            old.update(question=edit['question'], options=deepcopy(edit['options']), answer=deepcopy(edit['answer']),
                       analysis=edit['analysis'], visual=visual, optionVisuals=visuals)
            old.pop('questionAudioUrl', None)
            action['text'] = edit['question']
            for field in AUDIO_FIELDS:
                action.pop(field, None)
            changed.add((scene['id'], aid))
            bindings.append({'sceneId': scene['id'], 'questionId': old['id'], 'actionId': aid,
                             'question': deepcopy(old)})
        intro = change['intro']
        if (not isinstance(intro, dict) or set(intro) != {'actionId', 'beforeTextSha256', 'text'}
                or intro['actionId'] not in speeches or intro['actionId'] in used
                or not isinstance(intro['text'], str) or intro['text'] != intro['text'].strip()
                or not 1 <= len(intro['text']) <= 1000):
            fail('需要与选图任务一致的独立开场')
        action = speeches[intro['actionId']]
        if (sha_text(action['text']) != intro['beforeTextSha256'] or action['text'] == intro['text']
                or scene['actions'].index(action) >= min(scene['actions'].index(speeches[a]) for a in used)):
            fail('开场必须匹配原文且位于全部题干之前')
        action['text'] = intro['text']
        for field in AUDIO_FIELDS:
            action.pop(field, None)
        changed.add((scene['id'], action['id']))
    old_id = target['id']
    target['id'] = target['stage']['id'] = target_id
    target = json.loads(canonical(target).replace(f'/api/classroom-media/{old_id}/audio/',
                                                f'/api/classroom-media/{target_id}/audio/'))
    return {'revisionId': revision_id, 'parent': origin, 'patch': deepcopy(patch), 'visualPatch': None,
            'classroom': target, 'changedSegments': [list(k) for k in sorted(changed)],
            'inheritedSegments': [s for s in origin['segments'] if (s['sceneId'], s['actionId']) not in changed],
            'derivedImages': deepcopy(derived_assets), 'quizBindings': bindings,
            'assessmentEvidence': 'picture-and-narration-supported-comprehension'}


def inheritance_provenance(candidate, target_plan):
    """Bind inheritance to an independent target plan; never relabel the source."""
    contract = resolve_audio_contract(target_plan, candidate['parent']['binding'])
    core = deepcopy(candidate['classroom'])
    core.pop('createdAt', None)
    for _, action in speech_index(core).values():
        for field in AUDIO_FIELDS:
            action.pop(field, None)
    if (contract['legacy'] or contract['teacher'] != candidate['parent']['teacher']
            or target_plan['previewKey'] == candidate['parent']['previewKey']
            or target_plan['coreSha256'] != digest(core)):
        fail('新预览必须冻结同一教师的 v2 合同')
    if candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA and target_plan.get('schemaVersion') == PINYIN_SCHEMA:
        if target_plan.get('revisionId') != candidate['revisionId'] or target_plan.get('parentPlanSha256') != candidate['parent']['planSha256']:
            fail('纯视觉拼音计划必须显式继承原合同')
    value = {'schemaVersion': PROVENANCE_SCHEMA, 'revisionId': candidate['revisionId'],
             'parent': candidate['parent'], 'patchSha256': digest(candidate['patch']),
             'targetPreviewKey': target_plan['previewKey'], 'targetPlanSha256': digest(target_plan),
             'targetClassroomId': candidate['classroom']['id'],
             'inheritedSegments': candidate['inheritedSegments']}
    if candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA:
        value['schemaVersion'] = VISUAL_PROVENANCE_SCHEMA
    if candidate['patch']['schemaVersion'] == QUIZ_PATCH_SCHEMA:
        value.update(schemaVersion=QUIZ_PROVENANCE_SCHEMA, derivedImages=deepcopy(candidate['derivedImages']),
                     quizBindings=deepcopy(candidate['quizBindings']), assessmentEvidence=candidate['assessmentEvidence'])
    from content.textbook_complete_scene_revision import PATCH_SCHEMA as COMPLETE_SCHEMA, PREVIEW_PATCH_SCHEMA, PROVENANCE_SCHEMA as COMPLETE_PROVENANCE
    from content.textbook_legacy_complete_scene_revision import PATCH_SCHEMA as LEGACY_COMPLETE_SCHEMA
    if candidate['patch']['schemaVersion'] in {COMPLETE_SCHEMA, PREVIEW_PATCH_SCHEMA, LEGACY_COMPLETE_SCHEMA}:
        value.update(schemaVersion=COMPLETE_PROVENANCE,
                     completeSceneEvidenceSha256=digest(candidate['completeSceneEvidence']),
                     modifiedSegments=candidate['modifiedSegments'], addedSegments=candidate['addedSegments'],
                     deletedSegments=candidate['deletedSegments'])
    return {**deepcopy(value), 'sha256': digest(value)}


def verify_inherited_segment(parent, candidate, target_plan, provenance, scene, action, receipt):
    """Verify original evidence, then locally compare its transcript for target."""
    return verify_inherited_segments(parent, candidate, target_plan, provenance,
                                     [(scene, action, receipt)])[0]


def verify_inherited_segments(parent, candidate, target_plan, provenance, segments):
    """Validate the whole immutable candidate once, then verify every segment.

    Rebuilding the same classroom for each utterance made one published lesson
    take tens of seconds to open. This batch boundary keeps the complete parent
    and candidate checks; callers cannot opt out of them or supply a trusted flag.
    """
    rebuilt = revision_candidate(parent, candidate['patch'], candidate.get('visualPatch'),
                                 derived_assets=candidate.get('derivedImages'),
                                 complete_scene_evidence=candidate.get('completeSceneEvidence'))
    if rebuilt != candidate or inheritance_provenance(rebuilt, target_plan) != provenance:
        fail('继承来源、白名单差异或目标合同已变化')
    source_actions = speech_index(parse(parent['preview']['classroom_json']))
    return [_verify_checked_inherited_segment(parent, candidate, target_plan, provenance,
                source_actions, scene, action, receipt) for scene, action, receipt in segments]


def _verify_checked_inherited_segment(parent, candidate, target_plan, provenance,
                                      source_actions, scene, action, receipt):
    matches = [s for s in provenance['inheritedSegments']
               if (s['sceneId'], s['actionId']) == (scene['id'], action['id'])]
    if len(matches) != 1:
        fail('修改过的旁白不能复用父音频')
    saved = matches[0]
    source_action = source_actions[(scene['id'], action['id'])][1]
    if (action.get('audioId') != saved['ttsRequestId'] or sha_text(action['text'].strip()) != saved['textSha256']
            or digest(receipt) != saved['ttsReceiptSha256'] or receipt.get('audioSha256') != saved['audioSha256']
            or action.get('audioMetadata') != source_action.get('audioMetadata')
            or urlparse(action.get('audioUrl', '')).path !=
               f"/api/classroom-media/{candidate['classroom']['id']}/audio/{saved['ttsRequestId']}.wav"):
        fail('继承的旁白文本、收据或音频摘要变化')
    entry = next(e for e in parent['audit']['segments']
                 if (e['sceneId'], e['actionId']) == (scene['id'], action['id']))
    comparison = compare_transcript(target_plan, action['text'], entry['transcript'])
    if not comparison['passed'] and not (candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA
            and parent['plan'].get('schemaVersion') == PINYIN_SCHEMA
            and target_plan.get('pronunciationPolicy') == parent['plan'].get('pronunciationPolicy')):
        fail('父语音未通过目标预览的审核策略')
    return {'sourceEntry': deepcopy(entry), 'comparison': comparison,
            'parentProvenanceSha256': provenance['sha256']}


def visual_audio_acceptance(parent, candidate, plan, provenance):
    """Portable source approval, explicitly not a new pronunciation/listening review."""
    rebuilt = revision_candidate(parent, candidate['patch'], candidate.get('visualPatch'))
    if (rebuilt != candidate or candidate['patch']['schemaVersion'] != VISUAL_PATCH_SCHEMA
            or parent['plan'].get('schemaVersion') != PINYIN_SCHEMA
            or candidate['changedSegments'] or inheritance_provenance(candidate, plan) != provenance):
        fail('音频审批继承仅适用于完整核验的纯视觉拼音修订')
    retained = {k: v for k, v in parent['plan'].items()
                if k not in {'previewKey', 'classroomSha256', 'coreSha256', 'revisionId', 'parentPlanSha256'}}
    if {k: v for k, v in plan.items() if k in retained} != retained or set(plan) != set(parent['plan']):
        fail('纯视觉修订不能切换拼音教师、策略或合同')
    value = {'schemaVersion': VISUAL_AUDIO_SCHEMA, 'parentEvidence': deepcopy(parent),
             'patch': deepcopy(candidate['patch']), 'visualPatch': deepcopy(candidate['visualPatch']),
             'targetPlanSha256': digest(plan), 'targetProvenanceSha256': provenance['sha256'],
             'evidenceLimit': 'Unchanged published audio and its original approval only; no new listening or browser review.'}
    return {**value, 'sha256': digest(value)}


def validate_visual_candidate_content(candidate, classroom, *, media=None):
    """No post-registration edits outside the frozen visual candidate."""
    # Media namespaces and scene ownership change on publication. The latter
    # has only one allowed mapping, checked below; all teaching fields stay exact.
    source_media = {urlparse(a['mediaPath']).path: a['sha256'] for a in candidate['parent']['originalMedia']['assets']}
    source_media.update({f"/api/classroom-media/{candidate['classroom']['id']}/audio/{x['ttsRequestId']}.wav": x['audioSha256']
                         for x in candidate['inheritedSegments']})
    source_media.update({f"/api/classroom-media/{candidate['classroom']['id']}/audio/{a['sourcePath'].rsplit('/', 1)[-1]}": a['audioSha256']
                         for a in candidate['parent'].get('audioAliases', [])})
    delivered_media = {urlparse(m['path']).path: m.get('sourceSha256', m.get('sha256')) for m in media or []}
    def normalized_room(room, lookup):
        room = deepcopy(room)
        room.pop('createdAt', None)
        room['id'] = room['stage']['id'] = 'visual-audio-identity'
        for scene in room['scenes']:
            if scene.get('type') == 'interactive':
                html = scene['content']['html']
                # Narration rebinding may relocate the exact helper to <head>
                # or the start. Its bytes, clips and all teaching HTML stay exact.
                # A published delivery copy may be MP3, while the authoring
                # helper accepts WAV only. Validate its exact known code with
                # immutable source-audio identities, never arbitrary URLs;
                # retain the original block for the full comparison below.
                def checked_audio_url(match):
                    path = urlparse(match.group(0)).path
                    sha = lookup.get(path)
                    if match.group(0) != path or not match[2].startswith('audio/') or not SHA.fullmatch(str(sha)):
                        fail('纯视觉播放器包含未继承的音频')
                    return f'/api/classroom-media/visual_audio_validation/audio/{sha}.wav'
                checked = AUDIO_BLOCK.sub(lambda block: MEDIA.sub(checked_audio_url, block.group(0)), html)
                without_audio_helper(checked)
                scene['content']['html'] = AUDIO_BLOCK.sub('', html) + ''.join(AUDIO_BLOCK.findall(html))
        def visit(value):
            if isinstance(value, dict):
                return {k: visit(v) for k, v in value.items()}
            if isinstance(value, list):
                return [visit(v) for v in value]
            if isinstance(value, str):
                def replace(match):
                    sha = lookup.get(urlparse(match.group(0)).path)
                    if not sha:
                        fail('纯视觉发布包含未继承的媒体')
                    return 'sha256:' + sha
                return MEDIA.sub(replace, value)
            return value
        return visit(room)
    actual = normalized_room(classroom, delivered_media if media is not None else source_media)
    expected = normalized_room(candidate['classroom'], source_media)
    if actual == expected:
        return  # Preserve the exact comparison for existing signed archives.
    published_id = classroom.get('id')
    if (media is not None and isinstance(published_id, str)
            and re.fullmatch(r'tbpub_[a-f0-9]{24}', published_id)
            and classroom.get('stage', {}).get('id') == published_id):
        for scene in expected['scenes']:
            scene['stageId'] = published_id
    if actual != expected:
        fail('纯视觉发布改变了冻结候选的旁白、测验、HTML 或其他内容')


def validate_visual_audio_acceptance(value, *, plan, provenance, classroom, audit, media=None):
    """Rebuild the entire source approval and exact unchanged target speech set."""
    if not isinstance(value, dict) or value.get('schemaVersion') != VISUAL_AUDIO_SCHEMA:
        fail('缺少版本化的已发布拼音音频继承证据')
    parent = value.get('parentEvidence', {})
    candidate = revision_candidate(parent, value.get('patch'), value.get('visualPatch'))
    if visual_audio_acceptance(parent, candidate, plan, provenance) != value:
        fail('已发布拼音音频继承证据摘要或内容变化')
    actions = speech_index(classroom)
    expected = speech_index(candidate['classroom'])
    entries = {(e['sceneId'], e['actionId']): e for e in audit.get('segments', [])}
    if (set(actions) != set(expected) or set(entries) != set(expected)
            or len(entries) != len(audit.get('segments', []))
            or audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('previewKey') != plan['previewKey']
            or audit.get('contract') != audit_contract_identity(plan)
            or audit.get('operatorParentProvenanceSha256') != provenance['sha256']
            or audit.get('sha256') != digest({k: v for k, v in audit.items() if k != 'sha256'})):
        fail('纯视觉目标审核必须覆盖全部原旁白并保留字面识别结果')
    validate_visual_candidate_content(candidate, classroom, media=media)
    receipts = {r['requestId']: r for r in parent['receipts']}
    media_index = {m['path']: m for m in media or []}
    results = []
    proofs = verify_inherited_segments(parent, candidate, plan, provenance,
        [(scene, action, receipts[action['audioId']]) for scene, action in expected.values()])
    for (identity, (scene, action)), proof in zip(expected.items(), proofs):
        receipt = receipts[action['audioId']]
        segment = next(s for s in candidate['inheritedSegments'] if (s['sceneId'], s['actionId']) == identity)
        entry = {**proof['sourceEntry'], 'comparison': proof['comparison'],
                 'similarityBps': proof['comparison']['similarityBps'],
                 'operatorParent': {'provenanceSha256': provenance['sha256'], 'sourceEntrySha256': segment['asrEntrySha256']}}
        actual = actions[identity][1]
        asset = media_index.get(actual.get('audioUrl'), {})
        if (entries[identity] != entry or actual['text'] != action['text'] or actual.get('audioId') != action['audioId']
                or actual.get('audioMetadata') != action.get('audioMetadata')
                or (media is not None and asset.get('sourceSha256', asset.get('sha256')) != receipt['audioSha256'])):
            fail('纯视觉目标音频、原文、回执或审核不再相同')
        results.append(proof['comparison']['passed'])
    if audit.get('passed') is not all(results):
        fail('不得把原字面 ASR 失败改写为通过')
    return entries


def validate_published_inheritance(frozen, release):
    """Delivery checks the new immutable proof, never reinterprets old releases."""
    proof, plan = frozen.get('operatorParent'), frozen.get('audioContract')
    if not isinstance(proof, dict) or not isinstance(plan, dict):
        fail('继承发布缺少独立配音计划和来源证明')
    from content.textbook_complete_scene_revision import PROVENANCE_SCHEMA as COMPLETE_PROVENANCE_SCHEMA
    if (proof.get('schemaVersion') not in {PROVENANCE_SCHEMA, QUIZ_PROVENANCE_SCHEMA, VISUAL_PROVENANCE_SCHEMA, COMPLETE_PROVENANCE_SCHEMA}
            or proof.get('sha256') != digest({k: v for k, v in proof.items() if k != 'sha256'})
            or proof.get('targetPreviewKey') != frozen['previewKey']
            or proof.get('targetPlanSha256') != digest(plan)
            or proof.get('targetClassroomId') != 'tbrev_' + str(proof.get('revisionId'))[:24]
            or proof['parent'].get('binding') != plan['binding'] or proof['parent'].get('teacher') != plan['teacher']
            or proof['parent'].get('contentKey') == frozen['contentKey']
            or release['audioAudit'].get('operatorParentProvenanceSha256') != proof['sha256']):
        fail('继承发布的来源或目标身份不一致')
    if proof['schemaVersion'] == QUIZ_PROVENANCE_SCHEMA:
        validate_quiz_revision_binding(proof, release['classroom'], media=release['media'])
    source = {(s['sceneId'], s['actionId']): s for s in proof['parent']['segments']}
    inherited = {(s['sceneId'], s['actionId']): s for s in proof['inheritedSegments']}
    if len(inherited) != len(proof['inheritedSegments']):
        fail('继承发布的段落身份重复')
    actions, media = speech_index(release['classroom']), {m['path']: m for m in release['media']}
    for alias in proof['parent'].get('audioAliases', []):
        scene = next((s for s in release['classroom']['scenes'] if s['id'] == alias['sceneId']), {})
        matches = [q for q in scene.get('content', {}).get('questions', []) if q.get('id') == alias['questionId']]
        segment = inherited.get((alias['sceneId'], alias['actionId']), {})
        asset = media.get(matches[0].get('questionAudioUrl'), {}) if len(matches) == 1 else {}
        if (len(matches) != 1 or sha_text(matches[0].get('question', '')) != alias['questionTextSha256']
                or segment.get('ttsRequestId') != alias['ttsRequestId'] or segment.get('audioSha256') != alias['audioSha256']
                or asset.get('sourceSha256', asset.get('sha256')) != alias['audioSha256']):
            fail('继承的旧题目别名没有保持准确的原已审核音频')
    for identity, segment in inherited.items():
        if source.get(identity) != segment or identity not in actions:
            fail('继承发布的段落不是冻结的父段落')
        action = actions[identity][1]
        asset = media.get(action.get('audioUrl'), {})
        if (action.get('audioId') != segment['ttsRequestId'] or sha_text(action['text'].strip()) != segment['textSha256']
                or asset.get('sourceSha256', asset.get('sha256')) != segment['audioSha256']):
            fail('继承发布的文本或交付音频发生变化')
    from content.textbook_parent_audio_restoration import validate_published_restorations
    validate_published_restorations(frozen, release)


def validate_quiz_revision_binding(proof, classroom, *, media=None, course_questions=None):
    """New picture quizzes keep their reviewed private question and audio pair.

    Publication changes media namespaces. Compare their original byte digests,
    not the delivery URL, and require the exact corresponding speech audio.
    """
    if proof.get('schemaVersion') != QUIZ_PROVENANCE_SCHEMA:
        return
    media_index = {m['path']: m for m in media or []}
    source_hashes = {a['mediaPath']: a['sha256'] for a in proof['parent']['originalMedia']['assets']}
    source_hashes.update({a['mediaPath']: a['sha256'] for a in proof['derivedImages']})
    scenes = {s['id']: s for s in classroom['scenes']}

    def normalize(value, *, delivered):
        if isinstance(value, dict):
            return {k: normalize(v, delivered=delivered) for k, v in value.items() if k != 'questionAudioUrl'}
        if isinstance(value, list):
            return [normalize(v, delivered=delivered) for v in value]
        if isinstance(value, str) and MEDIA.fullmatch(value):
            if delivered and media is not None:
                entry = media_index.get(value, {})
                result = entry.get('sourceSha256', entry.get('sha256'))
            else:
                result = source_hashes.get(value)
            if not result:
                fail('修订小测引用了未审核的题图')
            return {'imageSha256': result}
        return value

    seen = set()
    for binding in proof.get('quizBindings', []):
        identity = (binding['sceneId'], binding['questionId'])
        if identity in seen or binding['sceneId'] not in scenes:
            fail('修订小测绑定重复或缺失')
        seen.add(identity)
        scene = scenes[binding['sceneId']]
        items = [q for q in scene['content'].get('questions', []) if q['id'] == binding['questionId']]
        actions = [a for a in scene.get('actions', []) if a.get('type') == 'speech' and a['id'] == binding['actionId']]
        if (len(items) != 1 or len(actions) != 1
                or normalize(items[0], delivered=True) != normalize(binding['question'], delivered=False)
                or actions[0]['text'] != items[0]['question']
                or urlparse(actions[0].get('audioUrl', '')).path != items[0].get('questionAudioUrl')):
            fail('修订小测的私有题意、答案、题图或逐题语音发生变化')
        if course_questions is not None:
            snapshots = [q for q in course_questions if q['id'] == items[0]['id']]
            q = items[0]
            expected = {'id': q['id'], 'type': 'single_choice', 'prompt': q['question'],
                        'choices': [{'id': o['value'], 'text': o['label']} for o in q['options']],
                        'answer': q['answer'][0], 'explanation': q['analysis']}
            if len(snapshots) != 1 or {k: snapshots[0].get(k) for k in expected} != expected:
                fail('课程私有题库与修订小测不一致')
    if not seen:
        fail('修订小测缺少逐题绑定')
