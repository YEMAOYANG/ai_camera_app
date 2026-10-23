"""Complete-scene revision adoption, separate from the v1-v3 patch contracts.

An applied native revision is evidence of exact artifacts, never of play quality
or audio approval. Only unchanged scene/action/text identities inherit audio.
"""
from copy import deepcopy
import hashlib
import json

from content.textbook_catalog import canonical, digest, identifier, lesson_by_id
from content.textbook_authoring_candidate import (_scenes, _questions, _image_coverage,
                                                 ASSET_FIELDS, IMAGE_URL, IMAGE_REFERENCE)
from content.textbook_interactive_narration import AUDIO_BLOCK
from content.textbook_operator_revision import (AUDIO_FIELDS, fail, parse, sha_text,
                                              speech_index, validate_parent)
from content.textbook_review_followup import (PLAN_FIELDS, PLAN_SCHEMA, RECEIPT_FIELDS,
    RECEIPT_SCHEMA, _sealed, _unique_pairs, validate_complete_scene_review_followup)
from content.textbook_scene_contract import scene_digest, validate_scene_contract

PATCH_SCHEMA = 'mira.textbook.published-complete-scene-patch.v4'
PREVIEW_PATCH_SCHEMA = 'mira.textbook.unpublished-complete-scene-patch.v4'
PROVENANCE_SCHEMA = 'mira.textbook.operator-parent-complete-scene-provenance.v4'


def _json(raw):
    if not isinstance(raw, str):
        fail('完整场景归档必须保留原始 JSON 字节')
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (TypeError, ValueError):
        fail('完整场景归档 JSON 无效')


