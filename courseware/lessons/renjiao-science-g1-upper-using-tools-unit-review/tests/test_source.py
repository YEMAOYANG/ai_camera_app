from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom
from courseware.tools.game_audio import verify_recordings


LESSON = Path(__file__).resolve().parents[1]


class UsingToolsReviewTest(unittest.TestCase):
    def test_resume_narration_does_not_announce_a_completed_demo(self):
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        cues = {
            'sort-tools': '看卡片往哪里去。工具能做图里的事，卡片才会留下。',
            'tool-camera': '等照片出现，在照片里找一个圆孔和一个三角孔。',
        }
        scenes = {scene['key']: scene for scene in lesson['scenes']}
        for key, cue in cues.items():
            scene = scenes[key]
            index = scene['script'].index({'setState': {'pause': False}})
            self.assertEqual(scene['script'][index + 1], {'say': cue})

    def test_source_and_picture_questions(self):
        notes = json.loads((LESSON / 'official-notes.json').read_text())
        brief = json.loads((LESSON / 'brief.json').read_text())
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        self.assertEqual(notes['officialTextbook']['printedPages'], [62, 63, 64])
        self.assertEqual(brief['goals'], notes['objectives'])
        self.assertEqual(brief['officialNotesSha256'], sha256((LESSON / 'official-notes.json').read_bytes()).hexdigest())
        self.assertEqual({key for entry in notes['factChecks'] for key in entry.get('images', [])}, set(lesson['images']))
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in quiz['questions']), {'A': 2, 'B': 2, 'C': 2})
        for question in quiz['questions']:
            self.assertEqual(len({option['visual']['image'] for option in question['options'].values()}), 3)
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='using-tools-test', now_ms=1)
            body = draft['body']
            issues = check_classroom(body, Path(workspace) / 'media', notes=notes, roster=draft['roster'],
                                     grade=1, teaching=True, require_play=True)
            self.assertEqual({issue['code'] for issue in issues if issue['severity'] == 'error'}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid', 'play_receipt_missing',
            })
            verify_recordings(body, before_voice=True)
            scene = next(scene for scene in body['scenes'] if scene['id'] == 'scene-tool-camera')
            self.assertIn('miraActivityCheckpoint', scene['content']['html'])
            self.assertIn('mira-game-observation-ready', scene['content']['html'])

    def test_observation_and_transfer_are_demonstrated_in_the_narration(self):
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        scripts = {scene['key']: [beat['say'] for beat in scene.get('script', []) if 'say' in beat]
                   for scene in lesson['scenes']}
        self.assertTrue(any('确实看见三角孔' in line and '我猜' in line and '拿笔试' in line
                            for line in scripts['what-to-look-for']))
        improve = scripts['test-and-improve']
        self.assertTrue(any('夹口够不到' in line and '改用长夹' in line and '都不挪' in line
                            for line in improve))
        new_task = next(i for i, line in enumerate(improve) if '积木桥下' in line)
        steps = ('积木桥下', '画夹口从旁边', '合住球', '有没有到桥外')
        self.assertEqual(len(improve[new_task:]), len(steps))
        for line, expected in zip(improve[new_task:], steps):
            self.assertIn(expected, line)
