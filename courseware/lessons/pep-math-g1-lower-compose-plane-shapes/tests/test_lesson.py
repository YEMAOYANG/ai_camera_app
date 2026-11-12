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
ROOT = LESSON.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class PlaneShapeCompositionTest(unittest.TestCase):
    def test_official_scope_and_all_companion_pages(self):
        notes = read(LESSON / 'official-notes.json')
        identity = read(LESSON / 'identity.json')
        self.assertEqual(identity['editionId'], 'pep-math-g1-lower-2022-standard')
        self.assertEqual(identity['revisionId'], 'directory-6205d2037284e91f10b25edd')
        self.assertEqual(identity['nodeId'], '43c58aab-3f26-4ee6-b49d-29086a5ff85f')
        self.assertEqual(identity['officialActivityId'], 'a0cc7c58-08ee-a303-9c6b-319ed1004377')
        textbook = notes['officialTextbook']
        self.assertEqual(textbook['directTeachingPrintedPages'], [3])
        self.assertEqual(textbook['assetPages'], [8])
        self.assertEqual(textbook['relatedPracticePrintedPages'], [7])
        self.assertIn('印4例3七巧板是独立解决问题', textbook['boundary'])
        for proof in textbook['pageProof']:
            path = ROOT / proof['path']
            self.assertEqual(path.stat().st_size, proof['bytes'])
            self.assertEqual(digest(path), proof['sha256'])
        sources = notes['sourceEvidence']
        for name in ('prepManifest', 'textbookPageManifest'):
            self.assertEqual(digest(ROOT / sources[name]), sources[name + 'Sha256'])
        manifest = ROOT / sources['prepManifest']
        pack = read(manifest)['classHours'][0]['resources']
        counts = {'courseware': 35, 'teachingDesign': 5, 'learningTaskSheet': 2, 'afterClassExercise': 1}
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
                         [('shapeBridge', 1), ('magnetMarbles', 1)])
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
        self.assertEqual(questions[2]['visual']['image'], 'q-diag-plan')
        self.assertEqual(questions[-1]['visual']['image'], 'q-circle-plan')
        self.assertEqual(questions[-1]['options']['a']['visual']['image'], 'q-circle-fit')

    def test_regular_builder_reaches_prevoice_boundary(self):
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='plane-composition-test', now_ms=1)
            body = draft['body']
            issues = check_classroom(body, Path(workspace) / 'media', notes=read(LESSON / 'official-notes.json'),
                                     roster=draft['roster'], grade=1, teaching=True, require_play=True)
            self.assertEqual({issue['code'] for issue in issues if issue['severity'] == 'error'}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid', 'play_receipt_missing',
            })
            self.assertNotIn('media_unreferenced', {issue['code'] for issue in issues})
            verify_recordings(body, before_voice=True)