def validate_evidence(parent, evidence, *, unpublished=False):
    """Rebuild the applied native document from literal operator archives."""
    fields = {'authoring', 'summary', 'draftJson', 'frozenJson', 'stateJson',
              'ledgerJson', 'revisionFiles', 'media'}
    if not isinstance(evidence, dict) or set(evidence) != fields:
        fail('完整场景修订证据缺失')
    draft, frozen, state, ledger = [_json(evidence[k]) for k in
                                  ('draftJson', 'frozenJson', 'stateJson', 'ledgerJson')]
    authoring = evidence['authoring']
    sid, stage = authoring.get('sessionId'), authoring.get('stageId')
    if (not identifier(stage) or not isinstance(sid, str) or not sid
            or state.get('sessionId') != sid
            or stage not in {s.get('stageId') for s in state.get('savedStages', [])}
            or frozen.get('schemaVersion') != 'mira.operator.workbench-authoring.v3'
            or sha_text(evidence['draftJson']) != frozen.get('draftSha256')
            or digest(draft) != frozen.get('draftCanonicalSha256')
            or sha_text(draft.get('request', '')) != frozen.get('requestSha256')
            or draft.get('binding') != frozen.get('binding')
            or draft.get('teacherContract') != frozen.get('teacherContract')
            or ledger.get('sessionId') != sid or ledger.get('stageId') != stage
            or ledger.get('frozenContract') != frozen.get('sceneContract')
            or ledger.get('sha256') != digest({k: v for k, v in ledger.items() if k != 'sha256'})):
        fail('完整场景不是原冻结任务的已保存候选')
    try:
        contract = validate_scene_contract(frozen['sceneContract'], draft=draft,
            catalog_check=frozen['catalogCheck'], interaction_policy=frozen['interactionPolicy'])
    except (ValueError, KeyError, TypeError):
        fail('完整场景冻结合同无效')
    manifest, node = parent['manifest'], parent['preview']['node_id']
    unit, lesson = lesson_by_id(manifest, node)
    expected = {k: manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
    expected.update(nodeId=node, unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
    source_input = parse(parent['preview']['input_json'])
    old_authoring = source_input.get('authoring', {})
    old_candidate = source_input.get('authoringCandidate', {})
    if (any(contract['binding'].get(k) != v for k, v in expected.items())
            or any(old_authoring.get(k) != authoring.get(k) for k in ('sessionId', 'stageId'))
            or old_candidate and old_candidate.get('contractSha256') != frozen['sceneContract']['sha256']):
        fail('v4 必须保留同一教材和原 v3 冻结锁题身份')
    if unpublished:
        from content.textbook_unpublished_preview_origin import validate_preview_parent
        origin = validate_preview_parent(parent)
    else:
        origin = validate_parent(parent, allow_complete_scene=True)
    teacher = origin['teacher']
    teacher_identity = {'teacherProfileId': teacher['teacherProfile']['id'],
        'teacherProfileVersion': teacher['teacherProfile']['version'],
        'teacherProfileHash': teacher['teacherProfile']['contentHash'],
        'voiceId': teacher['voiceId'], 'languageCode': teacher['languageCode']}
    for key, value in teacher_identity.items():
        if frozen['teacherContract'].get(key) != value:
            fail('完整场景不能通过继承切换教师或声音合同')
    files = evidence['revisionFiles']
    if not isinstance(files, dict) or not files:
        fail('完整场景缺少正式修订原始文件')
    try:
        plan, receipt = _json(files['intent.json']), _json(files['receipt.json'])
        _sealed(plan, (PLAN_FIELDS, PLAN_FIELDS - {'assetAdditions'}), PLAN_SCHEMA)
        _sealed(receipt, (RECEIPT_FIELDS, RECEIPT_FIELDS - {'assetAdditions'}), RECEIPT_SCHEMA)
        before = _json(files['original-document.json'])
        original_ledger = _json(files['original-candidate.json'])
    except (KeyError, ValueError):
        fail('完整场景正式计划或回执缺失')
    if (plan['sessionId'] != sid or plan['stageId'] != stage
            or plan['contractSha256'] != frozen['sceneContract']['sha256']
            or plan['verification'] != 'static_review_only_not_play_audio_or_publication'
            or receipt.get('status') != 'static_candidate_review_revised'
            or receipt.get('verification') != plan['verification'] or receipt.get('providerCalls') != 0
            or any(receipt.get(k) != v for k, v in {
                'revisionId': plan['sha256'], 'planSha256': plan['sha256'], 'sessionId': sid,
                'stageId': stage, 'documentSha256': plan['afterDocumentSha256'],
                'candidateSha256': plan['afterCandidateSha256'],
                'candidateFileSha256': plan['afterCandidateFileSha256'],
                'revisions': plan['revisions'], 'stateTransitionNotes': plan['stateTransitionNotes']}.items())
            or receipt.get('assetAdditions', []) != plan.get('assetAdditions', [])
            or scene_digest(before) != plan['beforeDocumentSha256']
            or original_ledger.get('sha256') != plan['beforeCandidateSha256']
            or original_ledger.get('sha256') != digest({k: v for k, v in original_ledger.items() if k != 'sha256'})
            or original_ledger.get('frozenContract') != ledger['frozenContract']
            or original_ledger.get('sessionId') != sid or original_ledger.get('stageId') != stage
            or sha_text(files['original-candidate.json']) != plan['beforeCandidateFileSha256']
            or ledger['sha256'] != plan['afterCandidateSha256']
            or sha_text(evidence['ledgerJson']) != plan['afterCandidateFileSha256']):
        fail('完整场景正式回执与原始或当前字节不同')
    after, seen = deepcopy(before), set()
    for revision in plan['revisions']:
        scene_id, proof = revision.get('sceneId'), revision.get('completeSceneEvidence')
        if scene_id in seen or not isinstance(proof, dict):
            fail('v4 只采用明确完整场景替换，不能混入自由字段修改')
        seen.add(scene_id)
        suffix = sha_text(scene_id)
        try:
            raw = files['replacement-scene-' + suffix + '.json']
            replacement = _json(raw)
            declared_raw = files['declared-original-scene-' + suffix + '.json']
            declared = _json(declared_raw)
            old = _json(files['original-scene-' + suffix + '.json'])
        except KeyError:
            fail('完整场景必须保留原始和替换文件')
        current = next((s for s in after['scenes'] if s['id'] == scene_id), None)
        identity = ('stageId', 'order', 'type', 'title', 'outlineId', 'createdAt')
        if (current != old or replacement.get('id') != scene_id or declared.get('id') != scene_id
                or proof.get('exactSceneId') != scene_id
                or proof.get('frozenContractSha256') != plan['contractSha256']
                or proof.get('currentSceneSha256') != scene_digest(old)
                or proof.get('originalSceneSha256') != scene_digest(declared)
                or proof.get('replacementSceneSha256') != scene_digest(replacement)
                or proof.get('originalSceneFileSha256') != sha_text(declared_raw)
                or proof.get('replacementSceneFileSha256') != sha_text(raw)
                or revision.get('beforeSceneSha256') != scene_digest(old)
                or revision.get('afterSceneSha256') != scene_digest(replacement)
                or any(old.get(k) != replacement.get(k) or declared.get(k) != old.get(k) for k in identity)):
            fail('完整场景原始身份或替换内容摘要已改变')
        after['scenes'] = [replacement if s['id'] == scene_id else s for s in after['scenes']]
    if not seen or scene_digest(after) != plan['afterDocumentSha256']:
        fail('完整场景不能重建正式修订后的准确文档')
    room = {'id': stage, 'stage': after['stage'], 'scenes': after['scenes']}
    _scenes(ledger, room, contract)
    assets = {a['assetKey']: a for a in ledger['assetBindings']}
    if len(assets) != len(ledger['assetBindings']) or any(
            set(a) != ASSET_FIELDS or not IMAGE_URL.fullmatch(a.get('src', ''))
            or IMAGE_URL.fullmatch(a['src'])[1] != stage
            or a.get('status') != 'author_candidate' for a in assets.values()):
        fail('完整场景图片身份无效')
    _questions(room, contract, assets)
    _image_coverage(room, contract, assets)
    references = set(IMAGE_REFERENCE.findall(canonical(room)))
    media = evidence['media'].get('assets', [])
    by_path = {a['src']: a for a in assets.values()}
    if ({a.get('mediaPath') for a in media} != references or len(media) != len(references)
            or any(a.get('sha256') != by_path.get(a.get('mediaPath'), {}).get('sha256') for a in media)):
        fail('完整场景素材清单必须精确覆盖已绑定图片')
    summary = evidence['summary']
    followup = summary.get('completeSceneReviewFollowup')
    try:
        validate_complete_scene_review_followup(followup, candidate_source_sha256=digest(room), candidate=summary)
    except (ValueError, TypeError):
        fail('完整场景必须携带当前规则的后续质量审核绑定')
    if (summary['sha256'] != ledger['sha256'] or summary['contractSha256'] != plan['contractSha256']
            or followup['revisionIds'][-1] != plan['sha256']
            or followup['revisionReceiptSha256s'][-1] != receipt['sha256']
            or followup['candidateFileSha256'] != sha_text(evidence['ledgerJson'])):
        fail('当前完整场景与质量审核来源不一致')
    return room, origin


def complete_scene_candidate(parent, patch, evidence):
    unpublished = isinstance(patch, dict) and patch.get('schemaVersion') == PREVIEW_PATCH_SCHEMA
    parent_field = 'parentPreviewKey' if unpublished else 'parentContentKey'
    fields = {'schemaVersion', 'parentContentKey', 'expectedSourceSha256', 'teachingRevision',
              'reviewer', 'basis', 'nativeSessionId', 'nativeStageId', 'nativeRevisionId',
              'expectedCandidateSha256', 'evidenceSha256'}
    fields.discard('parentContentKey'); fields.add(parent_field)
    old_revision = parse(parent['preview']['input_json']).get('teachingRevision') if unpublished else parent['build']['teaching_revision']
    if (not isinstance(patch, dict) or set(patch) != fields or patch.get('schemaVersion') not in {PATCH_SCHEMA, PREVIEW_PATCH_SCHEMA}
            or not identifier(patch.get('teachingRevision'))
            or patch['teachingRevision'] == old_revision
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or digest(evidence) != patch['evidenceSha256']):
        fail('v4 需要明确的完整场景来源和不同教学版本')
    target, origin = validate_evidence(parent, evidence, unpublished=unpublished)
    followup = evidence['summary']['completeSceneReviewFollowup']
    if (patch[parent_field] != origin['previewKey' if unpublished else 'contentKey'] or patch['expectedSourceSha256'] != origin['classroomSha256']
            or patch['nativeSessionId'] != followup['sessionId'] or patch['nativeStageId'] != followup['stageId']
            or patch['nativeRevisionId'] != followup['revisionIds'][-1]
            or patch['expectedCandidateSha256'] != followup['candidateSha256']):
        fail('v4 的父发布或正式修订摘要已变化')
    return build_complete_scene_candidate(parent, patch, evidence, target, origin)


def build_complete_scene_candidate(parent, patch, evidence, target, origin):
    """Shared transformation after a source-specific evidence gate succeeds."""
    target = deepcopy(target)
    source_identity = ({'parentPreviewEvidenceSha256': origin['sourceIdentitySha256']}
                       if origin.get('sourceKind') == 'audited-unpublished-preview'
                       else {'parentReleaseSha256': origin['releaseSha256']})
    revision_id = digest({**source_identity, 'patch': patch, 'visualPatch': None})
    cid = 'tbrev_' + revision_id[:24]
    source = parse(parent['preview']['classroom_json'])
    source_actions, target_actions = speech_index(source), speech_index(target)
    inherited, modified, added = [], [], []
    segments = {(s['sceneId'], s['actionId']): s for s in origin['segments']}
    for key, (_, action) in target_actions.items():
        for field in AUDIO_FIELDS:
            action.pop(field, None)
        old = source_actions.get(key)
        if old and old[1]['text'] == action['text'] and key in segments:
            segment = segments[key]
            inherited.append(segment)
            for field in AUDIO_FIELDS:
                action[field] = deepcopy(old[1][field])
            action['audioUrl'] = f"/api/classroom-media/{cid}/audio/{segment['ttsRequestId']}.wav"
        else:
            (modified if old else added).append(list(key))
    for scene in target['scenes']:
        scene['stageId'] = cid
        if scene['type'] == 'interactive':
            scene['content']['html'] = AUDIO_BLOCK.sub('', scene['content']['html'])
        for q in scene.get('content', {}).get('questions', []):
            for field in ('questionAudioUrl', 'questionAudioBinding'):
                q.pop(field, None)
            for feedback in (q.get('optionFeedback') or {}).values():
                feedback.pop('audioUrl', None)
                feedback.pop('audioBinding', None)
    target['id'] = target['stage']['id'] = cid
    return {'revisionId': revision_id, 'parent': origin, 'patch': deepcopy(patch), 'visualPatch': None,
            'completeSceneEvidence': deepcopy(evidence), 'classroom': target,
            'changedSegments': sorted(modified + added), 'modifiedSegments': sorted(modified),
            'addedSegments': sorted(added), 'deletedSegments': [list(k) for k in sorted(set(source_actions) - set(target_actions))],
            'inheritedSegments': inherited}
