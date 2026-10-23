"""Visual amendments use only an in-memory DB, temporary assets and mock runtime."""
from copy import deepcopy
import base64
import fcntl
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import POLICY
from content.textbook_interactive_narration import bind_interactive_audio
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.textbook_preview_audio import narrate_preview
from services.textbook_preview_visual_revision import (CANVAS_SCHEMA, QUIZ_VISUAL_SCHEMA, QUANTITY_VISUAL_SCHEMA, IMAGE_ALT_SCHEMA,
    QUESTION_BINDING_SCHEMA, SCHEMA, revise_preview_visuals, sha_bytes, verify_quantity_visual_revisions)
from services.textbook_publication_service import TextbookPublicationService
from tests import test_textbook_preview as preview_fixtures


class VisualRevisionTests(unittest.TestCase):
    def setUp(self):
        fixture = preview_fixtures.TextbookPreviewTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.service, self.runtime, self.db = fixture.service, fixture.runtime, fixture.db
        self.key = fixture.prepare()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cid = 'class-visual'
        self.folder = self.root / self.cid / 'textbook-preview-audio'
        self.folder.mkdir(parents=True)
        (self.root / self.cid / 'audio').mkdir()
        (self.root / self.cid / 'media').mkdir()
        (self.root / self.cid / 'media/picture.png').write_bytes(b'existing-original-picture')
        (self.root / self.cid / 'media/cover.png').write_bytes(b'existing-original-cover')
        picture = f'/api/classroom-media/{self.cid}/media/picture.png'
        self.cover = f'/api/classroom-media/{self.cid}/media/cover.png'
        frozen = json.loads(self.service.get(self.key)['input_json'])
        frozen['originalMedia']['assets'] = [{'mediaPath': picture, 'sha256': sha_bytes(b'existing-original-picture')},
                                            {'mediaPath': self.cover, 'sha256': sha_bytes(b'existing-original-cover')}]
        self.db.execute('UPDATE learning_textbook_course_previews SET input_json=? WHERE preview_key=?', (canonical(frozen), self.key))
        self.classroom = {'id': self.cid, 'stage': {'id': self.cid, 'name': '数一数'}, 'createdAt': 'original', 'scenes': []}
        receipts = []
        for i, kind in enumerate(['slide'] * 5 + ['interactive', 'quiz', 'slide']):
            request = 'tbprev_' + digest({'index': i})
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(24000)
                wav.writeframes(b'\x10\x27\xf0\xd8' * 12000)
            audio = buffer.getvalue()
            (self.root / self.cid / 'audio' / (request + '.wav')).write_bytes(audio)
            action = {'id': f'action-{i}', 'type': 'speech', 'text': '数一数。', 'audioId': request,
                      'audioUrl': f'http://127.0.0.1:3100/api/classroom-media/{self.cid}/audio/{request}.wav'}
            content = preview_fixtures.scene_content(kind)
            if kind == 'slide':
                for element_index, element in enumerate(content['canvas']['elements']):
                    element.setdefault('id', f'element-{i}-{element_index}')
                content['canvas']['elements'][0]['src'] = self.cover if i == 0 else picture
            if kind == 'interactive':
                content['html'] = f'<img src="{picture}">'
                content['html'] += '<svg><path d="M10 20H30"/></svg><script id="mira-narration-cues" type="application/json">' + canonical({
                    'schemaVersion': 'mira.interactive.narration-cues.v1', 'cues': [{'id': 'ask', 'text': action['text']}]}) + '</script>'
                content['html'] = bind_interactive_audio(preview_fixtures.responsive_html(content['html']), {'ask': action['audioUrl'].removeprefix('http://127.0.0.1:3100')}, self.cid)
            if kind == 'quiz':
                content['questions'] = [{'id': f'q-{q}', 'type': 'single', 'question': '数一数。',
                    'options': [{'value': 'A', 'label': '一个'}, {'value': 'B', 'label': '两个'}], 'answer': ['A'],
                    'analysis': '这是一个。', 'points': 1, 'questionAudioUrl': action['audioUrl']} for q in range(6)]
            self.classroom['scenes'].append({'id': f'scene-{i}', 'order': i + 1, 'type': kind, 'content': content, 'actions': [action]})
            receipts.append({'requestId': request, 'status': 'succeeded', 'audioSha256': sha_bytes(audio)})
        self.result = {'audioReceipts': receipts, 'audioStopCode': None, 'audioSeconds': 12,
                       'frozenPreview': {'sourceSha256': digest(self.classroom)}}
        self.source_sha = digest(self.classroom)
        self.db.execute("UPDATE learning_textbook_course_previews SET status='preview_ready',runtime_job_id='job-visual',classroom_id=?,classroom_json=?,classroom_sha256=?,result_json=? WHERE preview_key=?",
                        (self.cid, canonical(self.classroom), self.source_sha, canonical(self.result), self.key))
        self.db.raw.commit()
        (self.root / (self.cid + '.json')).write_text(canonical(self.classroom))
        self.plan = {'previewKey': self.key, 'classroomSha256': 'a' * 64, 'coreSha256': 'b' * 64,
                     'teacher': deepcopy(POLICY['subjects']['chinese']['teacher'])}
        (self.folder / 'plan.json').write_text(canonical(self.plan))
        (self.folder / 'receipts.json').write_text(canonical(receipts))
        self.runtime.get_classroom.side_effect = lambda _: deepcopy(self.classroom)
        self.runtime.save_preview_classroom.side_effect = self.save
        old_html = self.classroom['scenes'][5]['content']['html']
        self.patch = {'schemaVersion': SCHEMA, 'expectedSourceSha256': self.source_sha, 'reviewer': 'operator',
                      'basis': '补齐笔画，不改变语音与任务', 'changes': [{'sceneId': 'scene-5',
                      'beforeHtmlSha256': sha_bytes(old_html.encode()), 'html': old_html.replace('M10 20H30', 'M10 20H30 M20 10V30')}]}

    def save(self, classroom):
        self.classroom = {**deepcopy(classroom), 'createdAt': 'saved'}
        (self.root / (self.cid + '.json')).write_text(canonical(self.classroom))

    def apply(self, patch_value=None):
        return revise_preview_visuals(self.service, self.key, self.root, patch_value or self.patch)

    def archive(self):
        return self.folder / 'visual-revisions' / digest({'previewKey': self.key, 'patch': self.patch})

    def canvas_patch(self):
        old = self.classroom['scenes'][0]['content']['canvas']
        canvas = deepcopy(old)
        canvas['elements'][0]['src'] = f'/api/classroom-media/{self.cid}/media/picture.png'
        canvas['elements'][0]['left'] = 40
        return {'schemaVersion': CANVAS_SCHEMA, 'expectedSourceSha256': digest(self.classroom),
                'reviewer': 'operator', 'basis': '修正图片与版面，保持讲解',
                'changes': [{'sceneId': 'scene-0', 'beforeCanvasSha256': digest(old), 'canvas': canvas}]}

    def append_source_html(self, html):
        self.classroom['scenes'][5]['content']['html'] += html
        self.persist_source()

    def persist_source(self):
        self.source_sha = digest(self.classroom)
        self.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                        (canonical(self.classroom), self.source_sha, self.key))
        self.db.raw.commit()
        (self.root / (self.cid + '.json')).write_text(canonical(self.classroom))

    def append_source_canvas_svg(self, svg):
        self.classroom['scenes'][0]['content']['canvas']['elements'].append({
            'id': 'adopted-svg', 'type': 'image', 'left': 60, 'top': 60,
            'src': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()})
        self.persist_source()

    def svg_patch(self, svg):
        value = self.canvas_patch()
        value['changes'][0]['canvas']['elements'].append({'id': 'reused-svg', 'type': 'image',
            'src': 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()})
        return value

    def quiz_visual_patch(self):
        question = self.classroom['scenes'][6]['content']['questions'][0]
        return {'schemaVersion': QUIZ_VISUAL_SCHEMA, 'expectedSourceSha256': digest(self.classroom),
                'reviewer': 'operator', 'basis': '补显示已有目标图，题目和音频不变',
                'changes': [{'sceneId': 'scene-6', 'questionId': question['id'],
                             'beforeQuestionSha256': digest(question),
                             'visual': {'kind': 'image', 'src': self.cover, 'alt': '待辨认的目标图'}}]}

    def image_alt_patch(self):
        question = self.classroom['scenes'][6]['content']['questions'][0]
        # Shared image bytes must not cause another option to be relabeled.
        question['optionVisuals'] = {
            'A': {'kind': 'image', 'src': self.cover, 'alt': '图片，待 operator 修订'},
            'B': {'kind': 'image', 'src': self.cover, 'alt': '另一张选项图片'}}
        self.persist_source()
        old = question['optionVisuals']['A']
        return {'schemaVersion': IMAGE_ALT_SCHEMA, 'expectedSourceSha256': self.source_sha,
                'reviewer': 'operator', 'basis': '清除无障碍说明里的内部备注，保留原图与题目',
                'changes': [{'sceneId': 'scene-6', 'questionId': question['id'], 'optionValue': 'A',
                    'beforeQuestionSha256': digest(question), 'beforeVisualSha256': digest(old),
                    'beforeAlt': old['alt'], 'src': old['src'],
                    'imageSha256': sha_bytes(b'existing-original-cover'), 'alt': '供孩子观察的图片'}]}

    def question_binding_patch(self):
        scene = self.classroom['scenes'][6]
        for question in scene['content']['questions'][1:]:
            question['question'] = '另一道题' + question['id']
        question = scene['content']['questions'][0]
        question['questionAudioBinding'] = {'stale': 'previous narration'}
        self.persist_source()
        return {'schemaVersion': QUESTION_BINDING_SCHEMA, 'expectedSourceSha256': self.source_sha,
                'reviewer': 'operator', 'basis': '同步已完成题干录音的准确绑定，保留全部题目与原始录音',
                'changes': [{'sceneId': scene['id'], 'questionId': question['id'],
                             'actionId': scene['actions'][0]['id'], 'beforeQuestionSha256': digest(question)}]}

    def test_question_binding_repairs_metadata_only_without_provider_calls(self):
        value = self.question_binding_patch()
        original = deepcopy(self.classroom)
        receipt = self.apply(value)
        expected = deepcopy(original)
        scene = expected['scenes'][6]
        action = scene['actions'][0]
        scene['content']['questions'][0]['questionAudioBinding'] = {
            'schemaVersion': 'mira.learning.question-narration-binding.v1',
            'sceneId': scene['id'], 'actionId': action['id'], 'ttsRequestId': action['audioId'],
            'sourceTextSha256': sha_bytes(action['text'].encode())}
        expected['createdAt'] = 'saved'
        self.assertEqual(self.classroom, expected)
        self.assertFalse(receipt['ttsDispatched'])
        self.assertEqual(receipt['patchSchemaVersion'], QUESTION_BINDING_SCHEMA)
        self.assertEqual(json.loads((self.folder / 'receipts.json').read_text()), self.result['audioReceipts'])

    def test_question_binding_rejects_wrong_clip_duplicate_speech_and_extra_fields(self):
        for variant in ('wrong_clip', 'duplicate_speech', 'extra_fields'):
            with self.subTest(variant=variant):
                value = self.question_binding_patch()
                scene = self.classroom['scenes'][6]
                if variant == 'wrong_clip':
                    scene['content']['questions'][0]['questionAudioUrl'] = '/unrelated.wav'
                    value['changes'][0]['beforeQuestionSha256'] = digest(scene['content']['questions'][0])
                elif variant == 'duplicate_speech':
                    scene['actions'].append({**scene['actions'][0], 'id': 'duplicate'})
                else:
                    value['changes'][0]['questionAudioBinding'] = {'ttsRequestId': 'invented'}
                self.persist_source()
                value['expectedSourceSha256'] = self.source_sha
                with self.assertRaises(ApiError):
                    self.apply(value)
                self.runtime.save_preview_classroom.assert_not_called()
                scene['actions'] = scene['actions'][:1]
                scene['content']['questions'][0]['questionAudioUrl'] = scene['actions'][0]['audioUrl']

    def test_image_alt_changes_only_exact_option_and_preserves_frozen_audio_and_archive(self):
        value = self.image_alt_patch()
        original = deepcopy(self.classroom)
        frozen_before = self.service.get(self.key)['input_json']
        receipt = self.apply(value)
        expected = deepcopy(original)
        expected['scenes'][6]['content']['questions'][0]['optionVisuals']['A']['alt'] = '供孩子观察的图片'
        expected['createdAt'] = 'saved'
        self.assertEqual(self.classroom, expected)
        self.assertEqual(self.service.get(self.key)['input_json'], frozen_before)
        archive = self.folder / 'visual-revisions' / digest({'previewKey': self.key, 'patch': value})
        self.assertEqual(json.loads((archive / 'source.json').read_text()), original)
        self.assertEqual(json.loads((archive / 'saved.json').read_text()), expected)
        for name in ('plan.json', 'receipts.json'):
            self.assertEqual((archive / name).read_bytes(), (self.folder / name).read_bytes())
        self.assertEqual(receipt['patchSchemaVersion'], IMAGE_ALT_SCHEMA)
        narrate_preview(self.service, self.key, self.root)
        self.assertEqual(self.apply(value), receipt)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_generation.assert_not_called()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()

    def test_image_alt_rejects_identity_drift_cross_option_and_non_alt_mutations(self):
        good = self.image_alt_patch()
        mutations = [
            {'beforeQuestionSha256': 'f' * 64}, {'beforeVisualSha256': 'f' * 64},
            {'imageSha256': 'f' * 64}, {'beforeAlt': '过时说明'}, {'sceneId': 'scene-0'},
            {'questionId': 'missing'}, {'optionValue': 'missing'}, {'optionValue': 'B'},
            {'src': self.cover.replace('cover.png', 'picture.png')},
            {'src': '/api/classroom-media/other/media/cover.png'},
            {'alt': ''}, {'alt': '<img src=x>'}, {'alt': '含\n换行'},
            {'alt': good['changes'][0]['beforeAlt']}, {'alt': ' 前置空格'},
            {'answer': ['B']}, {'question': '新题'}, {'points': 20},
            {'actions': []}, {'kind': 'image'}, {'visual': {'src': self.cover}},
        ]
        for mutation in mutations:
            value = deepcopy(good)
            value['changes'][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                self.apply(value)
        value = deepcopy(good)
        value['changes'].append(deepcopy(value['changes'][0]))
        with self.assertRaises(ApiError):
            self.apply(value)
        with self.assertRaises(ApiError):
            self.apply({**good, 'expectedSourceSha256': 'f' * 64})
        (self.root / self.cid / 'media/cover.png').write_bytes(b'changed frozen picture')
        with self.assertRaises(ApiError):
            self.apply(good)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_image_alt_reuses_existing_asr_cache_and_requires_new_aggregate_source(self):
        from scripts import audit_textbook_audio as audit_script
        value = self.image_alt_patch()
        output = self.root / 'asr-alt-audit'
        self.runtime.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('not_found', 'not found', status_code=404)
        self.runtime.start_formal_audio_asr.side_effect = lambda **kw: {
            'status': 'succeeded', 'requestId': kw['request_id'], 'transcript': '数一数。'}
        argv = ['audit_textbook_audio.py', '--key', self.key, '--classroom-directory', str(self.root), '--output', str(output)]
        with patch.object(audit_script.AppConfig, 'from_env'), patch.object(audit_script, 'Database', return_value=self.db), \
                patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=self.runtime), patch('sys.argv', argv):
            audit_script.main()
            old_audit = json.loads((output / 'audit.json').read_text())
            self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 8)
            receipt = self.apply(value)
            audit_script.main()
            audit = json.loads((output / 'audit.json').read_text())
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 8)
        self.assertTrue(audit['passed'])
        self.assertEqual(audit['segments'], old_audit['segments'])
        self.assertEqual(audit['sourceSha256'], receipt['targetSha256'])
        self.assertNotEqual(audit['sourceSha256'], old_audit['sourceSha256'])
        self.assertEqual({c.kwargs['classroom_content_sha256'] for c in self.runtime.start_formal_audio_asr.call_args_list}, {'a' * 64})
        self.runtime.start_formal_audio_tts.assert_not_called()

    def quantity_patch(self):
        from PIL import Image, ImageDraw
        from content.textbook_preview_quantity_images import TRANSFORM, quantity_png
        image = Image.new('RGB', (120, 160), '#fffdf7')
        ImageDraw.Draw(image).rectangle((10, 10, 110, 150), fill='#db753f')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        raw = buffer.getvalue()
        source_path = f'/api/classroom-media/{self.cid}/media/object.png'
        (self.root / self.cid / 'media/object.png').write_bytes(raw)
        frozen = json.loads(self.service.get(self.key)['input_json'])
        frozen['originalMedia']['assets'].append({'mediaPath': source_path, 'sha256': sha_bytes(raw)})
        self.classroom['scenes'][5]['content']['html'] += f'<img src="{source_path}">'
        definitions, paths = [], {}
        for count in (2, 3):
            positions = [[5, 5], [55, 5]] if count == 2 else [[5, 5], [40, 5], [75, 5]]
            old = {'cropBox': [0, 0, 120, 160], 'thumbnailSize': [20, 30], 'canvasSize': [100, 80],
                   'positions': positions, 'centerWithinThumbnail': False}
            new = {**old, 'cropBox': [10, 10, 110, 150], 'thumbnailSize': [25, 35], 'canvasSize': [100, 100],
                   'positions': [[x, 45] for x, _ in positions], 'centerWithinThumbnail': True}
            old_raw = quantity_png(raw, source_size=[120, 160], count=count, layout=old)
            new_raw = quantity_png(raw, source_size=[120, 160], count=count, layout=new)
            path = f'/api/classroom-media/{self.cid}/media/group-{count}.png'
            (self.root / self.cid / 'media' / f'group-{count}.png').write_bytes(old_raw)
            frozen['originalMedia']['assets'].append({'mediaPath': path, 'sha256': sha_bytes(old_raw)})
            paths[count] = {'kind': 'image', 'src': path, 'alt': '数量图片'}
            definitions.append({'id': f'group-{count}', 'transform': TRANSFORM,
                'sourcePath': source_path, 'sourceSha256': sha_bytes(raw), 'sourceSize': [120, 160],
                'count': count, 'replacesPath': path, 'replacesSha256': sha_bytes(old_raw),
                'originalLayout': old, 'layout': new, 'sha256': sha_bytes(new_raw)})
        question = self.classroom['scenes'][6]['content']['questions'][0]
        question.update(visual=paths[2], optionVisuals={'A': paths[2], 'B': paths[3]})
        self.db.execute('UPDATE learning_textbook_course_previews SET input_json=? WHERE preview_key=?', (canonical(frozen), self.key))
        self.persist_source()
        return {'schemaVersion': QUANTITY_VISUAL_SCHEMA, 'expectedSourceSha256': digest(self.classroom),
                'reviewer': 'operator', 'basis': '保留数量，紧裁同源对象改善触屏可辨认性', 'derivedImages': definitions,
                'changes': [{'sceneId': 'scene-6', 'questionId': question['id'], 'beforeQuestionSha256': digest(question),
                             'visualImageId': 'group-2', 'optionImageIds': {'A': 'group-2', 'B': 'group-3'}}]}

    def test_quantity_revision_preserves_frozen_question_and_audio_bytes(self):
        value = self.quantity_patch()
        original = deepcopy(self.classroom)
        frozen = self.service.get(self.key)['input_json']
        audio = {p.name: p.read_bytes() for p in (self.root / self.cid / 'audio').iterdir()}
        plan, receipts = (self.folder / 'plan.json').read_bytes(), (self.folder / 'receipts.json').read_bytes()
        receipt = self.apply(value)
        expected = deepcopy(original)
        q = expected['scenes'][6]['content']['questions'][0]
        paths = {d['id']: f"/api/classroom-media/{self.cid}/media/{d['sha256']}.png" for d in value['derivedImages']}
        q['visual']['src'] = paths['group-2']
        q['optionVisuals']['A']['src'] = paths['group-2']
        q['optionVisuals']['B']['src'] = paths['group-3']
        expected['createdAt'] = 'saved'
        self.assertEqual(self.classroom, expected)
        self.assertEqual(self.service.get(self.key)['input_json'], frozen)
        self.assertEqual((self.folder / 'plan.json').read_bytes(), plan)
        self.assertEqual((self.folder / 'receipts.json').read_bytes(), receipts)
        self.assertEqual({p.name: p.read_bytes() for p in (self.root / self.cid / 'audio').iterdir()}, audio)
        verify_quantity_visual_revisions(self.service.get(self.key), self.root)
        self.assertEqual(self.apply(value), receipt)
        narrate_preview(self.service, self.key, self.root)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()
        self.runtime.start_generation.assert_not_called()

    def test_quantity_revision_rejects_count_source_crop_overlap_and_question_changes(self):
        good = self.quantity_patch()
        mutations = []
        for field, replacement in (('count', 3), ('sourceSha256', 'a' * 64), ('replacesSha256', 'b' * 64),
                                   ('sourcePath', '/api/classroom-media/elsewhere/media/object.png'),
                                   ('sourceSize', [121, 160]), ('transform', 'unreviewed'), ('sha256', 'c' * 64)):
            value = deepcopy(good)
            value['derivedImages'][0][field] = replacement
            mutations.append(value)
        for field, replacement in (('cropBox', [-1, 0, 120, 160]), ('positions', [[5, 5], [5, 5]]),
                                   ('canvasSize', [10, 10])):
            value = deepcopy(good)
            value['derivedImages'][0]['layout'][field] = replacement
            mutations.append(value)
        for field, replacement in (('answer', ['B']), ('question', '新题目'), ('optionImageIds', {'A': 'group-3', 'B': 'group-2'})):
            value = deepcopy(good)
            value['changes'][0][field] = replacement
            mutations.append(value)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(ApiError):
                self.apply(value)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_quantity_revision_rechecks_source_target_and_archive_before_publication(self):
        value = self.quantity_patch()
        receipt = self.apply(value)
        paths = [self.root / self.cid / 'media/object.png',
                 self.root / self.cid / 'media' / (value['derivedImages'][0]['sha256'] + '.png'),
                 self.folder / 'visual-revisions' / receipt['revisionId'] / 'derived-images.json']
        for path in paths:
            raw = path.read_bytes()
            path.write_bytes(b'changed')
            with self.subTest(path=path), self.assertRaises(ApiError):
                verify_quantity_visual_revisions(self.service.get(self.key), self.root)
            with self.assertRaises(ApiError):
                TextbookPublicationService(self.service).prepare(key=self.key, edition='', revision='', node='',
                    teaching_revision='1', review={}, audio_audit={}, classroom_directory=self.root)
            path.write_bytes(raw)
        verify_quantity_visual_revisions(self.service.get(self.key), self.root)
        paths[1].unlink()
        with self.assertRaises(ApiError):
            self.apply(value)

    def test_quantity_original_encoding_may_differ_but_frozen_bytes_and_pixels_must_match(self):
        from PIL import Image
        value = self.quantity_patch()
        definition = value['derivedImages'][0]
        path = self.root / self.cid / 'media/group-2.png'
        output = io.BytesIO()
        with Image.open(path) as image:
            image.save(output, format='PNG', compress_level=9)
        self.assertNotEqual(sha_bytes(output.getvalue()), definition['replacesSha256'])
        path.write_bytes(output.getvalue())
        definition['replacesSha256'] = sha_bytes(output.getvalue())
        frozen = json.loads(self.service.get(self.key)['input_json'])
        next(a for a in frozen['originalMedia']['assets'] if a['mediaPath'] == definition['replacesPath'])['sha256'] = definition['replacesSha256']
        self.db.execute('UPDATE learning_textbook_course_previews SET input_json=? WHERE preview_key=?', (canonical(frozen), self.key))
        self.db.raw.commit()
        self.apply(value)
        verify_quantity_visual_revisions(self.service.get(self.key), self.root)

    def test_quantity_revision_lost_save_reconciles_without_new_provider_calls(self):
        value = self.quantity_patch()
        def lost(target):
            self.save(target)
            raise TimeoutError('response lost')
        self.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError):
            self.apply(value)
        self.apply(value)
        verify_quantity_visual_revisions(self.service.get(self.key), self.root)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()

    def test_v3_quiz_visual_preserves_question_audio_and_archive_identity(self):
        # A historical unknown field is preserved; the renderer's actual
        # visual field receives the same already frozen picture.
        question = self.classroom['scenes'][6]['content']['questions'][0]
        question['questionVisual'] = {'kind': 'image', 'src': self.cover, 'alt': '待辨认的目标图'}
        self.persist_source()
        original = deepcopy(self.classroom)
        value = self.quiz_visual_patch()
        value['changes'].extend(self.canvas_patch()['changes'])
        value['changes'].extend(deepcopy(self.patch['changes']))
        receipt = self.apply(value)
        expected = deepcopy(original)
        expected['scenes'][6]['content']['questions'][0]['visual'] = value['changes'][0]['visual']
        expected['scenes'][0]['content']['canvas'] = value['changes'][1]['canvas']
        expected['scenes'][5]['content']['html'] = value['changes'][2]['html']
        expected['createdAt'] = 'saved'
        self.assertEqual(self.classroom, expected)
        from content.textbook_release import public_classroom
        public_question = public_classroom({'classroomId': self.classroom['id'],
            'classroom': self.classroom})['scenes'][6]['content']['questions'][0]
        self.assertEqual(public_question['visual'], value['changes'][0]['visual'])
        self.assertNotIn('questionVisual', public_question)
        self.assertNotIn('answer', public_question)
        archive = self.folder / 'visual-revisions' / digest({'previewKey': self.key, 'patch': value})
        self.assertEqual(json.loads((archive / 'source.json').read_text()), original)
        self.assertEqual(json.loads((archive / 'target.json').read_text())['scenes'][6], expected['scenes'][6])
        for name in ('plan.json', 'receipts.json'):
            self.assertEqual((archive / name).read_bytes(), (self.folder / name).read_bytes())
        self.assertEqual(receipt['audioIdentityClassroomSha256'], self.plan['classroomSha256'])
        self.assertEqual(self.apply(value), receipt)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()

    def test_quiz_visual_rejects_stale_identity_and_nonvisual_fields(self):
        good = self.quiz_visual_patch()
        changes = [{'beforeQuestionSha256': 'f' * 64}, {'questionId': 'missing'},
                   {'sceneId': 'scene-0'}, {'sceneId': 'scene-5'}, {'sceneId': 'missing'},
                   {'answer': ['B']}, {'question': '另外的问题'}, {'actions': []}]
        for change in changes:
            value = deepcopy(good)
            value['changes'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ApiError):
                self.apply(value)
        for version in (SCHEMA, CANVAS_SCHEMA):
            with self.subTest(version=version), self.assertRaises(ApiError):
                self.apply({**good, 'schemaVersion': version})
        self.runtime.save_preview_classroom.assert_not_called()

    def test_quiz_visual_rejects_new_changed_or_unsafe_media(self):
        good = self.quiz_visual_patch()
        (self.root / self.cid / 'media/new.png').write_bytes(b'not a frozen original')
        for visual in (
                {'kind': 'image', 'src': f'/api/classroom-media/{self.cid}/media/new.png', 'alt': '新图'},
                {'kind': 'image', 'src': '/api/classroom-media/other/media/picture.png', 'alt': '外课图'},
                {'kind': 'image', 'src': 'https://example.com/image.png', 'alt': '外链'},
                {'kind': 'image', 'src': 'data:image/svg+xml;base64,PHN2Zy8+', 'alt': '内嵌'},
                {'kind': 'quantity', 'count': 3},
                {**good['changes'][0]['visual'], 'onload': 'alert(1)'},
                {**good['changes'][0]['visual'], 'correct': True},
                {**good['changes'][0]['visual'], 'alt': ''}):
            value = deepcopy(good)
            value['changes'][0]['visual'] = visual
            with self.subTest(visual=visual), self.assertRaises(ApiError):
                self.apply(value)
        (self.root / self.cid / 'media/cover.png').write_bytes(b'changed original bytes')
        with self.assertRaises(ApiError):
            self.apply(good)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_v2_canvas_preserves_other_content_audio_and_original_assets(self):
        original = deepcopy(self.classroom)
        value = self.canvas_patch()
        value['changes'].extend(deepcopy(self.patch['changes']))
        receipt = self.apply(value)
        expected = deepcopy(original)
        expected['scenes'][0]['content']['canvas'] = value['changes'][0]['canvas']
        expected['scenes'][5]['content']['html'] = value['changes'][1]['html']
        expected['createdAt'] = 'saved'
        self.assertEqual(self.classroom, expected)
        self.assertEqual((self.root / self.cid / 'media/cover.png').read_bytes(), b'existing-original-cover')
        self.assertEqual((self.folder / 'plan.json').read_text(), canonical(self.plan))
        self.assertEqual((self.folder / 'receipts.json').read_text(), canonical(self.result['audioReceipts']))
        self.assertEqual(self.apply(value), receipt)
        narrate_preview(self.service, self.key, self.root)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()
        self.runtime.start_generation.assert_not_called()

    def test_canvas_requires_a_nonempty_unique_id_on_every_element(self):
        good = self.canvas_patch()
        for extra in ({'type': 'text'}, {'id': '', 'type': 'text'}, {'id': '   ', 'type': 'text'},
                      {'id': good['changes'][0]['canvas']['elements'][0]['id'], 'type': 'text'}):
            value = deepcopy(good)
            value['changes'][0]['canvas']['elements'].append(extra)
            with self.subTest(extra=extra), self.assertRaises(ApiError):
                self.apply(value)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_canvas_hash_scene_identity_and_audio_mutations_are_rejected(self):
        good = self.canvas_patch()
        mutations = []
        for change in ({'beforeCanvasSha256': 'f' * 64}, {'sceneId': 'scene-5'}, {'sceneId': 'scene-6'},
                       {'actions': []}, {'order': 2}, {'type': 'interactive'}, {'questions': []}):
            value = deepcopy(good)
            value['changes'][0].update(change)
            mutations.append(value)
        mutations.append({**good, 'schemaVersion': SCHEMA})
        for extra in ({'type': 'audio', 'src': self.classroom['scenes'][0]['actions'][0]['audioUrl']},
                      {'type': 'text', 'audioUrl': 'another.wav'},
                      {'type': 'text', 'content': '<img src="https://example.com/new.png">'},
                      {'type': 'text', 'content': '<span onclick="alert(1)">字</span>'}):
            value = deepcopy(good)
            value['changes'][0]['canvas']['elements'].append({'id': 'invalid-extra', **extra})
            mutations.append(value)
        for value in mutations:
            with self.subTest(change=value['changes'][0]), self.assertRaises(ApiError):
                self.apply(value)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_canvas_rejects_unknown_unfrozen_and_changed_image_bytes(self):
        for src in ('https://example.com/image.png', '/api/classroom-media/other/media/image.png',
                    self.classroom['scenes'][0]['actions'][0]['audioUrl'], 'data:image/png;base64,YQ=='):
            value = self.canvas_patch()
            value['changes'][0]['canvas']['elements'][0]['src'] = src
            with self.subTest(src=src), self.assertRaises(ApiError):
                self.apply(value)
        # A file being present does not make it an original frozen lesson asset.
        (self.root / self.cid / 'media/new.png').write_bytes(b'new')
        self.append_source_html(f'<img src="/api/classroom-media/{self.cid}/media/new.png">')
        value = self.canvas_patch()
        value['changes'][0]['canvas']['elements'][0]['src'] = f'/api/classroom-media/{self.cid}/media/new.png'
        with self.assertRaises(ApiError):
            self.apply(value)
        (self.root / self.cid / 'media/picture.png').write_bytes(b'changed bytes')
        with self.assertRaises(ApiError):
            self.apply(self.canvas_patch())
        self.runtime.save_preview_classroom.assert_not_called()

    def test_canvas_accepts_only_exact_original_inline_svg_bytes(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><rect width="30" height="20" fill="#DE2910"/></svg>'
        self.append_source_html(svg)
        for variant in (svg.replace('#DE2910', '#de2910'), svg.replace('><rect', '>\n<rect')):
            with self.subTest(variant=variant), self.assertRaises(ApiError):
                self.apply(self.svg_patch(variant))
        value = self.svg_patch(svg)
        receipt = self.apply(value)
        self.assertEqual(self.apply(value), receipt)
        encoded = self.classroom['scenes'][0]['content']['canvas']['elements'][-1]['src'].split(',', 1)[1]
        self.assertEqual(base64.b64decode(encoded), svg.encode())
        self.runtime.save_preview_classroom.assert_called_once()

    def test_exact_source_svg_with_script_events_or_external_references_is_rejected(self):
        for svg in ('<svg><script>alert(1)</script></svg>', '<svg onload="alert(1)"><path d="M0 0"/></svg>',
                    '<svg><image href="https://example.com/image.png"/></svg>',
                    '<svg><path fill="url(https://example.com/paint)" d="M0 0"/></svg>',
                    '<svg><foreignObject><p>HTML</p></foreignObject></svg>'):
            self.append_source_html(svg)
            with self.subTest(svg=svg), self.assertRaises(ApiError):
                self.apply(self.svg_patch(svg))
        self.runtime.save_preview_classroom.assert_not_called()

    def test_canvas_layout_revision_preserves_an_adopted_svg_and_audio(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 20"><path d="M2 2L20 18"/></svg>'
        self.append_source_canvas_svg(svg)
        original = deepcopy(self.classroom)
        old = original['scenes'][0]['content']['canvas']
        value = self.canvas_patch()
        value['changes'][0]['canvas'] = deepcopy(old)
        value['changes'][0]['canvas']['elements'][-1]['left'] = 120
        receipt = self.apply(value)
        expected = deepcopy(original)
        expected['scenes'][0]['content']['canvas']['elements'][-1]['left'] = 120
        expected['createdAt'] = 'saved'
        self.assertEqual(self.classroom, expected)
        self.assertEqual(self.apply(value), receipt)
        self.assertEqual((self.folder / 'plan.json').read_text(), canonical(self.plan))
        self.assertEqual((self.folder / 'receipts.json').read_text(), canonical(self.result['audioReceipts']))
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_canvas_svg_reuse_does_not_allow_new_or_reencoded_geometry(self):
        svg = '<svg><path d="M2 2L20 18"/></svg>'
        self.append_source_canvas_svg(svg)
        value = self.canvas_patch()
        original_src = value['changes'][0]['canvas']['elements'][-1]['src']
        for src in ('data:image/svg+xml;base64,' + base64.b64encode(
                    svg.replace('20 18', '21 18').encode()).decode(), original_src + '\n'):
            changed = deepcopy(value)
            changed['changes'][0]['canvas']['elements'][-1]['src'] = src
            with self.subTest(src=src), self.assertRaises(ApiError):
                self.apply(changed)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_unsafe_adopted_canvas_svg_is_revalidated_even_when_unchanged(self):
        for svg in ('<svg><script>alert(1)</script></svg>', '<svg onload="alert(1)"/>',
                    '<svg><image href="https://example.com/image.png"/></svg>',
                    '<svg><path fill="url(https://example.com/paint)" d="M0 0"/></svg>'):
            elements = self.classroom['scenes'][0]['content']['canvas']['elements']
            elements[:] = [element for element in elements if element['id'] != 'adopted-svg']
            self.append_source_canvas_svg(svg)
            with self.subTest(svg=svg), self.assertRaises(ApiError):
                self.apply(self.canvas_patch())
        self.runtime.save_preview_classroom.assert_not_called()

    def test_svg_only_in_a_script_string_is_not_an_inline_original(self):
        svg = '<svg><circle r="2"/></svg>'
        self.append_source_html('<script>const unused = ' + json.dumps(svg) + ';</script>')
        with self.assertRaises(ApiError):
            self.apply(self.svg_patch(svg))
        self.runtime.save_preview_classroom.assert_not_called()

    def test_canvas_lost_save_response_reconciles_without_reposting(self):
        value = self.canvas_patch()
        def lost(target):
            self.save(target)
            raise TimeoutError('response lost')
        self.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError):
            self.apply(value)
        receipt = self.apply(value)
        self.assertEqual(self.service.get(self.key)['classroom_sha256'], receipt['targetSha256'])
        self.runtime.save_preview_classroom.assert_called_once()

    def test_html_revision_preserves_audio_identity_and_replays_without_paid_calls(self):
        original = deepcopy(self.classroom)
        receipt = self.apply()
        row = self.service.get(self.key)
        self.assertEqual(row['classroom_sha256'], receipt['targetSha256'])
        self.assertNotEqual(row['classroom_sha256'], self.source_sha)
        self.assertEqual(receipt['audioIdentityClassroomSha256'], self.plan['classroomSha256'])
        self.assertEqual(json.loads((self.folder / 'plan.json').read_text()), self.plan)
        self.assertEqual(json.loads(row['result_json'])['audioReceipts'], self.result['audioReceipts'])
        self.assertEqual(json.loads((self.archive() / 'source.json').read_text()), original)
        self.assertNotIn('frozenPreview', json.loads(row['result_json']))
        # Existing narration's fast path still validates/reuses every WAV.
        narrate_preview(self.service, self.key, self.root)
        self.assertEqual(self.apply(), receipt)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()
        self.runtime.start_generation.assert_not_called()
        for before, after in zip(original['scenes'], self.classroom['scenes']):
            self.assertEqual(before['actions'], after['actions'])

    def test_cues_helper_media_and_non_html_mutations_are_rejected(self):
        html = self.patch['changes'][0]['html']
        changes = [html.replace('数一数。', '数一数！'),
                   html.replace('let active=null', 'let active=1'),
                   html + '<img src="/api/classroom-media/other/media/extra.png">',
                   html + '<script src="https://example.com/extra.js"></script>']
        for changed in changes:
            value = deepcopy(self.patch)
            value['changes'][0]['html'] = changed
            with self.subTest(changed=changed[-80:]), self.assertRaises(ApiError):
                self.apply(value)
        for extra in ('actions', 'sceneOrder', 'stage'):
            value = deepcopy(self.patch)
            value['changes'][0][extra] = []
            with self.subTest(extra=extra), self.assertRaises(ApiError):
                self.apply(value)
        self.runtime.save_preview_classroom.assert_not_called()

    def test_active_narration_stale_version_and_changed_assets_are_rejected(self):
        with (self.folder / 'operator.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ApiError):
                self.apply()
        with self.assertRaises(ApiError):
            self.apply({**self.patch, 'expectedSourceSha256': 'c' * 64})
        audio = next((self.root / self.cid / 'audio').iterdir())
        audio.write_bytes(b'changed')
        with self.assertRaises(ApiError):
            self.apply()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_existing_frozen_lesson_picture_can_be_added_but_unknown_or_changed_image_cannot(self):
        value = deepcopy(self.patch)
        value['changes'][0]['html'] += f'<img src="{self.cover}" alt="等待操作">'
        unknown = deepcopy(value)
        unknown['changes'][0]['html'] += '<img src="/api/classroom-media/elsewhere/media/unreviewed.png">'
        with self.assertRaises(ApiError):
            self.apply(unknown)
        cover = self.root / self.cid / 'media/cover.png'
        cover.write_bytes(b'replaced image bytes')
        with self.assertRaises(ApiError):
            self.apply(value)
        self.runtime.save_preview_classroom.assert_not_called()
        cover.write_bytes(b'existing-original-cover')
        receipt = self.apply(value)
        self.assertIn(self.cover, self.classroom['scenes'][5]['content']['html'])
        self.assertEqual(self.apply(value), receipt)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_generation.assert_not_called()
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_incomplete_audio_and_runtime_drift_are_rejected(self):
        self.db.execute("UPDATE learning_textbook_course_previews SET status='review_required' WHERE preview_key=?", (self.key,))
        self.db.raw.commit()
        with self.assertRaises(ApiError):
            self.apply()
        self.db.execute("UPDATE learning_textbook_course_previews SET status='preview_ready' WHERE preview_key=?", (self.key,))
        self.db.raw.commit()
        self.classroom['scenes'][0]['actions'][0]['text'] = '其他编辑者的讲解。'
        with self.assertRaises(ApiError):
            self.apply()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_lost_save_response_reconciles_exact_target_without_second_save(self):
        def lost(value):
            self.save(value)
            raise TimeoutError('response lost')
        self.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError):
            self.apply()
        self.assertEqual(self.service.get(self.key)['classroom_sha256'], self.source_sha)
        receipt = self.apply()
        self.assertEqual(self.service.get(self.key)['classroom_sha256'], receipt['targetSha256'])
        self.runtime.save_preview_classroom.assert_called_once()

    def test_unknown_save_with_old_runtime_is_not_reposted(self):
        self.runtime.save_preview_classroom.side_effect = TimeoutError('unknown')
        with self.assertRaises(TimeoutError):
            self.apply()
        with self.assertRaises(ApiError):
            self.apply()
        self.runtime.save_preview_classroom.assert_called_once()

    def test_commit_without_final_receipt_recovers_and_detects_tampered_archive(self):
        from services import textbook_preview_visual_revision as module
        real = module.immutable
        def fail_last(path, raw):
            if path.name == 'amendment.json':
                raise OSError('interrupted after commit')
            real(path, raw)
        with patch.object(module, 'immutable', side_effect=fail_last), self.assertRaises(OSError):
            self.apply()
        self.assertNotEqual(self.service.get(self.key)['classroom_sha256'], self.source_sha)
        receipt = self.apply()
        self.assertEqual(json.loads((self.archive() / 'amendment.json').read_text()), receipt)
        (self.archive() / 'plan.json').write_text('{}')
        with self.assertRaises(ApiError):
            self.apply()
        self.runtime.save_preview_classroom.assert_called_once()

    def test_asr_uses_original_identity_and_publication_requires_current_audit(self):
        from scripts import audit_textbook_audio as audit_script
        receipt = self.apply()
        output = self.root / 'asr-audit'
        self.runtime.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('not_found', 'not found', status_code=404)
        self.runtime.start_formal_audio_asr.side_effect = lambda **kw: {
            'status': 'succeeded', 'requestId': kw['request_id'], 'transcript': '数一数。'}
        argv = ['audit_textbook_audio.py', '--key', self.key, '--classroom-directory', str(self.root), '--output', str(output)]
        with patch.object(audit_script.AppConfig, 'from_env'), patch.object(audit_script, 'Database', return_value=self.db), \
                patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=self.runtime), patch('sys.argv', argv):
            audit_script.main()
            audit_script.main()
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 8)
        self.assertEqual({c.kwargs['classroom_content_sha256'] for c in self.runtime.start_formal_audio_asr.call_args_list}, {'a' * 64})
        audit = json.loads((output / 'audit.json').read_text())
        self.assertTrue(audit['passed'])
        self.assertEqual(audit['sourceSha256'], receipt['targetSha256'])
        row = self.service.get(self.key)
        review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
                  'publicationAuthorized': True, 'reviewer': 'test', 'basis': 'isolated review',
                  'sourceSha256': row['classroom_sha256'], 'reviewedAt': now_ms() - 1}
        publication = TextbookPublicationService(self.service)
        def prepare(value):
            return publication.prepare(key=self.key, edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
                teaching_revision='1', review=review, audio_audit=value, classroom_directory=self.root)
        old_audit = {**audit, 'sourceSha256': self.source_sha}
        old_audit['sha256'] = digest({k: v for k, v in old_audit.items() if k != 'sha256'})
        with self.assertRaises(ApiError):
            prepare(old_audit)
        prepared = prepare(audit)
        self.assertEqual(prepared['frozen']['sourceSha256'], receipt['targetSha256'])
        self.assertEqual(prepared['release']['audioAudit']['segments'], 8)
        self.runtime.start_formal_audio_tts.assert_not_called()


if __name__ == '__main__':
    unittest.main()
