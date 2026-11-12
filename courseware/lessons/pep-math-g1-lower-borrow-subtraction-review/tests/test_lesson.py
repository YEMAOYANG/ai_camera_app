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


LESSON = Path(__file__).resolve().parents[1]
ROOT = LESSON.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class BorrowSubtractionReviewTest(unittest.TestCase):
    def test_official_scope_and_all_companion_pages(self):
        notes = read(LESSON / 'official-notes.json')
        identity = read(LESSON / 'identity.json')
        self.assertEqual(identity['editionId'], 'pep-math-g1-lower-2022-standard')
        self.assertEqual(identity['revisionId'], 'directory-6205d2037284e91f10b25edd')
        self.assertEqual(identity['nodeId'], '080af136-a527-42a5-8367-b6855c2b2935')
        self.assertEqual(identity['officialActivityId'], '0c2c7bd6-2068-0312-c903-67732615ffe7')
        textbook = notes['officialTextbook']
        self.assertEqual(textbook['directTeachingPrintedPages'], [20])
        self.assertEqual(textbook['assetPages'], [25, 26, 27])
        self.assertEqual(textbook['relatedPracticePrintedPages'], [21, 22])
        self.assertIn('印23', textbook['boundary'])
        for proof in textbook['pageProof']:
            path = ROOT / proof['path']
            self.assertEqual(path.stat().st_size, proof['bytes'])
            self.assertEqual(digest(path), proof['sha256'])
        sources = notes['sourceEvidence']
        for name in ('prepManifest', 'textbookPageManifest'):
            self.assertEqual(digest(ROOT / sources[name]), sources[name + 'Sha256'])
        activity = sources['exactActivity']
        self.assertEqual(digest(ROOT / activity['path']), activity['sha256'])
        manifest = ROOT / sources['prepManifest']
        pack = read(manifest)['classHours'][0]['resources']
        counts = {'courseware': 25, 'teachingDesign': 3, 'learningTaskSheet': 2, 'afterClassExercise': 1}
        self.assertEqual(sum(counts.values()), sources['companionPageCount'])
        for name, count in counts.items():
            pages = pack[name]['pages']
            self.assertEqual([p['page'] for p in pages], list(range(1, count + 1)))
            for record in pages:
                path = manifest.parent / record['path']
                self.assertEqual(path.stat().st_size, record['bytes'])
                self.assertEqual(digest(path), record['sha256'])

    def test_original_quiz_and_traced_art(self):
        lesson = read(LESSON / 'lesson.json')
        brief = read(LESSON / 'brief.json')
        notes = read(LESSON / 'official-notes.json')
        self.assertEqual(brief['goals'], notes['objectives'])
        self.assertEqual(brief['officialNotesSha256'], digest(LESSON / 'official-notes.json'))
        self.assertEqual([p['key'] for p in brief['pageSequence']], [s['key'] for s in lesson['scenes']])
        self.assertEqual([(g['template'], g['version']) for g in brief['games']],
                         [('platformHop', 1), ('sortingDepot', 1)])
        provenance = read(LESSON / 'asset-provenance.json')
        for receipt in provenance['atlasReceipts'].values():
            self.assertEqual(digest(LESSON / receipt['path']), receipt['sha256'])
        art = provenance['assets']
        self.assertEqual({key for key, row in art.items() if row['usedBy']}, set(lesson['images']))
        self.assertEqual({key for row in notes['factChecks'] for key in row['images']}, set(art))
        for row in notes['factChecks']:
            self.assertGreaterEqual(len({source['resource'] for source in row['sources']}), 2)
            for source in row['sources']:
                self.assertLessEqual(set(source['pageRefs']), set(notes['resources'][source['resource']]['pageRefs']))
        for key, row in art.items():
            self.assertEqual(digest(LESSON / row['path']), row['sha256'], key)
            if 'generatedSource' in row:
                self.assertEqual(digest(LESSON / row['generatedSource']), row['generatedSourceSha256'], key)
            else:
                self.assertEqual(digest(LESSON / row['renderSource']), row['renderSourceSha256'], key)
                self.assertEqual(row['inputs'], {dep: art[dep]['sha256'] for dep in row['inputs']})
        questions = next(s['questions'] for s in lesson['scenes'] if s['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in questions), {'a': 2, 'b': 2, 'c': 2})
        self.assertEqual(questions[1]['visual']['image'], 'q-col-stem')
        self.assertEqual(questions[-1]['options']['a']['visual']['image'], 'q-line-a')

    def test_regular_builder_reaches_prevoice_boundary(self):
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='borrow-subtraction-review-test', now_ms=1)
            body = draft['body']
            issues = check_classroom(body, Path(workspace) / 'media', notes=read(LESSON / 'official-notes.json'),
                                     roster=draft['roster'], grade=1, teaching=True, require_play=True)
            self.assertEqual({issue['code'] for issue in issues if issue['severity'] == 'error'}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid', 'play_receipt_missing',
            })
            self.assertNotIn('media_unreferenced', {issue['code'] for issue in issues})
            self.assertFalse(any(issue['severity'] == 'warn' for issue in issues), issues)
            games = [interactive_cues(s['content']['html']) for s in body['scenes'] if s['type'] == 'interactive']
            self.assertEqual([len(cues) for cues in games], [6, 6])
            self.assertEqual(games[0][0]['text'], '同一列往下，减数八不变，原数每次加一。')
            self.assertEqual(games[1][0]['text'], '看总量和已知部分，再算还缺多少。')
            verify_recordings(body, before_voice=True)
