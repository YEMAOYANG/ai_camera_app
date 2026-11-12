import unittest

from backend.tests.test_courseware_release import refresh_receipts, sample_inputs
from content.courseware_release import build_release, validate_light_release
from content.textbook_interactive_narration import interactive_cues, without_audio_helper
from courseware.tools import game_audio


class CoursewareGameAudioReleaseTests(unittest.TestCase):
    def test_release_projects_the_same_archive_wav_into_the_game(self):
        inputs = sample_inputs()
        body = inputs['body']
        teacher_line = body['scenes'][0]['actions'][0]
        game = {'id': 'game', 'stageId': 'authored', 'type': 'interactive', 'actions': [],
                'content': {'type': 'interactive', 'html': '<html><head></head><body></body></html>'}}
        body['scenes'].insert(1, game)
        game_audio.compile_cues(body, {'game': {'listen': teacher_line['id']}}, {teacher_line['id']})
        game_audio.bind_recordings(body)
        inputs['playReceipt']['pages'] = [{'scene': 2, 'ok': True, 'finished': True, 'errors': [], 'stuck': None}]
        refresh_receipts(inputs)

        prepared = build_release(inputs)
        self.assertEqual(validate_light_release(prepared, inputs['manifest']), [])
        release = prepared['release']
        teacher, game, _ = release['classroom']['scenes']
        expected = teacher['actions'][0]['audioUrl']
        html = game['content']['html']
        self.assertIn(f'/api/classroom-media/{release["classroomId"]}/audio/', expected)
        self.assertIn(f'const clips={{"listen":"{expected}"}};let active=null;', html)
        self.assertNotIn('mira-pre-recorded-audio', without_audio_helper(html))
        self.assertEqual(interactive_cues(html), [{'id': 'listen', 'text': teacher_line['text']}])
        self.assertEqual(sum(item['mimeType'] == 'audio/wav' for item in release['media']), 1)
