from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('age_lesson_art', ROOT / 'lesson_art.py')
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class AgeLessonArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        cls.manifest = json.loads((ROOT / 'asset-provenance.json').read_text(encoding='utf-8'))

    def test_final_illustrations_reproduce_from_registered_masters(self):
        assets = self.manifest['assets'] | self.manifest['sourceOnlyAssets']
        for source, keys in ART.SOURCE_GROUPS.items():
            original = self.manifest['imagegenOriginals'][source]
            path = ROOT / original['path']
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), original['sha256'])
            with Image.open(path) as image:
                if source == ART.GUESTS:
                    for x in (724, 1448):
                        self.assertEqual(image.getchannel('A').crop((x, 0, x + 1, 724)).getextrema(), (0, 0))
                for key in keys:
                    with self.subTest(key=key):
                        rendered, crop = ART.source_art(source, key, image)
                        asset = assets[key]
                        self.assertEqual(asset['originalKey'], source)
                        self.assertEqual(asset.get('crop'), list(crop) if crop else None)
                        self.assertEqual(list(rendered.size), asset['pixels'])
                        with io.BytesIO() as stream:
                            rendered.save(stream, 'PNG', optimize=True)
                            data = stream.getvalue()
                        self.assertEqual(data, (ROOT / asset['path']).read_bytes())
                        self.assertEqual(sha256(data).hexdigest(), asset['sha256'])

    def test_asking_and_answering_use_only_their_numeric_age_card(self):
        quiz = next(scene for scene in self.lesson['scenes'] if scene['type'] == 'quiz')
        assets = self.manifest['assets']
        for question, answer, age in ((quiz['questions'][0], 'b', 7), (quiz['questions'][5], 'a', 8)):
            self.assertEqual(question['answer'], [answer])
            for choice, option in question['options'].items():
                asset = assets[option['visual']['image']]
                self.assertEqual(asset['pixels'], [320, 320])
                if choice == answer:
                    self.assertEqual(asset['deterministicAgeMark']['age'], age)
                else:
                    self.assertNotIn('deterministicAgeMark', asset)
        pictures = {option['visual']['image'] for question in quiz['questions'] for option in question['options'].values()}
        self.assertLess(sum((ROOT / assets[key]['path']).stat().st_size for key in pictures), 3_000_000)
        self.assertEqual(set(assets), set(self.lesson['images']))

    def test_speaker_switch_uses_separate_portraits_of_the_same_original_scene(self):
        scene = next(item for item in self.lesson['scenes'] if item['key'] == 'listen-to-the-speaker')
        assets = self.manifest['assets']
        keys = [scene['data']['left_picture'], scene['data']['right_picture']]
        self.assertEqual(keys, ['speaker-round-cap', 'speaker-paint-apron'])
        source = self.manifest['sourceOnlyAssets']['same-age-pair']
        self.assertNotIn('same-age-pair', self.lesson['images'])
        with Image.open(ROOT / source['path']) as original:
            for key in keys:
                asset = assets[key]
                self.assertEqual(asset['inputSha256'], source['sha256'])
                rendered = original.crop(asset['crop'])
                with Image.open(ROOT / asset['path']) as portrait:
                    self.assertEqual(rendered.size, portrait.size)
                    self.assertEqual(rendered.tobytes(), portrait.tobytes())
        script = scene['script']
        self.assertIn('猜', script[0]['say'])
        self.assertEqual([beat['spotlight'] for beat in script if 'spotlight' in beat],
                         ['left-picture', 'right-picture', 'right-body', 'left-picture', 'right-picture'])
        self.assertIn("I'm seven.", script[2]['say'])
        self.assertIn("I'm ten.", script[4]['say'])
        self.assertIn('自己的年龄', script[7]['say'])
        self.assertIn("I'm six, too.", script[12]['say'])
