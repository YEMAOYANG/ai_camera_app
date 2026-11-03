import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from courseware.tools.check import body_hash, check_classroom


SAMPLE = Path(__file__).parent / 'fixtures' / 'sample_body.json'


def valid_body():
    body = json.loads(SAMPLE.read_text(encoding='utf-8'))
    body['stage']['generatedAgentConfigs'] = [{'name': 'Teacher', 'voiceConfig': {'voiceId': 'Ethan'}}]
    body['scenes'] = [
        {'type': 'slide', 'actions': [], 'content': {'canvas': {'elements': [
            {'id': 'title', 'type': 'text', 'left': 20, 'top': 20, 'width': 300, 'content': '<p style="font-size:20px">Hello</p>'}]}}},
        {'type': 'interactive', 'actions': [
            *[{'type': 'speech', 'text': 'Hello', 'audioUrl': '/api/classroom-media/stage/media/a.wav'} for _ in range(3)],
            {'type': 'widget_highlight', 'target': '#cell-2-1'},
            {'type': 'widget_reveal', 'target': '#fixed'},
            {'type': 'widget_setState', 'state': {'currentStep': 1}}],
         'content': {'html': '<style>#cv{width:1280px;height:720px;}</style><div id="fixed"></div><script>var currentStep; var id="cell-";</script>'}},
        {'type': 'quiz', 'actions': [], 'content': {'questions': [{
            'id': 'q', 'question': 'How many?', 'options': [{'value': 'A', 'label': 'One'}, {'value': 'B', 'label': 'Two'}],
            'answer': ['A'], 'analysis': 'One', 'skill': 'count', 'questionAudioUrl': '/api/classroom-media/stage/media/a.wav',
            'optionVisuals': {'A': {'kind': 'quantity'}, 'B': {'kind': 'image'}}}]}}]
    return body


