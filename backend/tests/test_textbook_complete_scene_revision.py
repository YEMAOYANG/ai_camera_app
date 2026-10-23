"""Synthetic complete-scene receipts; no providers, network or production data."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_complete_scene_revision import PATCH_SCHEMA, PREVIEW_PATCH_SCHEMA, complete_scene_candidate, validate_evidence
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_interactive_narration import AUDIO_BLOCK
from content.textbook_operator_revision import (AUDIO_FIELDS, inheritance_provenance, revision_candidate,
    sha_text, validate_parent, verify_inherited_segments)
from content.textbook_preview_audio_contract import new_audio_plan, compare_transcript
from content.textbook_scene_contract import freeze_scene_contract
from core.errors import ApiError
from services.course_reuse_resolver import lesson_scope
from services.textbook_preview_audio import core_content
from services.textbook_operator_revision_service import target_input
from tests.test_textbook_operator_revision import parent_fixture


def fixture():
    parent = parent_fixture(v2=True, quiz_intro=True, authoring={
        'mode': 'openmaic_pro_workbench', 'request': 'Synthetic original authoring request.',
        'sessionId': 'complete-scene-test', 'stageId': 'original-operator'})
    origin = validate_parent(parent)
    manifest, node = parent['manifest'], parent['build']['node_id']
    source = json.loads(parent['preview']['classroom_json'])
    stage, session = source['id'], 'complete-scene-test'
    body = deepcopy(source)
    body.pop('createdAt')
    for scene in body['scenes']:
        scene.update(stageId=stage, title=scene['id'])
        for action in scene['actions']:
            for key in AUDIO_FIELDS:
                action.pop(key, None)
        if scene['type'] == 'interactive':
            scene['content']['html'] = AUDIO_BLOCK.sub('', scene['content']['html'])
    q = body['scenes'][2]['content']['questions'][0]
    q.pop('questionAudioUrl'); q['points'] = 10
    q['optionVisuals']['B']['src'] = f'/api/classroom-media/{stage}/media/second.png'
    body['scenes'][2]['actions'] = [a for a in body['scenes'][2]['actions'] if a['id'] != 'quiz-intro']
    unit, lesson = lesson_by_id(manifest, node)
    binding = {k: manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
    binding.update(nodeId=node, unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
    teacher = origin['teacher']
    draft = {'binding': binding, 'request': 'Synthetic original authoring request.',
        'teacherContract': {'subject': manifest['subject'], 'teacherName': teacher['teacherName'],
            'teacherProfileId': teacher['teacherProfile']['id'], 'teacherProfileVersion': teacher['teacherProfile']['version'],
            'teacherProfileHash': teacher['teacherProfile']['contentHash'],
            'voiceId': teacher['voiceId'], 'languageCode': teacher['languageCode']},
        'qualityRules': ['Picture and voice support.'], 'scopeReview': {'status': 'synthetic'},
        'pagePlan': [{'page': s['order'], 'type': s['type'], 'title': s['title'], 'move': 'Observe or respond.',
                      **({'questionIds': [q['id']]} if s['type'] == 'quiz' else {})} for s in body['scenes']],
        'lockedAssessments': [{**{k: q[k] for k in ('id', 'type', 'points', 'question', 'analysis')}, 'page': 3,
            'answer': q['answer'][0], 'choices': [{**o, 'asset': 'first' if o['value'] == 'A' else 'second'} for o in q['options']]}]}
    draft_raw = canonical(draft) + '\n'
    check = {'manifestSha256': digest(manifest), 'lessonScopeSha256': lesson_scope(manifest, node)}
    policy = freeze_interaction_policy()
    frozen = {'schemaVersion': 'mira.operator.workbench-authoring.v3', 'binding': binding,
        'teacherContract': draft['teacherContract'], 'catalogCheck': check, 'interactionPolicy': policy,
        'draftSha256': sha_text(draft_raw), 'draftCanonicalSha256': digest(draft), 'requestSha256': sha_text(draft['request']),
        'sceneContract': freeze_scene_contract(draft, check, policy)}
    authoring = {**json.loads(parent['preview']['input_json'])['authoring'], 'sessionId': session, 'stageId': stage}
    assets = [{'assetKey': key, 'src': f'/api/classroom-media/{stage}/media/{name}.png',
        'sha256': digest(key), 'width': 64, 'height': 64, 'bindingVersion': 1, 'status': 'author_candidate'}
        for key, name in [('first', 'picture'), ('second', 'second')]]
    def ledger(room):
        value = {'schemaVersion': 'mira.textbook.authoring-candidate.v1', 'sessionId': session, 'stageId': stage,
            'frozenContract': frozen['sceneContract'], 'status': 'author_candidate',
            'verification': 'static_contract_only_not_play_or_semantic_review', 'assetBindings': assets,
            'bindingHistory': [], 'scenes': [{'sceneId': s['id'], 'order': s['order'], 'canonicalJson': canonical(s),
                'sha256': digest(s), 'contractSha256': frozen['sceneContract']['sha256']} for s in room['scenes']]}
        return {**value, 'sha256': digest(value)}
    before = {'dslVersion': '1', 'stage': body['stage'], 'scenes': deepcopy(body['scenes']), 'outline': {'producerRef': session}}
    original_ledger = ledger(body)
    body['scenes'][0]['actions'][0]['text'] = '目，就是眼睛，我们用眼睛来看书。'
    body['scenes'][0]['actions'].append({'id': 'new-feedback', 'type': 'speech', 'text': '再看一看。'})
    after = {**deepcopy(before), 'scenes': deepcopy(body['scenes'])}
    current_ledger = ledger(body)
    old, replacement = before['scenes'][0], after['scenes'][0]
    suffix = sha_text(old['id'])
    raw = lambda value: canonical(value) + '\n'
    complete = {'exactSceneId': old['id'], 'frozenContractSha256': frozen['sceneContract']['sha256'],
        'originalSceneSha256': digest(old), 'currentSceneSha256': digest(old),
        'replacementSceneSha256': digest(replacement), 'reason': 'Synthetic reviewed body repair.',
        'preservedIdentity': {k: old.get(k) for k in ('stageId', 'order', 'type', 'title', 'outlineId', 'createdAt')},
        'originalSceneFileSha256': sha_text(raw(old)), 'replacementSceneFileSha256': sha_text(raw(replacement)), 'assetAdditions': []}
    revision = {'sceneId': old['id'], 'beforeSceneSha256': digest(old), 'afterSceneSha256': digest(replacement),
                'completeSceneEvidence': complete}
    plan = {'schemaVersion': 'mira.textbook.current-review-revision-plan.v1',
        'verification': 'static_review_only_not_play_audio_or_publication', 'input': {}, 'dataDir': 'synthetic',
        'sessionId': session, 'stageId': stage, 'ownerFingerprint': digest('owner'),
        'contractSha256': frozen['sceneContract']['sha256'], 'beforeDocumentSha256': digest(before),
        'afterDocumentSha256': digest(after), 'beforeCandidateSha256': original_ledger['sha256'],
        'beforeCandidateFileSha256': sha_text(raw(original_ledger)), 'afterCandidateSha256': current_ledger['sha256'],
        'afterCandidateFileSha256': sha_text(raw(current_ledger)), 'assetAdditions': [],
        'stateTransitionNotes': ['Synthetic repair.'], 'revisions': [revision]}
    plan['sha256'] = digest(plan)
    receipt = {'schemaVersion': 'mira.textbook.current-review-revision-receipt.v1', 'revisionId': plan['sha256'],
        'status': 'static_candidate_review_revised', 'verification': plan['verification'], 'sessionId': session,
        'stageId': stage, 'planSha256': plan['sha256'], 'documentSha256': plan['afterDocumentSha256'],
        'candidateSha256': plan['afterCandidateSha256'], 'candidateFileSha256': plan['afterCandidateFileSha256'],
        'stateTransitionNotes': plan['stateTransitionNotes'], 'revisions': plan['revisions'], 'assetAdditions': [], 'providerCalls': 0}
    receipt['sha256'] = digest(receipt)
    followup = {'schemaVersion': 'mira.textbook.complete-scene-review-followup.v1', 'status': 'quality_review_required',
        'verification': 'sealed_complete_scene_revision_chain_and_current_candidate', 'sessionId': session, 'stageId': stage,
        'baseInteractionPolicyVersion': policy['policy']['version'], 'baseInteractionPolicySha256': policy['sha256'],
        'currentInteractionPolicyVersion': policy['policy']['version'], 'currentInteractionPolicySha256': policy['sha256'],
        'wholeCourseQualityContractSha256': digest(policy['policy']['wholeCourseQualityContract']),
        'candidateSourceSha256': digest(body), 'candidateSha256': current_ledger['sha256'],
        'candidateFileSha256': sha_text(raw(current_ledger)), 'revisionIds': [plan['sha256']],
        'revisionReceiptSha256s': [receipt['sha256']], 'completeSceneIds': ['slide']}
    followup['sha256'] = digest(followup)
    evidence = {'authoring': authoring, 'draftJson': draft_raw, 'frozenJson': raw(frozen),
        'stateJson': raw({'sessionId': session, 'savedStages': [{'stageId': stage}]}), 'ledgerJson': raw(current_ledger),
        'revisionFiles': {'intent.json': raw(plan), 'receipt.json': raw(receipt), 'original-document.json': raw(before),
            'original-candidate.json': raw(original_ledger), 'original-scene-' + suffix + '.json': raw(old),
            'declared-original-scene-' + suffix + '.json': raw(old), 'replacement-scene-' + suffix + '.json': raw(replacement)},
        'summary': {'sha256': current_ledger['sha256'], 'contractSha256': frozen['sceneContract']['sha256'],
            'interactionPolicyVersion': policy['policy']['version'], 'interactionPolicySha256': policy['sha256'],
            'completeSceneReviewFollowup': followup},
        'media': {'assets': [{'mediaPath': a['src'], 'sha256': a['sha256']} for a in assets]}}
    patch = {'schemaVersion': PATCH_SCHEMA, 'parentContentKey': parent['build']['content_key'],
        'expectedSourceSha256': parent['preview']['classroom_sha256'], 'teachingRevision': '4',
        'reviewer': 'synthetic', 'basis': 'Complete-scene test.', 'nativeSessionId': session, 'nativeStageId': stage,
        'nativeRevisionId': plan['sha256'], 'expectedCandidateSha256': current_ledger['sha256'], 'evidenceSha256': digest(evidence)}
    return parent, patch, evidence


class CompleteSceneRevisionTests(unittest.TestCase):
    def test_unpublished_source_retains_failed_audit_and_does_not_inherit_unchanged_failed_line(self):
        parent, patch, evidence = fixture()
        parent.pop('build')
        patch.update(schemaVersion=PREVIEW_PATCH_SCHEMA, parentPreviewKey=parent['preview']['preview_key'])
        patch.pop('parentContentKey')
        entry = next(e for e in parent['audit']['segments'] if e['sceneId'] == 'interactive')
        entry['transcript'] = '完全不同的声音。'
        entry['asr'].update(transcript=entry['transcript'], transcriptSha256=sha_text(entry['transcript']))
        entry['comparison'] = compare_transcript(parent['plan'], entry['text'], entry['transcript'])
        entry['similarityBps'] = entry['comparison']['similarityBps']
        parent['audit']['passed'] = False
        parent['audit']['sha256'] = digest({k: v for k, v in parent['audit'].items() if k != 'sha256'})
        before = deepcopy(parent)
        candidate = revision_candidate(parent, patch, complete_scene_evidence=evidence)
        self.assertEqual(parent, before)
        self.assertNotIn('releaseSha256', candidate['parent'])
        self.assertFalse(candidate['parent']['sourceAuditPassed'])
        self.assertIn(['interactive', entry['actionId']], candidate['modifiedSegments'])
        self.assertFalse(any(s['sceneId'] == 'interactive' for s in candidate['inheritedSegments']))
        frozen = target_input(parent, candidate)
        plan = new_audio_plan(preview_key=frozen['previewKey'], classroom_sha256=digest(candidate['classroom']),
            core_sha256=digest(core_content(candidate['classroom'])), frozen_input=frozen)
        proof = inheritance_provenance(candidate, plan)
        self.assertEqual(proof['parent']['sourceKind'], 'audited-unpublished-preview')
        with self.assertRaises((ApiError, KeyError)):
            revision_candidate(parent, {**patch, 'schemaVersion': PATCH_SCHEMA}, complete_scene_evidence=evidence)

    def test_separate_identity_exact_inheritance_delta_and_deleted_slots(self):
        parent, patch, evidence = fixture()
        original = deepcopy(parent)
        candidate = revision_candidate(parent, patch, complete_scene_evidence=evidence)
        self.assertEqual(parent, original)
        self.assertEqual(candidate['modifiedSegments'], [['slide', 'line-slide']])
        self.assertEqual(candidate['addedSegments'], [['slide', 'new-feedback']])
        self.assertEqual(candidate['deletedSegments'], [['quiz', 'quiz-intro']])
        self.assertEqual(len(candidate['inheritedSegments']), 2)
        self.assertNotEqual(candidate['classroom']['id'], parent['preview']['classroom_id'])
        frozen = target_input(parent, candidate)
        plan = new_audio_plan(preview_key=frozen['previewKey'], classroom_sha256=digest(candidate['classroom']),
            core_sha256=digest(core_content(candidate['classroom'])), frozen_input=frozen)
        proof = inheritance_provenance(candidate, plan)
        clips = [(s, a, next(r for r in parent['receipts'] if r['requestId'] == a['audioId']))
                 for s in candidate['classroom']['scenes'] for a in s['actions'] if a.get('audioId')]
        self.assertEqual(len(verify_inherited_segments(parent, candidate, plan, proof, clips)), 2)
        self.assertEqual(proof['addedSegments'], candidate['addedSegments'])
        self.assertEqual(frozen['authoringCandidate']['completeSceneReviewFollowup']['candidateSourceSha256'], frozen['sourceSha256'])

    def test_stale_receipt_replacement_or_media_rejected_even_if_outer_patch_is_resealed(self):
        for mutate in (
            lambda e: e['revisionFiles'].__setitem__('receipt.json', e['revisionFiles']['receipt.json'].replace('static_candidate_review_revised', 'passed')),
            lambda e: e['revisionFiles'].__setitem__('replacement-scene-' + sha_text('slide') + '.json', '{}'),
            lambda e: e['media']['assets'][0].update(sha256='0' * 64),
            lambda e: e['authoring'].update(sessionId='another-session'),
        ):
            parent, patch, evidence = fixture(); mutate(evidence); patch['evidenceSha256'] = digest(evidence)
            with self.assertRaises((ApiError, ValueError)):
                complete_scene_candidate(parent, patch, evidence)

    def test_v1_to_v3_do_not_accept_v4_evidence_and_missing_proof_never_inherits(self):
        parent, patch, evidence = fixture()
        for schema in ('mira.textbook.published-operator-patch.v1', 'mira.textbook.published-operator-patch.v2',
                       'mira.textbook.published-operator-visual-patch.v3'):
            with self.assertRaises(ApiError):
                revision_candidate(parent, {**patch, 'schemaVersion': schema}, complete_scene_evidence=evidence)
        with self.assertRaises(ApiError):
            revision_candidate(parent, patch)

    def test_feedback_speech_requires_unique_exact_text_after_its_stem(self):
        from content.textbook_authoring_candidate import _questions
        parent, _, evidence = fixture()
        room, _ = validate_evidence(parent, evidence)
        ledger = json.loads(evidence['ledgerJson'])
        contract = ledger['frozenContract']['contract']
        assets = {a['assetKey']: a for a in ledger['assetBindings']}
        quiz = room['scenes'][-1]
        question = quiz['content']['questions'][0]
        question['optionFeedback'] = {'A': {'text': '再看看河流的形状。'}}
        feedback = {'id': 'quiz-feedback-A', 'type': 'speech', 'text': '再看看河流的形状。'}
        quiz['actions'].append(feedback)
        _questions(room, contract, assets)
        for mutate in (
            lambda s: s['actions'].insert(0, s['actions'].pop()),
            lambda s: s['actions'][-1].update(text='再看看河流的形状。答案是B。'),
            lambda s: s['content']['questions'][0]['optionFeedback'].update(B={'text': feedback['text']}),
        ):
            changed = deepcopy(room); mutate(changed['scenes'][-1])
            with self.assertRaises(ApiError):
                _questions(changed, contract, assets)


if __name__ == '__main__':
    unittest.main()
