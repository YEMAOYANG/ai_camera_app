from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('birthday_quiz_art', ROOT / 'quiz_art.py')
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class BirthdayQuizArtTests(unittest.TestCase):
    def test_registered_choices_reproduce_without_dividers(self):
        manifest = json.loads((ROOT / 'asset-provenance.json').read_text(encoding='utf-8'))
        for source, keys in ART.SOURCE_GROUPS.items():
            record = manifest['imagegenOriginals'][source]
            original = ROOT / record['path']
            self.assertEqual(sha256(original.read_bytes()).hexdigest(), record['sha256'])
            self.assertEqual(record['receipt']['embeddedImageSha256'], record['sha256'])
            with Image.open(original) as image:
                if source == ART.STATIONERY_ATLAS:
                    alpha = image.getchannel('A')
                    for x in (724, 1448):
                        self.assertEqual(alpha.crop((x, 0, x + 1, 724)).getextrema(), (0, 0))
                for key in keys:
                    with self.subTest(option=key):
                        rendered, box = ART.quiz_art(source, key, image)
                        asset = (manifest['sourceOnlyAssets']['quiz-welcome-giver-v1']
                                 if key == 'quiz-welcome-giver' else manifest['assets'][key])
                        self.assertEqual(rendered.size, (320, 320))
                        self.assertEqual((box[2] - box[0], box[3] - box[1]), (696, 696))
                        self.assertEqual(list(box), asset['crop'])
                        if key == 'quiz-welcome-giver':
                            self.assertEqual(box[2], 716)
                        with io.BytesIO() as stream:
                            rendered.save(stream, 'PNG', optimize=True)
                            data = stream.getvalue()
                        self.assertEqual(data, (ROOT / asset['path']).read_bytes())
                        self.assertEqual(sha256(data).hexdigest(), asset['sha256'])

    def test_handoff_choice_uses_single_new_master_and_keeps_the_other_options(self):
        lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        manifest = json.loads((ROOT / 'asset-provenance.json').read_text(encoding='utf-8'))
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        question = next(q for q in quiz['questions'] if q['id'] == 'welcome-after-thanks')
        self.assertEqual(question['answer'], ['a'])
        self.assertEqual([option['visual']['image'] for option in question['options'].values()],
                         ['quiz-welcome-giver', 'quiz-welcome-receiver', 'quiz-welcome-bystander'])
        asset = manifest['assets']['quiz-welcome-giver']
        record = manifest['imagegenOriginals'][asset['originalKey']]
        self.assertEqual(asset['path'], lesson['images']['quiz-welcome-giver']['file'])
        original = ROOT / record['path']
        self.assertEqual(sha256(original.read_bytes()).hexdigest(), record['sha256'])
        self.assertEqual(record['receipt']['embeddedImageSha256'], record['sha256'])
        for reference in record['referenceAssets']:
            self.assertEqual(sha256((ROOT / reference['path']).read_bytes()).hexdigest(), reference['sha256'])
        with Image.open(original) as image, io.BytesIO() as stream:
            image.resize((320, 320), Image.Resampling.LANCZOS).save(stream, 'PNG', optimize=True)
            data = stream.getvalue()
        self.assertEqual(data, (ROOT / asset['path']).read_bytes())
        self.assertEqual(sha256(data).hexdigest(), asset['sha256'])

    def test_full_picture_check_is_under_budget_with_equal_size_per_question(self):
        lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        seen = set()
        for question in quiz['questions']:
            sizes = set()
            for option in question['options'].values():
                key = option['visual']['image']
                path = ROOT / lesson['images'][key]['file']
                seen.add(path)
                with Image.open(path) as image:
                    sizes.add(image.size)
            self.assertEqual(len(sizes), 1)
        self.assertEqual(len(seen), 18)
        self.assertLess(sum(p.stat().st_size for p in seen), 3_000_000)