def codes(issues):
    return {issue['code'] for issue in issues}


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.body = valid_body()
        self.notes = {'resources': {name: {'findings': ['a'], 'pageRefs': ['1']} for name in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise')}}
        self.receipt = {'bodySha256': body_hash(self.body), 'ok': True, 'viewports': ['1280x720', '1000x563', '640x360']}
        self.verification = {'bodySha256': body_hash(self.body), 'speechChecked': 3, 'questionsChecked': 1, 'disagreements': []}

    def test_all_gates_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'a.wav').write_bytes(b'a')
            self.assertEqual([], check_classroom(self.body, directory, notes=self.notes, roster={'Teacher': 'male'}, receipt=self.receipt, verification=self.verification, grade=1))

    def test_notes(self):
        self.notes['resources']['courseware']['pageRefs'] = []
        self.assertIn('notes_incomplete', codes(check_classroom(self.body, notes=self.notes)))

    def test_notes_not_provided_needs_evidence(self):
        item = self.notes['resources']['afterClassExercise']
        item.update(status='not_provided', findings=[], pageRefs=[], evidence='lesson details sha256 ab12 lists no after-class exercise')
        self.assertNotIn('notes_incomplete', codes(check_classroom(self.body, notes=self.notes)))
        item['evidence'] = ' '
        self.assertIn('notes_incomplete', codes(check_classroom(self.body, notes=self.notes)))
        item.update(status='reviewed', evidence='kept but ignored')
        self.assertIn('notes_incomplete', codes(check_classroom(self.body, notes=self.notes)))

    def test_media_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            digest = hashlib.sha256(b'good').hexdigest()
            filename = 'asset-' + digest + '.png'
            self.body['scenes'][0]['content']['url'] = '/api/classroom-media/stage/media/' + filename
            Path(directory, filename).write_bytes(b'bad')
            Path(directory, 'unused').write_bytes(b'x')
            self.body['scenes'][1]['actions'][0]['audioUrl'] = ''
            issues = check_classroom(self.body, directory)
            self.assertTrue({'speech_audio_missing', 'media_missing', 'media_hash_mismatch', 'media_unreferenced'} <= codes(issues))
            Path(directory, filename).write_bytes(b'good')
            self.assertNotIn('media_hash_mismatch', codes(check_classroom(self.body, directory)))
        self.assertIn('media_directory_missing', codes(check_classroom(self.body, directory)))

    def test_slide_layout(self):
        elements = self.body['scenes'][0]['content']['canvas']['elements']
        elements.append(dict(elements[0], id='overlap'))
        elements.append(dict(elements[0], id='outside', top=550))
        self.assertTrue({'slide_text_overlap', 'slide_text_outside'} <= codes(check_classroom(self.body)))

    def test_interactive(self):
        scene = self.body['scenes'][1]
        scene['actions'] = [dict(type='speech', text='x' * 41, audioUrl='a'), dict(type='widget_annotation', target='#missing'), dict(type='widget_setState', state={'missingKey': 1})]
        scene['content']['html'] = ''
        self.assertTrue({'speech_too_long', 'interactive_operations_missing', 'interactive_speech_missing', 'interactive_stage_missing', 'interactive_target_missing', 'interactive_state_missing'} <= codes(check_classroom(self.body)))
        scene['actions'][0]['text'] = 'x' * 26
        self.assertEqual('warn', next(i['severity'] for i in check_classroom(self.body) if i['code'] == 'speech_too_long'))

    def test_interactive_quoted_targets(self):
        scene = self.body['scenes'][1]
        scene['actions'].extend([
            {'type': 'widget_highlight', 'target': '#start-btn'},
            {'type': 'widget_reveal', 'target': '#card-zero'},
            {'type': 'widget_annotation', 'target': '#absent'},
        ])
        scene['content']['html'] += "<script>o.btn||'start-btn'; var cards=[\"card-zero\"];</script>"
        missing = [i['detail'] for i in check_classroom(self.body) if i['code'] == 'interactive_target_missing']
        self.assertEqual(['#absent'], missing)

    def test_interactive_state_severity_per_action(self):
        scene = self.body['scenes'][1]
        scene['actions'].extend([
            {'type': 'widget_setState', 'state': {'currentStep': 1, 'unused': 2}},
            {'type': 'widget_setState', 'state': {'missingOne': 1, 'missingTwo': 2}},
            {'type': 'widget_setState', 'state': {}},
        ])
        issues = [i for i in check_classroom(self.body) if i['code'] == 'interactive_state_missing']
        self.assertEqual([('unused', 'warn'), ('missingOne', 'error'), ('missingTwo', 'error'), ('No state keys', 'error')],
                         [(i['detail'], i['severity']) for i in issues])

    def test_quiz(self):
        q = self.body['scenes'][2]['content']['questions'][0]
        q.update(question='请你读 🐥', options=[{'value': 'A', 'label': '🐥'}, {'value': 'A', 'label': 'two'}], answer=['B'], analysis='', skill='', questionAudioUrl='', optionVisuals={})
        self.assertTrue({'quiz_options_invalid', 'quiz_answer_invalid', 'quiz_analysis_missing', 'quiz_skill_missing', 'quiz_questionAudioUrl_missing', 'quiz_visuals_invalid', 'quiz_emoji', 'self_read_instruction'} <= codes(check_classroom(self.body, grade=1)))
        self.assertNotIn('quiz_emoji', codes(check_classroom(self.body, grade=3)))

    def test_answer_positions_must_be_spread(self):
        template = self.body['scenes'][2]['content']['questions'][0]

        def with_answers(letters):
            self.body['scenes'][2]['content']['questions'] = [dict(template, id='q%d' % i, answer=[letter]) for i, letter in enumerate(letters)]
            return codes(check_classroom(self.body))
        self.assertIn('answer_position_skewed', with_answers('AAAB'))
        self.assertNotIn('answer_position_skewed', with_answers('AABB'))
        self.assertNotIn('answer_position_skewed', with_answers('AAB'))

    def test_discussion_actions_are_refused(self):
        self.body['scenes'][0]['actions'].append({'id': 'talk', 'type': 'discussion', 'topic': 'x', 'prompt': 'y', 'agentId': 'a'})
        issues = [i for i in check_classroom(self.body) if i['code'] == 'discussion_not_allowed']
        self.assertEqual([(i['gate'], i['severity'], i['scene'], i['detail']) for i in issues], [('G3', 'error', 1, 'talk: write it as a teacher line such as 小满问：…')])

    def test_voices(self):
        agent = self.body['stage']['generatedAgentConfigs'][0]
        agent['voiceConfig'] = {}
        self.assertIn('voice_missing', codes(check_classroom(self.body)))
        agent['voiceConfig']['voiceId'] = 'Cherry'
        self.assertIn('voice_gender_mismatch', codes(check_classroom(self.body, roster={'Teacher': 'male'})))
        self.assertIn('roster_agent_missing', codes(check_classroom(self.body, roster={})))

    def test_receipts(self):
        self.receipt.update(bodySha256='wrong', ok=False, viewports=[])
        self.assertTrue({'audit_receipt_stale', 'audit_receipt_missing_viewport'} <= codes(check_classroom(self.body, receipt=self.receipt)))
        self.verification.update(bodySha256='wrong', speechChecked=2, questionsChecked=0, disagreements=['wrong'])
        self.assertTrue({'verification_receipt_stale', 'verification_disagreements', 'verification_incomplete'} <= codes(check_classroom(self.body, verification=self.verification)))

    def test_cli_require_all_and_json(self):
        result = subprocess.run([sys.executable, '-B', '-m', 'courseware.tools.check', '--body', str(SAMPLE), '--require-all', '--json'], capture_output=True, text=True, check=False)
        self.assertEqual(1, result.returncode)
        self.assertTrue({'notes_missing', 'receipt_missing', 'verification_missing'} <= codes(json.loads(result.stdout)))


if __name__ == '__main__':
    unittest.main()
