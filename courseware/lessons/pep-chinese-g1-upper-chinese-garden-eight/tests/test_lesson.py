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
REPO = LESSON.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class ChineseGardenEightTest(unittest.TestCase):
    def test_official_print_and_four_class_hours(self):
        notes = read(LESSON / 'official-notes.json')
        brief = read(LESSON / 'brief.json')
        identity = read(LESSON / 'identity.json')
        self.assertEqual((identity['editionId'], identity['revisionId'], identity['nodeId']),
                         ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3', 'u8-l4'))
        self.assertEqual(notes['officialTextbook']['printedPages'], [101,102,103,104])
        self.assertEqual(notes['officialTextbook']['pdfPages'], [106,107,108,109])
        self.assertEqual(notes['objectives'], brief['goals'])
        self.assertEqual(digest(LESSON / 'official-notes.json'), brief['officialNotesSha256'])
        sources = notes['sourceEvidence']
        manifest = REPO / sources['prepManifest']
        self.assertEqual(digest(manifest), sources['prepManifestSha256'])
        totals = []
        for hour in read(manifest)['classHours']:
            pages = [page for source in hour['resources'].values() for page in source.get('pages', [])]
            for page in pages:
                proof = manifest.parent / page['path']
                self.assertEqual(proof.stat().st_size, page['bytes'])
                self.assertEqual(digest(proof), page['sha256'])
            totals.append(len(pages))
        self.assertEqual(totals, [44,40,21,24])

    def test_picture_quiz_and_editable_art_provenance(self):
        lesson = read(LESSON / 'lesson.json')
        notes = read(LESSON / 'official-notes.json')
        brief = read(LESSON / 'brief.json')
        self.assertEqual([item['key'] for item in brief['pageSequence']],
                         [item['key'] for item in lesson['scenes']])
        self.assertEqual(sum(item['type']=='interactive' for item in lesson['scenes']), 2)
        art = read(LESSON / 'asset-provenance.json')['assets']
        self.assertEqual({key for key, row in art.items() if row['usedBy']}, set(lesson['images']))
        self.assertEqual({key for row in notes['factChecks'] for key in row['images']}, set(art))
        for key, row in art.items():
            self.assertEqual(digest(LESSON / row['path']), row['sha256'], key)
            if 'generatedSource' in row:
                self.assertEqual(digest(LESSON / row['generatedSource']), row['generatedSourceSha256'], key)
            else:
                self.assertEqual(digest(LESSON / row['renderSource']), row['renderSourceSha256'], key)
                self.assertEqual(row['inputs'], {dep: art[dep]['sha256'] for dep in row['inputs']})

        quiz = next(item for item in lesson['scenes'] if item['type'] == 'quiz')
        self.assertEqual(Counter(item['answer'][0] for item in quiz['questions']), {'a':3,'b':3,'c':3})
        for item in quiz['questions']:
            options = {option['visual']['image'] for option in item['options'].values()}
            self.assertEqual(len(options), 3)
            self.assertTrue(options <= set(lesson['images']))
        self.assertEqual(quiz['questions'][0]['visual']['image'], 'character-early')
        self.assertEqual(quiz['questions'][1]['visual']['image'], 'character-bright')
        text = (LESSON / 'lesson.json').read_text()
        for borrowed_phrase in ('解落三秋','过江千尺','小孩小孩','糖瓜粘'):
            self.assertNotIn(borrowed_phrase,text)

    def test_standard_builder_leaves_only_prevoice_errors(self):
        with TemporaryDirectory() as work:
            built = prepare(LESSON, work, stage_id='chinese-garden-eight-test', now_ms=1)
            issues = check_classroom(built['body'], Path(work) / 'media',
                                     notes=read(LESSON / 'official-notes.json'), roster=built['roster'],
                                     grade=1, teaching=True, require_play=True)
            self.assertEqual({issue['code'] for issue in issues if issue['severity']=='error'}, {
                'speech_audio_missing','quiz_questionAudioUrl_missing','game_audio_invalid','play_receipt_missing',
            })
            self.assertNotIn('media_unreferenced', {issue['code'] for issue in issues})
            verify_recordings(built['body'], before_voice=True)
