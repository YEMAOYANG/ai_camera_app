"""Explicit adoption of a reviewed legacy v2 body, never a fabricated v3 ledger.

The original publication and authoring request remain immutable. This validates
source identity and locked assessments; it does not certify pedagogical quality.
"""
from copy import deepcopy
import json
import re

from content.textbook_catalog import canonical, digest, identifier, lesson_by_id
from content.textbook_complete_scene_revision import _json, build_complete_scene_candidate
from content.textbook_interaction_policy import interaction_policy_prompt
from content.textbook_interactive_narration import AUDIO_BLOCK
from content.textbook_operator_revision import AUDIO_FIELDS, fail, parse, sha_text, speech_index, validate_parent
from content.textbook_release import validate_release

PATCH_SCHEMA = 'mira.textbook.published-legacy-complete-scene-patch.v4'
SUMMARY_SCHEMA = 'mira.textbook.legacy-complete-scene-candidate.v4'
BUNDLE_SCHEMA = 'mira.textbook.legacy-revision-source-bundle.v1'
IMAGE = re.compile(r'/review-assets/[A-Za-z0-9_./-]+\.(?:png|jpg|jpeg|webp)')
DOCUMENTS = ('candidate', 'replacementBody', 'parentClassroom', 'preparedRelease',
             'publicationReceipt', 'frozen', 'draft', 'sourceReview', 'lockedAssessments',
             'newPolicy', 'audioDelta')


def document_references(bundle):
    return {**{k: bundle[k] for k in ('candidate', 'replacementBody', 'audioDelta')},
        **{k: bundle['parent'][v] for k, v in (
            ('parentClassroom', 'classroom'), ('preparedRelease', 'preparedRelease'),
            ('publicationReceipt', 'publicationReceipt'))},
        **{k: bundle['legacyAuthority'][k] for k in
           ('frozen', 'draft', 'sourceReview', 'lockedAssessments')},
        'newPolicy': bundle['newPolicy']['source']}


def body_without_audio(room):
    value = deepcopy(room)
    for scene in value['scenes']:
        for action in scene['actions']:
            for key in AUDIO_FIELDS:
                action.pop(key, None)
        if scene['type'] == 'interactive':
            scene['content']['html'] = AUDIO_BLOCK.sub('', scene['content']['html'])
        for question in scene.get('content', {}).get('questions', []):
            for key in ('questionAudioUrl', 'questionAudioBinding'):
                question.pop(key, None)
            for feedback in (question.get('optionFeedback') or {}).values():
                for key in ('audioUrl', 'audioBinding'):
                    feedback.pop(key, None)
    return value


def mapped_body(body, assets, bundle_sha):
    """Only the reviewed image URLs change; record the immutable namespace."""
    serialized = canonical(body)
    media = []
    for asset in assets:
        suffix = '.' + asset['reviewUrl'].rsplit('.', 1)[1]
        path = f"/api/classroom-media/legacy-review-{bundle_sha[:24]}/media/{asset['sourceFileSha256']}{suffix}"
        serialized = serialized.replace(asset['reviewUrl'], path)
        media.append({'id': asset['assetKey'], 'file': asset['sourceFileSha256'] + suffix,
            'sha256': asset['sourceFileSha256'], 'mediaPath': path,
            'provenance': {'kind': 'explicit-legacy-body-revision', 'reviewUrl': asset['reviewUrl'],
                'sourceReceiptFileSha256': asset['sourceReceiptFileSha256'], 'sourceBundleSha256': bundle_sha}})
    return json.loads(serialized), {'schemaVersion': 'mira.textbook.lesson-media.v1', 'version': '1', 'assets': media}


def legacy_metadata(parent, bundle, bundle_sha, body):
    old = parse(parent['preview']['input_json'])['authoring']
    authoring = {**deepcopy(old), 'legacyBodyRevision': {
        'schemaVersion': 'mira.textbook.legacy-authoring-provenance.v4',
        'sourceBundleSha256': bundle_sha,
        'originalFrozenFileSha256': bundle['legacyAuthority']['frozen']['fileSha256'],
        'originalAuthoringSchemaVersion': 'mira.operator.workbench-authoring.v2',
        'verification': 'literal_legacy_source_and_locked_assessments_not_native_ledger_or_play_approval'}}
    summary = {'schemaVersion': SUMMARY_SCHEMA, 'sourceBundleSha256': bundle_sha,
        'sha256': digest(body), 'interactionPolicyVersion': bundle['newPolicy']['version'],
        'interactionPolicySha256': bundle['newPolicy']['canonicalSha256'],
        'qualityReviewRequired': True,
        'verification': 'legacy_body_source_only_not_audio_play_review_or_publication'}
    return authoring, summary


