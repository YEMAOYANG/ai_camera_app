"""Full-workload limits and saved-audio recovery; isolated DB/WAVs, mock HTTP."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_operator_revision import speech_index
from content.textbook_preview_audio_contract import MAX_SPEECH_ACTIONS, new_audio_plan, new_pinyin_audio_plan
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.textbook_preview_audio import core_content, narrate_preview
from services.textbook_preview_pronunciation_revision import _speech
from tests import test_textbook_pinyin_narrator as pinyin_fixtures
from tests import test_textbook_preview_audio_v2 as audio_fixtures


class PreviewAudioWorkloadTests(unittest.TestCase):
    def fixture(self, count, *, unsupported_last=False):
        helper = pinyin_fixtures.PinyinNarratorTests()
        self.addCleanup(helper.doCleanups)
        f = helper.fixture()
        # Keep each page within the existing formal 20-line limit. The lesson
        # count grows independently of the original eight-page test fixture.
        per_scene = OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT['speechActions']['perScene']['max']
        remaining = count - 8
        while remaining:
            index = len(f.classroom['scenes'])
            scene = deepcopy(f.classroom['scenes'][0])
            scene.update(id=f'extended-scene-{index}', order=index + 1,
                         actions=[{'id': f'extended-action-{index}-{n}', 'type': 'speech',
                                   'text': '听老师读这个音，再看图片。'}
                                  for n in range(min(remaining, per_scene))])
            f.classroom['scenes'].append(scene)
            remaining -= len(scene['actions'])
        if unsupported_last:
            f.classroom['scenes'][-1]['actions'][-1]['text'] = '这一句包含不支持的 hello。'
        frozen = json.loads(f.service.get(f.key)['input_json'])
        frozen['previewPrompt']['expectedSceneCount'] = len(f.classroom['scenes'])
        f.db.execute('UPDATE learning_textbook_course_previews SET input_json=? WHERE preview_key=?',
                     (canonical(frozen), f.key))
        audio_fixtures.PreviewAudioV2Tests().persist(f)
        parent = new_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen)
        f.plan = new_pinyin_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen,
            parent_plan=parent, revision_id='d' * 64)
        (f.folder / 'plan.json').write_text(canonical(f.plan))
        return f

    def assert_no_audio_calls(self, f):
        f.runtime.get_formal_audio_tts.assert_not_called()
        f.runtime.start_formal_audio_tts.assert_not_called()
        f.client._request_formal_audio_json.assert_not_called()
        f.runtime.download_formal_audio_tts.assert_not_called()

    def test_extended_lessons_reach_full_pronunciation_preflight_before_dispatch(self):
        self.assertEqual(MAX_SPEECH_ACTIONS, 240)
        for count in (161, 162, 240):
            with self.subTest(count=count):
                f = self.fixture(count, unsupported_last=True)
                before = (f.folder / 'plan.json').read_bytes()
                with self.assertRaises(ApiError) as raised:
                    narrate_preview(f.service, f.key, f.root, speech_selection=f.selection(0))
                # The selected first line is supported; the final, unselected
                # line must still reach phoneme preflight before any request.
                self.assertEqual(raised.exception.code, 'textbook_pinyin_pronunciation_invalid')
                self.assert_no_audio_calls(f)
                self.assertEqual((f.folder / 'plan.json').read_bytes(), before)

    def test_162_complete_lines_recover_lost_save_then_reuse_without_new_audio(self):
        f = self.fixture(162)
        before_plan = (f.folder / 'plan.json').read_bytes()
        before_text = [(s['id'], a['id'], a['text']) for s in f.classroom['scenes'] for a in s['actions']]
        def lost_response(value):
            f.save(value)
            raise OpenMaicFullRuntimeError('response_lost', 'saved but response lost')
        f.runtime.save_preview_classroom.side_effect = lost_response
        with self.assertRaises(OpenMaicFullRuntimeError):
            narrate_preview(f.service, f.key, f.root)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 162)
        saved_bytes = (f.root / (f.cid + '.json')).read_bytes()
        f.runtime.save_preview_classroom.side_effect = f.save
        result = narrate_preview(f.service, f.key, f.root)
        self.assertEqual((result['status'], result['result']['audioCompleted']), ('preview_ready', 162))
        narrate_preview(f.service, f.key, f.root)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 162)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 162)
        self.assertEqual(f.runtime.save_preview_classroom.call_count, 1)
        self.assertEqual((f.folder / 'plan.json').read_bytes(), before_plan)
        self.assertEqual((f.root / (f.cid + '.json')).read_bytes(), saved_bytes)
        self.assertEqual([(s['id'], a['id'], a['text']) for s in f.classroom['scenes'] for a in s['actions']], before_text)

    def test_above_formal_limit_rejects_complete_and_selected_runs_before_audio(self):
        for selected in (False, True):
            with self.subTest(selected=selected):
                f = self.fixture(241)
                before = (f.folder / 'plan.json').read_bytes()
                with self.assertRaises(ApiError) as raised:
                    narrate_preview(f.service, f.key, f.root,
                                    speech_selection=f.selection(0) if selected else None)
                self.assertEqual(raised.exception.code, 'textbook_preview_audio_workload')
                self.assert_no_audio_calls(f)
                f.runtime.save_preview_classroom.assert_not_called()
                self.assertEqual((f.folder / 'plan.json').read_bytes(), before)
                self.assertEqual(json.loads((f.folder / 'receipts.json').read_text()), [])

    def test_revision_full_source_indexes_use_same_limit_and_preserve_uniqueness(self):
        for count in (161, 162, 240, 241):
            room = {'scenes': [{'id': f'scene-{i}', 'actions': [
                {'id': f'action-{i}', 'type': 'speech', 'text': '老师说一句话。'}]} for i in range(count)]}
            for indexer in (speech_index, _speech):
                with self.subTest(count=count, indexer=indexer.__name__):
                    if count <= MAX_SPEECH_ACTIONS:
                        self.assertEqual(len(indexer(room)), count)
                    else:
                        with self.assertRaises(ApiError):
                            indexer(room)
        duplicate = {'scenes': [{'id': 'same', 'actions': [
            {'id': 'same', 'type': 'speech', 'text': '老师说一句话。'}] * 2}]}
        for indexer in (speech_index, _speech):
            with self.assertRaises(ApiError):
                indexer(duplicate)


if __name__ == '__main__':
    unittest.main()
