from copy import deepcopy
import json
import unittest

from content.textbook_catalog import digest
from content.textbook_complete_scene_revision import complete_scene_candidate
from content.textbook_operator_revision import inheritance_provenance
from content.textbook_parent_audio_restoration import (
    PATCH_SCHEMA, restoration_candidate, restoration_receipt, restored_entry, validate_published_restorations,
    validate_restoration_evidence)
from content.textbook_preview_audio_contract import new_audio_plan
from core.errors import ApiError
from services.textbook_operator_revision_service import target_input
from services.textbook_preview_audio import core_content
from tests.test_textbook_complete_scene_revision import fixture


def restoration_fixture():
    parent, patch, evidence = fixture()
    candidate = complete_scene_candidate(parent, patch, evidence)
    # This boundary is supplied by the fully verified archive adapter. Model a
    # slot omitted from initial inheritance whose wording was later restored.
    candidate['inheritedSegments'] = [s for s in candidate['inheritedSegments'] if s['sceneId'] != 'quiz']
    frozen = target_input(parent, candidate)
    plan = new_audio_plan(preview_key=frozen['previewKey'], classroom_sha256=digest(candidate['classroom']),
        core_sha256=digest(core_content(candidate['classroom'])), frozen_input=frozen)
    context = {'parent': parent, 'candidate': candidate, 'provenance': inheritance_provenance(candidate, plan)}
    source = deepcopy(candidate['classroom'])
    scene = next(s for s in source['scenes'] if s['id'] == 'quiz')
    action = scene['actions'][0]
    action['audioId'] = 'tbbtts2_' + '1' * 64
    action['audioUrl'] = '/api/classroom-media/' + source['id'] + '/audio/' + action['audioId'] + '.wav'
    q = scene['content']['questions'][0]
    q['questionAudioUrl'] = action['audioUrl']
    patch = {'schemaVersion': PATCH_SCHEMA, 'expectedSourceSha256': digest(source), 'reviewer': 'test',
        'basis': 'Restore exact same source text and approved audio.', 'changes': [{'sceneId': 'quiz',
            'actionId': action['id'], 'questionId': q['id'], 'beforeQuestionSha256': digest(q),
            'beforeAudioId': action['audioId']}]}
    return context, source, patch, plan


class ParentAudioRestorationTests(unittest.TestCase):
    def test_portable_ancestor_restoration_rebuilds_original_documents_and_rejects_substitution(self):
        context, source, patch, plan = restoration_fixture()
        target, segments = restoration_candidate(context, source, patch, plan)
        amendment = restoration_receipt(context, source, target, patch, plan, segments)
        item = {'revisionId': amendment['revisionId'], 'documents': {
            'source.json': source, 'patch.json': patch, 'saved.json': target, 'amendment.json': amendment}}
        restored = validate_restoration_evidence(context, plan, [item])
        self.assertEqual(restored['restorations'], [amendment])
        self.assertEqual(list(restored['restoredSegments']), [('quiz', segments[0]['actionId'])])
        for mutation in ('source', 'saved', 'receipt', 'id', 'missing'):
            bad = deepcopy(item)
            if mutation == 'source': bad['documents']['source.json']['scenes'][0]['title'] += 'changed'
            elif mutation == 'saved': bad['documents']['saved.json']['scenes'][-1]['actions'][0]['audioId'] = 'wrong'
            elif mutation == 'receipt': bad['documents']['amendment.json']['providerCalls'] = 1
            elif mutation == 'id': bad['revisionId'] = '0' * 64
            else: bad['documents'].pop('source.json')
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                validate_restoration_evidence(context, plan, [bad])

    def test_restores_original_receipt_and_asr_without_relabeling_or_changing_words(self):
        context, source, patch, plan = restoration_fixture()
        before = deepcopy(source)
        target, segments = restoration_candidate(context, source, patch, plan)
        self.assertEqual(source, before)
        amendment = restoration_receipt(context, source, target, patch, plan, segments)
        context['restoredSegments'] = {('quiz', segments[0]['actionId']): (segments[0], amendment)}
        scene = next(s for s in target['scenes'] if s['id'] == 'quiz'); action = scene['actions'][0]
        original_receipt = next(r for r in context['parent']['receipts'] if r['requestId'] == action['audioId'])
        entry = restored_entry(context, plan, scene, action, original_receipt)
        old_entry = next(e for e in context['parent']['audit']['segments'] if e['sceneId'] == 'quiz' and e['actionId'] == action['id'])
        self.assertEqual(entry['asr'], old_entry['asr'])
        self.assertEqual(entry['ttsRequestId'], old_entry['ttsRequestId'])
        self.assertTrue(entry['comparison']['passed'])
        self.assertEqual(entry['operatorParent']['restorationSha256'], amendment['sha256'])
        self.assertEqual(amendment['providerCalls'], 0)
        self.assertEqual(scene['content']['questions'][0]['questionAudioBinding']['sourceTextSha256'], segments[0]['textSha256'])
        self.assertEqual(action['text'], next(s for s in source['scenes'] if s['id'] == 'quiz')['actions'][0]['text'])

    def test_rejects_wrong_text_teacher_unapproved_clip_and_duplicate_mapping(self):
        for mutation in ('text', 'teacher', 'unapproved', 'duplicate', 'question'):
            context, source, patch, plan = restoration_fixture()
            if mutation == 'text': source['scenes'][-1]['actions'][0]['text'] += '不同'
            elif mutation == 'teacher': plan['teacher']['voiceId'] = 'Other'
            elif mutation == 'unapproved': context['candidate']['parent']['segments'] = []
            elif mutation == 'duplicate': patch['changes'].append(deepcopy(patch['changes'][0]))
            else: source['scenes'][-1]['content']['questions'][0]['question'] += '不同'
            patch['expectedSourceSha256'] = digest(source)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                restoration_candidate(context, source, patch, plan)

    def test_published_delivery_checks_restored_wav_identity(self):
        context, source, patch, plan = restoration_fixture()
        target, segments = restoration_candidate(context, source, patch, plan)
        amendment = restoration_receipt(context, source, target, patch, plan, segments)
        action = next(s for s in target['scenes'] if s['id'] == 'quiz')['actions'][0]
        frozen = {'operatorParent': context['provenance'], 'audioContract': plan,
                  'operatorParentAudioRestorations': [amendment]}
        release = {'classroom': target, 'media': [{'path': action['audioUrl'], 'sha256': segments[0]['audioSha256']}],
                   'audioAudit': {'operatorParentAudioRestorationsSha256': digest([amendment])}}
        validate_published_restorations(frozen, release)
        release['media'][0]['sha256'] = '0' * 64
        with self.assertRaises(ApiError): validate_published_restorations(frozen, release)


if __name__ == '__main__':
    unittest.main()
