"""Pure synthetic publication proofs. No config, database, HTTP or paid calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_interactive_narration import bind_interactive_audio, interactive_cues
from content.textbook_operator_revision import (
    PATCH_SCHEMA, VISUAL_PATCH_SCHEMA, inheritance_provenance, revision_candidate, sha_text,
    validate_parent, verify_inherited_segment, validate_visual_candidate_content,
)
from content.textbook_preview_audio_contract import (
    POLICY, asr_request_id, audit_contract_identity, compare_transcript, new_audio_plan, tts_request_id,
)
from content.textbook_release import INPUT_SCHEMA, RELEASE_SCHEMA
from core.errors import ApiError
from services.textbook_preview_audio import core_content


def parent_fixture(*, v2=False, retry=False, audio_sha=None, image_sha=None, quiz_intro=False, saved_preview=False, quiz_audio_alias=True, authoring=None):
    manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
    node, cid, key = 'u1-l3', 'original-operator', digest('source-preview')
    _, lesson = lesson_by_id(manifest, node)
    image = f'/api/classroom-media/{cid}/media/picture.png'
    room = {'id': cid, 'createdAt': 1, 'stage': {'id': cid, 'name': '原课堂'}, 'scenes': [
        {'id': 'slide', 'order': 1, 'type': 'slide', 'content': {'canvas': {'elements': [
            {'id': 'picture', 'type': 'image', 'src': image},
            {'id': 'title', 'type': 'text', 'content': '<p>原来源</p>'}]}},
         'actions': [{'id': 'line-slide', 'type': 'speech', 'text': '目，就是眼睛，字母里有两个眼睛呢。'}]},
        {'id': 'interactive', 'order': 2, 'type': 'interactive', 'content': {'html':
            '<html><head><meta name="mira-responsive-activity" content="low-reading-v1"></head><body><img src="' + image + '"><script id="mira-narration-cues" type="application/json">' + canonical({
                'schemaVersion': 'mira.interactive.narration-cues.v1',
                'cues': [{'id': 'na', 'text': '这是捺，先重后轻，尾巴要出来。'}]}) + '</script></body></html>'},
         'actions': [{'id': 'line-na', 'type': 'speech', 'text': '这是捺，先重后轻，尾巴要出来。'}]},
        {'id': 'quiz', 'order': 3, 'type': 'quiz', 'content': {'questions': [{
            'id': 'q4', 'type': 'single', 'question': '川，请找到河流。', 'answer': ['B'], 'analysis': '川就是河流。',
            'options': [{'value': 'A', 'label': '流水图'}, {'value': 'B', 'label': '河流图'}],
            'optionVisuals': {'A': {'kind': 'image', 'src': image, 'alt': '田地'},
                              'B': {'kind': 'image', 'src': image, 'alt': '河流'}}}]},
         'actions': [{'id': 'line-quiz', 'type': 'speech', 'text': '川，请找到河流。'}]},
    ]}
    if quiz_intro:
        room['scenes'][-1]['actions'].insert(0, {'id': 'quiz-intro', 'type': 'speech', 'text': '听题，再选一个字。'})
    if saved_preview:
        question = room['scenes'][-1]['content']['questions'][0]
        question['options'].append({'value': 'C', 'label': '山地图'})
        action = room['scenes'][-1]['actions'][-1]
        action.update(id='review_question-1', text='第1题。' + question['question'] + '。三个字分别是：' +
                      '，'.join(o['label'] for o in question['options']) + '。请选一选。')
    source_input = {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
        'manifestSha256': digest(manifest), 'nodeId': node, 'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'],
        'executionPolicy': 'operator-authored-saved-classroom.v1',
        'authoring': authoring or {'mode': 'openmaic_pro_workbench', 'request': 'synthetic test lesson'},
        'teachingRevision': '3', 'previewPrompt': {'expectedSceneCount': 3, 'expectedQuestionCount': 1, 'targets': ['川']},
        'originalMedia': {'assets': [{'mediaPath': image, 'sha256': image_sha or digest('picture')}]},
        'sourceSha256': digest(room)}
    if saved_preview:
        source_manifest = deepcopy(manifest)
        source_manifest['revisionId'] = 'legacy-preview-test'
        source_input.update(schemaVersion='mira.learning.textbook-private-preview.v1',
            executionPolicy='persist-content-before-segment-audio.v2',
            alignmentRevisionId=source_manifest['revisionId'], manifestSha256=digest(source_manifest),
            knowledgeBrief=deepcopy(lesson['brief']))
        source_input.pop('authoring'); source_input.pop('sourceSha256')
    key = digest(source_input)
    source_input['previewKey'] = key
    plan = new_audio_plan(preview_key=key, classroom_sha256=digest(room), core_sha256=digest(core_content(room)), frozen_input=source_input)
    if not v2:
        plan = {k: plan[k] for k in ('previewKey', 'classroomSha256', 'coreSha256', 'teacher')}
    receipts, entries = [], []
    for scene, action in [(s, a) for s in room['scenes'] for a in s['actions']]:
        attempt = 2 if retry and scene['id'] == 'interactive' else 1
        if attempt == 2:
            receipts.append({'requestId': tts_request_id(plan, scene['id'], action['id'], action['text']), 'status': 'failed'})
        request = tts_request_id(plan, scene['id'], action['id'], action['text'], attempt=attempt)
        segment_sha = audio_sha or digest({'audio': action['id']})
        receipt = {'requestId': request, 'status': 'succeeded', 'audioSha256': segment_sha, 'mimeType': 'audio/wav'}
        if v2:
            receipt['previewAudioIdentity'] = {'planSha256': digest(plan), 'attempt': attempt}
        receipts.append(receipt)
        action.update(audioId=request, audioUrl=f'/api/classroom-media/{cid}/audio/{request}.wav',
            audioMetadata={'schemaVersion': 'mira.openmaic.speech-audio.v1', 'providerId': 'qwen-tts',
                           'modelId': 'qwen3-tts-flash', 'voiceId': 'Serena', 'fallbackUsed': False})
        if scene['type'] == 'interactive':
            scene['content']['html'] = bind_interactive_audio(scene['content']['html'], {'na': action['audioUrl']}, cid)
        if scene['type'] == 'quiz' and action['id'] == 'line-quiz':
            scene['content']['questions'][0]['questionAudioUrl'] = action['audioUrl']
        if saved_preview and scene['type'] == 'quiz' and action['id'] == 'review_question-1':
            scene['content']['questions'][0]['questionAudioUrl'] = (f'/api/classroom-media/{cid}/audio/question-1.wav'
                if quiz_audio_alias else action['audioUrl'])
        entry = {'sceneId': scene['id'], 'actionId': action['id'], 'text': action['text'],
            'textSha256': sha_text(action['text']), 'ttsRequestId': request, 'audioSha256': segment_sha,
            'similarityBps': 10000, 'transcript': action['text'], 'durationMs': 1000,
            'asr': {'status': 'succeeded', 'requestId': asr_request_id(plan, request, segment_sha),
                    'transcript': action['text'], 'transcriptSha256': sha_text(action['text'])}}
        if v2:
            entry['comparison'] = compare_transcript(plan, action['text'], action['text'])
        entries.append(entry)
    audit = {'schemaVersion': 'mira.textbook.audio-audit.v2' if v2 else 'mira.textbook.audio-audit.v1',
             'previewKey': key, 'sourceSha256': digest(room), 'segments': entries, 'passed': True}
    if v2:
        audit['contract'] = audit_contract_identity(plan)
    audit['sha256'] = digest(audit)
    frozen = {'schemaVersion': INPUT_SCHEMA, 'previewKey': key, 'sourceSha256': digest(room),
        'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'], 'knowledgeBrief': lesson['brief'],
        'textbookBinding': {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
            'alignmentManifestSha256': digest(manifest), 'nodeId': node, 'partIndex': 1, 'teachingRevision': '3'}}
    content_key = digest(frozen)
    frozen['contentKey'] = content_key
    published = deepcopy(room)
    published['id'] = published['stage']['id'] = 'tbpub_' + content_key[:24]
    media = []
    for scene in published['scenes']:
        for action in scene['actions']:
            entry = next(e for e in entries if e['actionId'] == action['id'])
            action['audioUrl'] = f"/api/classroom-media/{published['id']}/audio/{entry['audioSha256']}.wav"
            media.append({'path': action['audioUrl'], 'sha256': entry['audioSha256'], 'mimeType': 'audio/wav'})
            if saved_preview and quiz_audio_alias and action['id'] == 'review_question-1':
                scene['content']['questions'][0]['questionAudioUrl'] = action['audioUrl']
    release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': content_key, 'classroomId': published['id'],
        'classroom': published, 'classroomSha256': digest(published), 'media': media,
        'audioAudit': {'passed': True, 'segments': len(entries), 'sha256': audit['sha256'], 'minSimilarityBps': 10000}}
    release['sha256'] = digest(release)
    review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
              'publicationAuthorized': True, 'reviewer': 'fixture', 'basis': 'explicit synthetic review', 'release': release}
    return {'manifest': manifest, 'build': {'status': 'published', 'content_key': content_key, 'node_id': node,
            'teaching_revision': '3', 'input_json': canonical(frozen), 'review_json': canonical(review)},
        'preview': {'preview_key': key, 'edition_id': manifest['editionId'], 'revision_id': source_input['alignmentRevisionId'],
            'node_id': node, 'status': 'preview_ready', 'classroom_id': cid, 'classroom_json': canonical(room),
            'classroom_sha256': digest(room), 'input_json': canonical(source_input),
            'result_json': canonical({'audioReceipts': receipts, 'audioStopCode': None})},
        'plan': plan, 'receipts': receipts, 'audit': audit,
        **({'sourceManifest': source_manifest} if saved_preview else {})}


def patch_for(parent, changes):
    return {'schemaVersion': PATCH_SCHEMA, 'parentContentKey': parent['build']['content_key'],
            'expectedSourceSha256': parent['preview']['classroom_sha256'], 'teachingRevision': '4',
            'reviewer': 'operator', 'basis': 'correct a reviewed teaching error', 'changes': changes}


def visual_patch_for(parent):
    old = json.loads(parent['preview']['classroom_json'])['scenes'][1]['content']['html']
    return {'schemaVersion': 'mira.textbook.preview-visual-patch.v1',
            'expectedSourceSha256': parent['preview']['classroom_sha256'],
            'reviewer': 'operator', 'basis': 'preserve native touch size without scaling',
            'changes': [{'sceneId': 'interactive', 'beforeHtmlSha256': sha_text(old),
                         'html': old.replace('</head>', '<style>button{min-width:48px;min-height:48px}</style></head>')}]}


class OperatorRevisionContractTests(unittest.TestCase):
    def speech_change(self, scene='slide'):
        old, new, action = ('目，就是眼睛，字母里有两个眼睛呢。', '目，就是眼睛，我们用眼睛来看书。', 'line-slide')
        if scene == 'interactive':
            old, new, action = '这是捺，先重后轻，尾巴要出来。', '这是捺，轻起笔，慢慢加重，再轻轻收笔。', 'line-na'
        return {'kind': 'speech', 'sceneId': scene, 'actionId': action, 'beforeSha256': sha_text(old), 'text': new}

    def target(self, candidate):
        return new_audio_plan(preview_key=digest('target-preview'), classroom_sha256=digest(candidate['classroom']),
            core_sha256=digest(core_content(candidate['classroom'])), frozen_input=candidate['parent']['binding'])

    def test_semantic_error_with_passed_asr_creates_new_revision_and_keeps_parent_exact(self):
        parent = parent_fixture()
        before = deepcopy(parent)
        result = revision_candidate(parent, patch_for(parent, [self.speech_change()]))
        self.assertEqual(parent, before)
        self.assertTrue(parent['audit']['passed'])
        self.assertEqual(result['changedSegments'], [['slide', 'line-slide']])
        self.assertEqual(len(result['inheritedSegments']), 2)
        changed = result['classroom']['scenes'][0]['actions'][0]
        self.assertNotIn('audioId', changed)
        self.assertNotEqual(result['classroom']['id'], parent['preview']['classroom_id'])
        self.assertEqual(result, revision_candidate(parent, patch_for(parent, [self.speech_change()])))

    def test_pure_visual_reuses_all_audio_and_asr_with_only_html_and_namespace_changes(self):
        for v2 in (False, True):
            with self.subTest(v2=v2):
                parent = parent_fixture(v2=v2, retry=True)
                original = deepcopy(parent)
                visual = visual_patch_for(parent)
                candidate = revision_candidate(parent, patch_for(parent, []), visual)
                self.assertEqual(parent, original)
                self.assertEqual(candidate['changedSegments'], [])
                self.assertEqual(candidate['inheritedSegments'], validate_parent(parent)['segments'])
                target = deepcopy(candidate['classroom'])
                target_id, source_id = target['id'], parent['preview']['classroom_id']
                target['id'] = target['stage']['id'] = source_id
                target = json.loads(canonical(target).replace('/api/classroom-media/' + target_id + '/audio/',
                                                              '/api/classroom-media/' + source_id + '/audio/'))
                source = json.loads(parent['preview']['classroom_json'])
                target['scenes'][1]['content']['html'] = source['scenes'][1]['content']['html']
                self.assertEqual(target, source)
                plan = self.target(candidate)
                provenance = inheritance_provenance(candidate, plan)
                for scene in candidate['classroom']['scenes']:
                    for action in scene['actions']:
                        receipt = next(r for r in parent['receipts'] if r['requestId'] == action['audioId'])
                        proof = verify_inherited_segment(parent, candidate, plan, provenance, scene, action, receipt)
                        self.assertEqual(proof['sourceEntry'], next(e for e in parent['audit']['segments'] if e['actionId'] == action['id']))

    def test_visual_v3_accepts_legacy_saved_preview_but_never_speech_changes(self):
        parent = parent_fixture(saved_preview=True, quiz_audio_alias=False)
        patch = {**patch_for(parent, []), 'schemaVersion': VISUAL_PATCH_SCHEMA}
        candidate = revision_candidate(parent, patch, visual_patch_for(parent))
        self.assertEqual(candidate['changedSegments'], [])
        self.assertEqual(len(candidate['inheritedSegments']), 3)
        with self.assertRaises(ApiError):
            revision_candidate(parent, patch_for(parent, []), visual_patch_for(parent))
        patch['changes'] = [self.speech_change()]
        with self.assertRaises(ApiError):
            revision_candidate(parent, patch, visual_patch_for(parent))

    def test_visual_v3_rejects_later_quiz_changes_even_when_speech_is_exact(self):
        parent = parent_fixture(v2=True)
        patch = {**patch_for(parent, []), 'schemaVersion': VISUAL_PATCH_SCHEMA}
        candidate = revision_candidate(parent, patch, visual_patch_for(parent))
        validate_visual_candidate_content(candidate, candidate['classroom'])
        later = deepcopy(candidate['classroom'])
        later['scenes'][2]['content']['questions'][0]['answer'] = ['A']
        with self.assertRaises(ApiError):
            validate_visual_candidate_content(candidate, later)

    def test_visual_delivery_allows_only_exact_published_scene_owner_mapping(self):
        parent = parent_fixture(v2=True)
        patch = {**patch_for(parent, []), 'schemaVersion': VISUAL_PATCH_SCHEMA}
        candidate = revision_candidate(parent, patch, visual_patch_for(parent))
        original = deepcopy(candidate)
        room = deepcopy(candidate['classroom'])
        media = [{'path': a['mediaPath'], 'sha256': a['sha256']}
                 for a in candidate['parent']['originalMedia']['assets']]
        media.extend({'path': f"/api/classroom-media/{room['id']}/audio/{s['ttsRequestId']}.wav",
                      'sha256': s['audioSha256']} for s in candidate['inheritedSegments'])
        published_id = 'tbpub_' + 'a' * 24
        room['id'] = room['stage']['id'] = published_id
        # Legacy archived bytes retain the old exact comparison.
        validate_visual_candidate_content(candidate, room, media=media)
        for scene in room['scenes']:
            scene['stageId'] = published_id
        validate_visual_candidate_content(candidate, room, media=media)
        self.assertEqual(candidate, original)

        for mutate in (
            lambda value: value['scenes'][0].update(stageId='another-classroom'),
            lambda value: value['scenes'][0].pop('stageId'),
            lambda value: value['stage'].update(id='another-classroom'),
            lambda value: value['scenes'][0]['actions'][0].update(text='Changed narration'),
            lambda value: value['scenes'][1]['content'].update(html='<button>Changed activity</button>'),
        ):
            changed = deepcopy(room)
            mutate(changed)
            with self.subTest(mutate=mutate), self.assertRaises((ApiError, ValueError)):
                validate_visual_candidate_content(candidate, changed, media=media)
        with self.assertRaises(ApiError):
            validate_visual_candidate_content(candidate, room)

    def test_empty_changes_require_valid_nonempty_visual_patch_and_preserve_audio(self):
        parent = parent_fixture(v2=True)
        for visual in (None, {}, {**visual_patch_for(parent), 'changes': []}):
            with self.subTest(visual=visual), self.assertRaises(ApiError):
                revision_candidate(parent, patch_for(parent, []), visual)
        visual = visual_patch_for(parent)
        for mutate in (
            lambda v: v.update(expectedSourceSha256='0' * 64),
            lambda v: v['changes'][0].update(beforeHtmlSha256='0' * 64),
            lambda v: v['changes'][0].update(sceneId='slide'),
            lambda v: v['changes'][0].update(actions=[]),
            lambda v: v['changes'][0].update(html=v['changes'][0]['html'].replace('这是捺', '改过的旁白')),
            lambda v: v['changes'][0].update(html=v['changes'][0]['html'].replace('const clips=', 'const otherClips=')),
        ):
            changed = deepcopy(visual)
            mutate(changed)
            with self.subTest(change=changed), self.assertRaises((ApiError, ValueError)):
                revision_candidate(parent, patch_for(parent, []), changed)

    def test_pure_visual_still_rejects_unpublished_or_inherited_parent(self):
        for mutate in (lambda p: p['build'].update(status='building'),
                       lambda p: p['preview'].update(input_json=canonical({
                           **json.loads(p['preview']['input_json']), 'operatorRevision': {'revisionId': 'prior'}}))):
            parent = parent_fixture(v2=True)
            visual = visual_patch_for(parent)
            mutate(parent)
            with self.assertRaises(ApiError):
                revision_candidate(parent, patch_for(parent, []), visual)

    def test_exact_old_retry_chain_is_reused_without_making_new_receipt(self):
        for v2 in (False, True):
            parent = parent_fixture(v2=v2, retry=True)
            candidate = revision_candidate(parent, patch_for(parent, [self.speech_change()]))
            scene = candidate['classroom']['scenes'][1]
            action = scene['actions'][0]
            receipt = next(r for r in parent['receipts'] if r['requestId'] == action['audioId'])
            plan = self.target(candidate)
            provenance = inheritance_provenance(candidate, plan)
            proof = verify_inherited_segment(parent, candidate, plan, provenance, scene, action, receipt)
            self.assertEqual(proof['sourceEntry'], parent['audit']['segments'][1])
            self.assertTrue(proof['comparison']['passed'])
            self.assertEqual(candidate['inheritedSegments'][0]['attempt'], 2)
            self.assertEqual(receipt['requestId'], action['audioId'])

    def test_cue_changes_are_synchronized_without_editing_other_html(self):
        parent = parent_fixture()
        candidate = revision_candidate(parent, patch_for(parent, [self.speech_change('interactive')]))
        scene = candidate['classroom']['scenes'][1]
        self.assertEqual(interactive_cues(scene['content']['html'])[0]['text'], scene['actions'][0]['text'])
        self.assertNotIn('mira-pre-recorded-audio', scene['content']['html'])
        self.assertIn('<img src="/api/classroom-media/original-operator/media/picture.png">', scene['content']['html'])

    def test_label_and_slide_text_leave_answer_pictures_and_all_audio_unchanged(self):
        parent = parent_fixture()
        source = json.loads(parent['preview']['classroom_json'])
        patch = patch_for(parent, [
            {'kind': 'option_label', 'sceneId': 'quiz', 'questionId': 'q4', 'optionValue': 'A',
             'beforeSha256': sha_text('流水图'), 'text': '田地图'},
            {'kind': 'slide_text', 'sceneId': 'slide', 'elementId': 'title',
             'beforeSha256': sha_text('<p>原来源</p>'), 'text': '<p>已核实来源</p>'}])
        candidate = revision_candidate(parent, patch)
        actual = candidate['classroom']['scenes'][2]['content']['questions'][0]
        original = source['scenes'][2]['content']['questions'][0]
        self.assertEqual(actual['answer'], original['answer'])
        self.assertEqual(actual['optionVisuals'], original['optionVisuals'])
        self.assertEqual(len(candidate['inheritedSegments']), 3)
        self.assertFalse(candidate['changedSegments'])
        patch['changes'][1]['text'] = '<p><img src="other.png"></p>'
        with self.assertRaises(ApiError): revision_candidate(parent, patch)

    def test_cross_binding_voice_and_nested_source_are_rejected(self):
        parent = parent_fixture()
        for mutate in (
            lambda p: p['plan']['teacher'].update(voiceId='Ethan'),
            lambda p: p['preview'].update(node_id='another-node'),
            lambda p: p['preview'].update(classroom_sha256='0' * 64),
            lambda p: p['plan'].update(revisionId='a' * 64),
        ):
            bad = deepcopy(parent)
            mutate(bad)
            with self.assertRaises(ApiError): validate_parent(bad)
        candidate = revision_candidate(parent, patch_for(parent, [self.speech_change()]))
        plan = self.target(candidate)
        plan['binding']['editionId'] = 'other-edition'
        with self.assertRaises(ApiError): inheritance_provenance(candidate, plan)

    def test_missing_retry_predecessor_cannot_be_assumed_success(self):
        parent = parent_fixture(retry=True)
        parent['receipts'] = [r for r in parent['receipts'] if r['status'] != 'failed']
        result = json.loads(parent['preview']['result_json'])
        result['audioReceipts'] = parent['receipts']
        parent['preview']['result_json'] = canonical(result)
        with self.assertRaises(ApiError): validate_parent(parent)

    def test_source_audit_receipt_and_original_input_tampering_are_rejected(self):
        parent = parent_fixture(v2=True)
        for mutate in (
            lambda p: p['audit'].update(passed=False),
            lambda p: p['audit']['segments'][0]['asr'].update(transcript='wrong'),
            lambda p: p['receipts'][0].update(audioSha256='0' * 64),
            lambda p: p['audit']['contract'].update(teacher={}),
            lambda p: p['preview'].update(input_json=canonical({
                **json.loads(p['preview']['input_json']), 'sourceSha256': 'f' * 64})),
        ):
            bad = deepcopy(parent)
            mutate(bad)
            with self.assertRaises(ApiError): validate_parent(bad)

    def test_stale_patch_duplicate_target_and_answer_edits_are_rejected(self):
        parent = parent_fixture()
        good = patch_for(parent, [self.speech_change()])
        for mutate in (
            lambda p: p.update(teachingRevision='3'),
            lambda p: p.update(expectedSourceSha256='a' * 64),
            lambda p: p['changes'][0].update(beforeSha256='a' * 64),
            lambda p: p['changes'][0].update(answer=['A']),
            lambda p: p['changes'][0].update(kind='html'),
            lambda p: p['changes'].append(deepcopy(p['changes'][0])),
        ):
            bad = deepcopy(good)
            mutate(bad)
            with self.assertRaises(ApiError): revision_candidate(parent, bad)

    def test_changed_text_audio_metadata_receipt_or_provenance_cannot_inherit(self):
        parent = parent_fixture(v2=True)
        candidate = revision_candidate(parent, patch_for(parent, [self.speech_change()]))
        plan = self.target(candidate)
        provenance = inheritance_provenance(candidate, plan)
        scene = candidate['classroom']['scenes'][1]
        action = scene['actions'][0]
        receipt = next(r for r in parent['receipts'] if r['requestId'] == action['audioId'])
        for key, value in [('text', '不同的旁白。'), ('audioUrl', '/different.wav'), ('audioMetadata', {})]:
            changed = {**action, key: value}
            with self.assertRaises(ApiError): verify_inherited_segment(parent, candidate, plan, provenance, scene, changed, receipt)
        with self.assertRaises(ApiError):
            verify_inherited_segment(parent, candidate, plan, provenance, scene, action, {**receipt, 'audioSha256': '0' * 64})
        bad = deepcopy(provenance)
        bad['parent']['releaseSha256'] = '0' * 64
        with self.assertRaises(ApiError): verify_inherited_segment(parent, candidate, plan, bad, scene, action, receipt)
        changed_scene = candidate['classroom']['scenes'][0]
        with self.assertRaises(ApiError):
            verify_inherited_segment(parent, candidate, plan, provenance, changed_scene, changed_scene['actions'][0], receipt)


if __name__ == '__main__':
    unittest.main()
