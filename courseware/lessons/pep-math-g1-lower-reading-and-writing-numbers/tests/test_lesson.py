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


class ReadingAndWritingNumbersTest(unittest.TestCase):
    def test_exact_textbook_and_all_companion_pages(self):
        notes = read(LESSON / 'official-notes.json')
        identity = read(LESSON / 'identity.json')
        self.assertEqual(identity['editionId'], 'pep-math-g1-lower-2022-standard')
        self.assertEqual(identity['revisionId'], 'directory-6205d2037284e91f10b25edd')
        self.assertEqual(identity['nodeId'], 'e0fe1ec3-dc6a-4da3-8f94-d868461a40c0')
        self.assertEqual(identity['officialActivityId'], 'f329c604-4fdb-a2c1-400e-5448cde940db')
        book = notes['officialTextbook']
        self.assertEqual(book['directTeachingPrintedPages'], [26])
        self.assertEqual(book['relatedPracticePrintedPages'], [27])
        self.assertEqual(book['assetPages'], [31, 32])
        self.assertIn('印28', book['boundary'])
        for proof in book['pageProof']:
            path = ROOT / proof['path']
            self.assertEqual(path.stat().st_size, proof['bytes'])
            self.assertEqual(digest(path), proof['sha256'])
        sources = notes['sourceEvidence']
        for name in ('prepManifest', 'textbookPageManifest'):
            self.assertEqual(digest(ROOT / sources[name]), sources[name + 'Sha256'])
        for name in ('exactActivity', 'materialActivityIndex'):
            proof = sources[name]
            self.assertEqual(digest(ROOT / proof['path']), proof['sha256'])
        self.assertEqual(sources['materialActivityIndex']['activityCount'], 43)
        pack_path = ROOT / sources['prepManifest']
        hours = read(pack_path)['classHours']
        self.assertEqual([hour['id'] for hour in hours], ['lesson_1'])
        resources = hours[0]['resources']
        counts = {'courseware': 30, 'teachingDesign': 5, 'learningTaskSheet': 3, 'afterClassExercise': 1}
        self.assertEqual(sum(counts.values()), sources['companionPageCount'])
        for kind, count in counts.items():
            pages = resources[kind]['pages']
            self.assertEqual([p['page'] for p in pages], list(range(1, count + 1)))
            for proof in pages:
                path = pack_path.parent / proof['path']
                self.assertEqual(path.stat().st_size, proof['bytes'])
                self.assertEqual(digest(path), proof['sha256'])

    def test_original_questions_and_traced_place_value_art(self):
        lesson = read(LESSON / 'lesson.json')
        brief = read(LESSON / 'brief.json')
        notes = read(LESSON / 'official-notes.json')
        self.assertEqual(brief['goals'], notes['objectives'])
        self.assertEqual(brief['officialNotesSha256'], digest(LESSON / 'official-notes.json'))
        self.assertEqual([p['key'] for p in brief['pageSequence']], [s['key'] for s in lesson['scenes']])
        self.assertEqual([(g['template'], g['version']) for g in brief['games']],
                         [('bubbleMaze', 1), ('listenDelivery', 1)])
        provenance = read(LESSON / 'asset-provenance.json')
        for receipt in provenance['atlasReceipts'].values():
            self.assertEqual(digest(LESSON / receipt['path']), receipt['sha256'])
        art = provenance['assets']
        self.assertEqual({key for key, row in art.items() if row['usedBy']}, set(lesson['images']))
        self.assertEqual({key for row in notes['factChecks'] for key in row['images']}, set(art))
        for row in notes['factChecks']:
            self.assertGreaterEqual(len({source['resource'] for source in row['sources']}), 2)
            for source in row['sources']:
                refs = notes['resources'][source['resource']]['pageRefs']
                self.assertLessEqual(set(source['pageRefs']), set(refs))
        for key, row in art.items():
            self.assertEqual(digest(LESSON / row['path']), row['sha256'], key)
            if 'generatedSource' in row:
                self.assertEqual(digest(LESSON / row['generatedSource']), row['generatedSourceSha256'], key)
            else:
                self.assertEqual(digest(LESSON / row['renderSource']), row['renderSourceSha256'], key)
                self.assertEqual(row['inputs'], {dep: art[dep]['sha256'] for dep in row['inputs']})
        questions = next(s['questions'] for s in lesson['scenes'] if s['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in questions), {'a': 2, 'b': 2, 'c': 2})
        for q in questions:
            if q['id'] not in ('same-digit-different-value', 'listen-to-number'):
                stem = q['visual']['image']
                answer = q['options'][q['answer'][0]]['visual']['image']
                self.assertEqual(art[stem]['quantity'], art[answer]['quantity'])

    def test_regular_builder_stops_only_at_pending_audio_and_play(self):
        notes = read(LESSON / 'official-notes.json')
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='reading-and-writing-numbers-test', now_ms=1)
            media = Path(workspace) / 'media'
            body = draft['body']
            issues = check_classroom(body, media, notes=notes, roster=draft['roster'],
                                     grade=1, teaching=True, require_play=True)
            self.assertEqual({i['code'] for i in issues}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid', 'play_receipt_missing',
            })
            self.assertFalse(any(i['severity'] != 'error' for i in issues), issues)
            games = [interactive_cues(s['content']['html']) for s in body['scenes'] if s['type'] == 'interactive']
            self.assertEqual([len(cues) for cues in games], [14, 15])
            self.assertIn('三十一。找和三十一相同的珠图。', [cue['text'] for cue in games[1]])
            verify_recordings(body, before_voice=True)
            requests = build_requests(body, notes, media=media, teaching=True)
            teaching = next(request for request in requests if request['kind'] == 'teaching')
            self.assertEqual(len(teaching['items']), len(notes['objectives']) + 2)