def _locked_questions(room, locked):
    actual = [(s, q) for s in room['scenes'] for q in s.get('content', {}).get('questions', [])]
    if len(actual) != len(locked) or not locked:
        fail('旧版修订必须完整保留原锁题数量与顺序')
    for (scene, question), old in zip(actual, locked):
        options = [{k: choice[k] for k in ('value', 'label')} for choice in old['choices']]
        answer = old['answer'] if isinstance(old['answer'], list) else [old['answer']]
        if (scene['order'] != old['page'] or scene['type'] != 'quiz'
                or any(question.get(k) != old[k] for k in ('id', 'type', 'points', 'question', 'analysis'))
                or question.get('answer') != answer or question.get('options') != options
                or set(question.get('optionVisuals', {})) != {o['value'] for o in options}):
            fail('旧版完整场景修订不能改动原锁题身份、正文或选项顺序')
        speeches = [a for a in scene['actions'] if a['type'] == 'speech']
        stem = next((i for i, a in enumerate(speeches)
                     if a['id'] == question.get('speechActionId') and a['text'] == question['question']), None)
        if stem is None:
            fail('旧版锁题必须绑定本题原文的独立旁白')
        feedback_texts = []
        for key, feedback in question.get('optionFeedback', {}).items():
            text = feedback.get('text')
            matches = [i for i, a in enumerate(speeches) if a['text'] == text]
            if key not in question['optionVisuals'] or len(matches) != 1 or matches[0] <= stem or text in feedback_texts:
                fail('选项反馈必须有题干后唯一的逐字旁白')
            feedback_texts.append(text)


