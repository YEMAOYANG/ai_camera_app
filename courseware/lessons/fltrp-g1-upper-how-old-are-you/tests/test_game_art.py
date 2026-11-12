from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import unittest

from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('age_game_art', ROOT / 'game_art.py')
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class AgeGameArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / 'asset-provenance.json').read_text(encoding='utf-8'))
        cls.assets = manifest['assets']
        cls.originals = manifest['imagegenOriginals']

    def asset(self, key):
        with Image.open(ROOT / self.assets[key]['path']) as image:
            return image.copy()

    def assert_registered(self, key, data):
        asset = self.assets[key]
        self.assertEqual(sha256(data).hexdigest(), asset['sha256'])
        self.assertEqual(len(data), asset['bytes'])
        self.assertEqual(data, (ROOT / asset['path']).read_bytes())

    def test_game_art_reproduces_from_four_accepted_masters(self):
        for source in (*ART.SOURCE_GROUPS, 'interview-game-actors-atlas-v1'):
            with self.subTest(source=source):
                original = self.originals[source]
                path = ROOT / original['path']
                self.assertEqual(sha256(path.read_bytes()).hexdigest(), original['sha256'])
                self.assertEqual(original['receipt']['embeddedImageSha256'], original['sha256'])
                self.assertEqual(sha256(original['prompt'].encode()).hexdigest(), original['promptSha256'])
                if source.endswith('-v1'):
                    self.assertNotIn(source, ART.SOURCE_GROUPS)
                    self.assertEqual(original['status'], 'reference_only_rejected_gift_ribbon')
                    continue
                with Image.open(path) as image:
                    for key in ART.SOURCE_GROUPS[source]:
                        rendered, crop = ART.source_art(key, image)
                        self.assertEqual(list(rendered.size), self.assets[key]['pixels'])
                        self.assertEqual(self.assets[key]['originalKey'], source)
                        if crop:
                            self.assertEqual(list(crop), self.assets[key]['crop'])
                            self.assertEqual(rendered.getchannel('A').getextrema(), (0, 255))
                        self.assert_registered(key, ART.png(rendered))
        for key, (backdrop, props) in ART.OPENINGS.items():
            inputs = {item: self.assets[item]['sha256'] for item in (backdrop, *props)}
            self.assertEqual(inputs, self.assets[key]['inputs'])
            self.assert_registered(key, ART.png(ART.opening_art(key, self.asset)))

    def test_guest_scarf_cut_preserves_tail_and_van_frames_align(self):
        with Image.open(ROOT / self.originals[ART.GUEST_ATLAS]['path']) as atlas:
            alpha = atlas.getchannel('A')
            for column in (512, 1024):
                self.assertLessEqual(alpha.crop((column, 0, column + 1, 1024)).getextrema()[1], 96)
            self.assertLessEqual(alpha.crop((0, 530, 1536, 531)).getextrema()[1], 96)
            self.assertGreater(alpha.crop((1024, 512, 1536, 530)).getextrema()[1], 96)
            self.assertGreater(self.assets['guest-scarf']['crop'][3], 521)
        van = self.asset('reporter-van').getchannel('A')
        loaded = self.asset('reporter-van-loaded').getchannel('A')
        self.assertEqual(van.size, loaded.size)
        difference = ImageStat.Stat(ImageChops.difference(van, loaded)).sum[0]
        self.assertLess(difference / ImageStat.Stat(van).sum[0], .03)

    def test_all_game_references_are_registered_under_each_page_budget(self):
        lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        counts = {'badge-marbles': 9, 'interview-dispatch': 17}
        for scene in (item for item in lesson['scenes'] if item['type'] == 'interactive'):
            script = (ROOT / 'pages' / (scene['page'] + '.js')).read_text(encoding='utf-8')
            keys = {scene['startImage'], *re.findall(r'__IMG:([^_]+)__', script)}
            self.assertEqual(len(keys), counts.pop(scene['key']))
            total = 0
            for key in keys:
                self.assertEqual(lesson['images'][key]['file'], self.assets[key]['path'])
                path = ROOT / self.assets[key]['path']
                total += path.stat().st_size
            self.assertLess(total, 3_000_000)
        self.assertEqual(counts, {})
