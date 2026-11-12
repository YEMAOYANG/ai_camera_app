from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom
from courseware.tools.game_audio import verify_recordings


LESSON=Path(__file__).resolve().parents[1]
ROOT=LESSON.parents[2]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class SolidShapeReviewTest(unittest.TestCase):
    def test_edition_exact_scope_and_all_companions(self):
        notes=read(LESSON/'official-notes.json')
        identity=read(LESSON/'identity.json')
        self.assertEqual(identity['nodeId'],'204c0d91-5317-458b-86fc-6f0df3577f66')
        self.assertEqual(identity['officialActivityId'],'e7c2de3c-b0c7-d058-61ed-f0cd1032f669')
        self.assertEqual(notes['officialTextbook']['printedPages'],[105])
        self.assertEqual(notes['officialTextbook']['ebookPages'],[110])
        self.assertIn('下半',notes['officialTextbook']['boundary'])
        for proof in notes['officialTextbook']['pageProof']:
            self.assertEqual(digest(ROOT/proof['path']),proof['sha256'])
        row=notes['sourceEvidence']['prepManifest']
        manifest=ROOT/row['path']
        self.assertEqual(digest(manifest),row['sha256'])
        pack=read(manifest)['classHours'][0]['resources']
        for name,count in {'teachingDesign':4,'courseware':19,'learningTaskSheet':2,'afterClassExercise':1}.items():
            pages=pack[name]['pages']
            self.assertEqual(len(pages),count)
            self.assertEqual(notes['resources'][name]['officialPreviewPages'],list(range(1,count+1)))
            for record in pages:
                path=manifest.parent/record['path']
                self.assertEqual(path.stat().st_size,record['bytes'])
                self.assertEqual(digest(path),record['sha256'])

    def test_quiz_and_registered_solid_art(self):
        lesson=read(LESSON/'lesson.json')
        brief=read(LESSON/'brief.json')
        notes=read(LESSON/'official-notes.json')
        self.assertEqual(brief['goals'],notes['objectives'])
        self.assertEqual(brief['officialNotesSha256'],digest(LESSON/'official-notes.json'))
        self.assertEqual([p['key'] for p in brief['pageSequence']],[s['key'] for s in lesson['scenes']])
        self.assertEqual(sum(s['type']=='interactive' for s in lesson['scenes']),2)
        art=read(LESSON/'asset-provenance.json')['assets']
        self.assertEqual({key for key,row in art.items() if row['usedBy']},set(lesson['images']))
        self.assertEqual({key for f in notes['factChecks'] for key in f['images']},set(art))
        for key,entry in art.items():
            self.assertEqual(digest(LESSON/entry['path']),entry['sha256'],key)
            if 'sourceLessonAsset' in entry:
                self.assertEqual(digest(ROOT/entry['sourceLessonAsset']),entry['sha256'],key)
                self.assertEqual(digest(ROOT/entry['sourceReceipt']),entry['sourceReceiptSha256'],key)
            elif 'generatedSource' in entry:
                self.assertEqual(digest(LESSON/entry['generatedSource']),entry['generatedSourceSha256'],key)
            else:
                self.assertEqual(digest(LESSON/entry['renderSource']),entry['renderSourceSha256'],key)
                self.assertEqual(entry['inputs'],{dep:art[dep]['sha256'] for dep in entry['inputs']})
        quiz=next(s for s in lesson['scenes'] if s['type']=='quiz')
        self.assertEqual(Counter(q['answer'][0] for q in quiz['questions']),{'a':2,'b':2,'c':2})
        self.assertEqual(quiz['questions'][-1]['visual']['image'],'q-gap-plan')
        self.assertEqual(quiz['questions'][-1]['options']['a']['visual']['image'],'q-fit-piece')

    def test_regular_builder_leaves_only_pending_prevoice_requirements(self):
        with TemporaryDirectory() as workspace:
            draft=prepare(LESSON,workspace,stage_id='solid-review-test',now_ms=1)
            body=draft['body']
            issues=check_classroom(body,Path(workspace)/'media',notes=read(LESSON/'official-notes.json'),
                                   roster=draft['roster'],grade=1,teaching=True,require_play=True)
            self.assertEqual({item['code'] for item in issues if item['severity']=='error'},{
                'speech_audio_missing','quiz_questionAudioUrl_missing','game_audio_invalid','play_receipt_missing',
            })
            self.assertNotIn('media_unreferenced',{item['code'] for item in issues})
            verify_recordings(body,before_voice=True)
