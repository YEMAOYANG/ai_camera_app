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


class CompareNumbersTo100Test(unittest.TestCase):
    def test_official_scope_and_all_assets_in_companion(self):
        identity = read(LESSON / 'identity.json')
        notes = read(LESSON / 'official-notes.json')
        self.assertEqual(identity['editionId'], 'pep-math-g1-lower-2022-standard')
        self.assertEqual(identity['revisionId'], 'directory-6205d2037284e91f10b25edd')
        self.assertEqual(identity['nodeId'], 'ba1db695-94ad-4c0f-9faf-fff92c93f0b3')
        self.assertEqual(identity['officialActivityId'], 'e1c3ce66-ccd3-11f5-306d-d8b7585278fd')
        book = notes['officialTextbook']
        self.assertEqual(book['directTeachingPrintedPages'], [33])
        self.assertEqual(book['relatedPracticePrintedPages'], [36])
        self.assertEqual(book['assetPages'], [38, 41])
        self.assertEqual(len(book['pageProof']), 11)
        self.assertIn('印34/e39', book['boundary'])
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
        counts = {'courseware': 25, 'teachingDesign': 3, 'learningTaskSheet': 2, 'afterClassExercise': 1}
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
                         [('compareSnake', 1), ('sortingDepot', 1)])
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
        self.assertEqual(actual, ['q-stamps-b', 'q-magnets-a', 'sign-eq', 'sign-lt', 'q-order-a', 'q-digit-9'])

    def test_standard_builder_and_local_g7_payload(self):
        notes = read(LESSON / 'official-notes.json')
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='compare-numbers-to-100-test', now_ms=1)
            media = Path(workspace) / 'media'
            body = draft['body']
            issues = check_classroom(body, media, notes=notes, roster=draft['roster'],
                                     grade=1, teaching=True, require_play=True)
            self.assertEqual({issue['code'] for issue in issues}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid', 'play_receipt_missing',
            })
            self.assertFalse(any(issue['severity'] != 'error' for issue in issues), issues)
            cues = [interactive_cues(s['content']['html']) for s in body['scenes'] if s['type'] == 'interactive']
            self.assertEqual([len(group) for group in cues], [9, 6])
            self.assertIn('基准变成五十八。找一个等于它的数。', [cue['text'] for cue in cues[0]])
            verify_recordings(body, before_voice=True)
            requests = build_requests(body, notes, media=media, teaching=True)
            teaching = next(request for request in requests if request['kind'] == 'teaching')
            self.assertEqual(len(teaching['items']), len(notes['objectives']) + 2)
