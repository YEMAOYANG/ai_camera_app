from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import unittest

from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('birthday_game_art', ROOT / 'game_art.py')
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class BirthdayGameArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ROOT / 'asset-provenance.json').read_text(encoding='utf-8'))
        cls.assets = manifest['assets']
        cls.originals = manifest['imagegenOriginals']

    def asset(self, key):
        with Image.open(ROOT / self.assets[key]['path']) as image:
            return image.copy()

    def assert_registered(self, key, image):
        record = self.assets[key]
        data = ART.png(image)
        self.assertEqual(data, (ROOT / record['path']).read_bytes())
        self.assertEqual(sha256(data).hexdigest(), record['sha256'])
        self.assertEqual(list(image.size), record['pixels'])

    def test_accepted_originals_reproduce_game_sprites_and_opening_cards(self):
        self.assertNotIn('workshop-gift-atlas-v1', self.originals)
        self.assertEqual(self.originals['workshop-gift-atlas']['referenceOnly']['status'], 'reference_only_opaque_panels')
        for source in (*ART.ATLAS_LAYOUTS, *ART.BACKDROPS):
            with self.subTest(source=source):
                original = self.originals[source]
                path = ROOT / original['path']
                self.assertEqual(sha256(path.read_bytes()).hexdigest(), original['sha256'])
                self.assertEqual(original['receipt']['embeddedImageSha256'], original['sha256'])
                with Image.open(path) as image:
                    if source in ART.BACKDROPS:
                        self.assert_registered(source, ART.backdrop_art(image))
                        continue
                    for key in ART.ATLAS_LAYOUTS[source][2]:
                        rendered, cell, crop = ART.sprite_art(source, key, image)
                        self.assertEqual(list(cell), self.assets[key]['atlasCell'])
                        self.assertEqual(list(crop), self.assets[key]['cropInIsolatedCell'])
                        self.assertEqual(rendered.getchannel('A').getextrema(), (0, 255))
                        self.assert_registered(key, rendered)
        for key, (background, props) in ART.OPENINGS.items():
            with self.subTest(opening=key):
                expected_inputs = {item: self.assets[item]['sha256'] for item in (background, *props)}
                self.assertEqual(expected_inputs, self.assets[key]['inputs'])
                self.assert_registered(key, ART.opening_art(key, self.asset))

    def test_vehicle_chassis_align_before_the_added_bubble(self):
        for first, second, width in (('boat-idle', 'boat-blow', 213), ('maze-rover', 'maze-bubble', 200)):
            with self.subTest(vehicle=first):
                idle, active = [self.asset(key).getchannel('A') for key in (first, second)]
                self.assertEqual(idle.size, active.size)
                region = (0, 0, width, idle.height)
                chassis, same_region = idle.crop(region), active.crop(region)
                difference = ImageStat.Stat(ImageChops.difference(chassis, same_region)).sum[0]
                self.assertLess(difference / ImageStat.Stat(chassis).sum[0], .02)

    def test_games_reference_only_registered_pngs_and_fit_the_picture_budget(self):
        lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        counts = {'gift-boat': 10, 'party-maze': 9}
        for scene in (item for item in lesson['scenes'] if item['type'] == 'interactive'):
            script = (ROOT / 'pages' / (scene['page'] + '.js')).read_text(encoding='utf-8')
            keys = {scene['startImage'], *re.findall(r'__IMG:([^_]+)__', script)}
            self.assertEqual(len(keys), counts.pop(scene['key']))
            size = sum((ROOT / self.assets[key]['path']).stat().st_size for key in keys)
            self.assertLess(size, 3_000_000)
        self.assertEqual(counts, {})
