from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.content.textbook_interactive_narration import interactive_cues
from courseware.tools.build import prepare
from courseware.tools.check import check_classroom
from courseware.tools.game_audio import verify_recordings
from courseware.tools.verify import build_requests


LESSON = Path(__file__).resolve().parents[1]
ROOT = LESSON.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class NumberOrderTest(unittest.TestCase):
    def test_official_scope_and_all_assets_in_companion(self):
        identity = read(LESSON / 'identity.json')
        notes = read(LESSON / 'official-notes.json')
        self.assertEqual(identity['editionId'], 'pep-math-g1-lower-2022-standard')
        self.assertEqual(identity['revisionId'], 'directory-6205d2037284e91f10b25edd')
        self.assertEqual(identity['nodeId'], '2f7b0931-670f-4664-af31-876f2693654e')
        self.assertEqual(identity['officialActivityId'], '2dcdc27a-6ac2-09b7-fea8-218dab100586')
        book = notes['officialTextbook']
        self.assertEqual(book['directTeachingPrintedPages'], [32])
        self.assertEqual(book['relatedPracticePrintedPages'], [35, 36])
        self.assertEqual(book['assetPages'], [37, 40, 41])
        self.assertEqual(len(book['pageProof']), 13)
        self.assertIn('印33～34', book['boundary'])
        sources = notes['sourceEvidence']
        for proof in [*book['pageProof'], sources['exactActivity'], *sources['officialIndex']]:
            path = ROOT / proof['path']
            self.assertEqual(path.stat().st_size, proof['bytes'])
            self.assertEqual(digest(path), proof['sha256'])
        for name in ('prepManifest', 'textbookPageManifest'):
            self.assertEqual(digest(ROOT / sources[name]), sources[name + 'Sha256'])
        manifest = ROOT / sources['prepManifest']
        hours = read(manifest)['classHours']
        self.assertEqual([row['id'] for row in hours], ['lesson_1'])
        counts = {'courseware': 28, 'teachingDesign': 3, 'learningTaskSheet': 2, 'afterClassExercise': 1}
        self.assertEqual(sum(counts.values()), sources['companionPageCount'])
        for kind, count in counts.items():
            pages = hours[0]['resources'][kind]['pages']
            self.assertEqual([row['page'] for row in pages], list(range(1, count + 1)))
            for proof in pages:
                path = manifest.parent / proof['path']
                self.assertEqual(path.stat().st_size, proof['bytes'])
                self.assertEqual(digest(path), proof['sha256'])

    def test_original_quiz_and_traceable_number_art(self):
        lesson = read(LESSON / 'lesson.json')
        notes = read(LESSON / 'official-notes.json')
        brief = read(LESSON / 'brief.json')
        self.assertEqual(brief['goals'], notes['objectives'])
        self.assertEqual(brief['officialNotesSha256'], digest(LESSON / 'official-notes.json'))
        self.assertEqual([row['key'] for row in brief['pageSequence']], [row['key'] for row in lesson['scenes']])
        self.assertEqual([(game['template'], game['version']) for game in brief['games']],
                         [('platformHop', 1), ('fallingTiles', 1)])
        assets = read(LESSON / 'asset-provenance.json')['assets']
        self.assertEqual(set(assets), set(lesson['images']))
        self.assertEqual(Counter(key for row in notes['factChecks'] for key in row['images']), Counter(assets.keys()))
        for row in notes['factChecks']:
            self.assertGreaterEqual(len({source['resource'] for source in row['sources']}), 2)
            for source in row['sources']:
                self.assertLessEqual(set(source['pageRefs']), set(notes['resources'][source['resource']]['pageRefs']))
        for key, row in assets.items():
            self.assertEqual(digest(LESSON / row['path']), row['sha256'], key)
            self.assertEqual(digest(LESSON / row['renderSource']), row['renderSourceSha256'], key)
        quiz = next(row['questions'] for row in lesson['scenes'] if row['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in quiz), {'a': 2, 'b': 2, 'c': 2})
        actual = [q['options'][q['answer'][0]]['visual']['image'] for q in quiz]
        self.assertEqual(actual, ['q-ticket-13', 'q-ticket-48', 'q-wrap-b', 'q-tens-c', 'q-ticket-82', 'q-ticket-25'])

    def test_standard_builder_and_local_g7_payload(self):
        notes = read(LESSON / 'official-notes.json')
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='number-order-test', now_ms=1)
            media = Path(workspace) / 'media'
            body = draft['body']
            issues = check_classroom(body, media, notes=notes, roster=draft['roster'],
                                     grade=1, teaching=True, require_play=True)
            self.assertEqual({issue['code'] for issue in issues}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid', 'play_receipt_missing',
            })
            self.assertFalse(any(issue['severity'] != 'error' for issue in issues), issues)
            cues = [interactive_cues(s['content']['html']) for s in body['scenes'] if s['type'] == 'interactive']
            self.assertEqual([len(group) for group in cues], [6, 8])
            self.assertIn('箭头向左。从八十八倒着数，每次少一。', [cue['text'] for cue in cues[0]])
            verify_recordings(body, before_voice=True)
            requests = build_requests(body, notes, media=media, teaching=True)
            teaching = next(request for request in requests if request['kind'] == 'teaching')
            self.assertEqual(len(teaching['items']), len(notes['objectives']) + 2)