def validate_legacy_evidence(parent, evidence):
    fields = {'sourceBundleJson', 'documents', 'assetReceipts', 'authoring', 'summary', 'media'}
    if not isinstance(evidence, dict) or set(evidence) != fields:
        fail('旧版完整场景需要独立来源证据，不能冒充原生账本')
    bundle = _json(evidence['sourceBundleJson'])
    bundle_sha = sha_text(evidence['sourceBundleJson'])
    if bundle.get('schemaVersion') != BUNDLE_SCHEMA:
        fail('旧版完整场景来源包版本不受支持')
    refs = document_references(bundle)
    raw = evidence['documents']
    if not isinstance(raw, dict) or set(raw) != set(DOCUMENTS):
        fail('旧版完整场景原始文档不完整')
    docs = {}
    for key, ref in refs.items():
        docs[key] = _json(raw[key])
        if sha_text(raw[key]) != ref.get('fileSha256') or (
                'canonicalSha256' in ref and digest(docs[key]) != ref['canonicalSha256']):
            fail('旧版完整场景原始文档摘要不一致：' + key)
    origin = validate_parent(parent, allow_complete_scene=True)
    release = validate_release(parent['build'], parent['manifest'])
    parent_bundle, prepared, receipt = bundle['parent'], docs['preparedRelease'], docs['publicationReceipt']
    if (prepared.get('release') != release or docs['parentClassroom'] != release['classroom']
            or any(parent_bundle.get(k) != release.get(k) for k in ('classroomId', 'contentKey'))
            or parent_bundle.get('releaseSha256') != origin['releaseSha256']
            or receipt.get('status') != 'published' or receipt.get('ok') is not True
            or any(receipt.get(k) != parent_bundle.get(k) for k in ('classroomId', 'contentKey', 'releaseSha256'))):
        fail('旧版完整场景必须追溯到真实父发布')
    frozen, draft, authority = docs['frozen'], docs['draft'], bundle['legacyAuthority']
    if (frozen.get('schemaVersion') != 'mira.operator.workbench-authoring.v2'
            or 'sceneContract' in frozen or authority.get('sceneContractPresent') is not False
            or authority.get('authoringCandidateLedgerPresent') is not False
            or authority.get('mustNotFabricateLegacyContractOrLedger') is not True
            or sha_text(raw['draft']) != frozen.get('draftSha256')
            or digest(draft) != frozen.get('draftCanonicalSha256')
            or sha_text(draft.get('request', '')) != frozen.get('requestSha256')
            or draft.get('binding') != frozen.get('binding')
            or draft.get('teacherContract') != frozen.get('teacherContract')
            or not (docs['sourceReview'] == draft.get('sourceReview') or
                    isinstance(draft.get('sourceReview'), str) and
                    refs['sourceReview']['path'].endswith('/' + draft['sourceReview']))
            or docs['sourceReview'].get('binding') != draft['binding']
            or docs['lockedAssessments'] != draft.get('lockedAssessments')):
        fail('旧版冻结、来源范围或锁题原文不一致')
    manifest, node = parent['manifest'], parent['build']['node_id']
    unit, lesson = lesson_by_id(manifest, node)
    expected = {k: manifest[k] for k in ('editionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
    expected.update(nodeId=node, unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
    if any(draft['binding'].get(k) != v for k, v in expected.items()):
        fail('旧版修订不能切换教材或课次')
    teacher = origin['teacher']
    teacher_fields = {'teacherProfileId': teacher['teacherProfile']['id'],
        'teacherProfileVersion': teacher['teacherProfile']['version'],
        'teacherProfileHash': teacher['teacherProfile']['contentHash'],
        'voiceId': teacher['voiceId'], 'languageCode': teacher['languageCode']}
    if any(frozen['teacherContract'].get(k) != v for k, v in teacher_fields.items()):
        fail('旧版修订不能改变冻结教师')
    policy = {'schemaVersion': 'mira.frozen-interaction-policy.v1', 'policy': docs['newPolicy'],
              'sha256': bundle['newPolicy']['canonicalSha256']}
    interaction_policy_prompt(policy)
    if policy['policy']['version'] != bundle['newPolicy']['version'] or policy['policy']['version'] < 2:
        fail('旧版完整场景修订需要独立冻结当前整课质量规则')
    body = docs['replacementBody']
    if body_without_audio(docs['candidate']) != body:
        fail('旧版替换正文只能从准确已审候选移除音频绑定')
    source = parse(parent['preview']['classroom_json'])
    identity = lambda room: [(s['id'], s['order'], s['type'], s.get('title')) for s in room['scenes']]
    if identity(body) != identity(source) or any(s.get('stageId') != body['id'] for s in body['scenes']):
        fail('旧版完整场景必须保留原场景身份与顺序')
    speech_index(body)
    if any(not 1 <= len([a for a in s['actions'] if a['type'] == 'speech']) <= 20 for s in body['scenes']):
        fail('旧版修订每场景旁白必须在原技术上限内')
    _locked_questions(body, docs['lockedAssessments'])
    additions = bundle['assetAdditions']
    urls = [a['reviewUrl'] for a in additions]
    keys = [a['assetKey'] for a in additions]
    if (len(set(urls)) != len(urls) or len(set(keys)) != len(keys)
            or set(IMAGE.findall(canonical(body))) != set(urls)
            or set(evidence['assetReceipts']) != set(keys)):
        fail('旧版图片来源清单必须唯一且精确覆盖候选')
    for asset in additions:
        receipt_raw = evidence['assetReceipts'][asset['assetKey']]
        item = _json(receipt_raw)
        if (sha_text(receipt_raw) != asset['sourceReceiptFileSha256']
                or item.get('schemaVersion') != 'mira.textbook.review-asset-source-receipt.v1'
                or any(item.get(k) != asset[k] for k in ('assetKey', 'sourceFilePath', 'sourceFileSha256', 'reviewUrl'))
                or any(not item.get(k) for k in ('kind', 'role', 'source'))):
            fail('旧版图片来源回执与原始字节不一致')
    mapped, media = mapped_body(body, additions, bundle_sha)
    authoring, summary = legacy_metadata(parent, bundle, bundle_sha, mapped)
    if evidence['media'] != media or evidence['authoring'] != authoring or evidence['summary'] != summary:
        fail('旧版图片映射或当前规则绑定已变化')
    return mapped, origin


def legacy_complete_scene_candidate(parent, patch, evidence):
    fields = {'schemaVersion', 'parentContentKey', 'expectedSourceSha256', 'teachingRevision',
              'reviewer', 'basis', 'sourceBundlePath', 'expectedSourceBundleSha256', 'evidenceSha256'}
    if (not isinstance(patch, dict) or set(patch) != fields or patch.get('schemaVersion') != PATCH_SCHEMA
            or not identifier(patch.get('teachingRevision'))
            or patch['teachingRevision'] == parent['build']['teaching_revision']
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis', 'sourceBundlePath'))
            or digest(evidence) != patch['evidenceSha256']):
        fail('旧版 v4 需要准确来源和独立教学版本')
    target, origin = validate_legacy_evidence(parent, evidence)
    if (patch['parentContentKey'] != origin['contentKey'] or patch['expectedSourceSha256'] != origin['classroomSha256']
            or patch['expectedSourceBundleSha256'] != sha_text(evidence['sourceBundleJson'])):
        fail('旧版 v4 父发布或来源包摘要已变化')
    return build_complete_scene_candidate(parent, patch, evidence, target, origin)
