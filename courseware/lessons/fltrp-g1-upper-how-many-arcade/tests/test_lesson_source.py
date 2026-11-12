import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom


SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('quantity_compositions', SOURCE / 'quantity_compositions.py')
COMPOSITIONS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPOSITIONS)
BOAT_INK = (35, 103, 151, 255)
SHELL_INK = (185, 74, 52, 255)


def make_test_media(root):
    """Draw tiny counting fixtures to exercise the compositor, never the shipped art."""
    root.mkdir()
    for name, color in [('wooden-boat-single', BOAT_INK), ('scallop-shell-single', SHELL_INK)]:
        sprite = Image.new('RGBA', (34, 34))
        sprite.paste(color, (1, 1, 33, 33))
        sprite.save(root / f'{name}.png')
    Image.new('RGB', (800, 350), '#abd9c8').save(root / 'harbor-backdrop.png')
    return COMPOSITIONS.compositions(root)


def horizontal_objects(image, y, color):
    pixels = image.load()
    return sum(pixels[x, y] == color and (x == 0 or pixels[x - 1, y] != color)
               for x in range(image.width))


class LessonSourceTests(unittest.TestCase):
    def test_compiled_non_game_source_and_quiz_match_the_brief(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'lesson'
            (source / 'assets').mkdir(parents=True)
            non_game = json.loads((SOURCE / 'lesson.json').read_text(encoding='utf-8'))
            non_game['scenes'] = [s for s in non_game['scenes'] if s['type'] != 'interactive']
            fixtures = make_test_media(root / 'art-fixture')
            non_game['images'] = {key: item for key, item in non_game['images'].items()
                                  if key in fixtures or 'glyph' in item}
            (source / 'lesson.json').write_text(json.dumps(non_game), encoding='utf-8')
            for key, image in fixtures.items():
                image.save(source / 'assets' / f'{key}.png')

            draft = prepare(source, root / 'build', stage_id='how-many-offline-source-test', now_ms=0)
            notes = json.loads((SOURCE / 'official-notes.json').read_text(encoding='utf-8'))
            brief = json.loads((SOURCE / 'brief.json').read_text(encoding='utf-8'))
            self.assertTrue(brief['goals'])
            self.assertEqual(brief['goals'], notes['objectives'])
            body = draft['body']
            issues = check_classroom(body, notes=notes, roster=draft['roster'], grade=1, teaching=True)
            errors = [i for i in issues if i['severity'] == 'error' and i['code'] not in {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing',
            }]
            self.assertEqual(errors, [])
            self.assertEqual([s['outlineId'] for s in body['scenes']],
                             [s['key'] for s in brief['pages'] if s['type'] != 'interactive'])
            self.assertEqual(body['scenes'][-1]['outlineId'], 'harbor-recap')
            quiz = next(s['content']['questions'] for s in body['scenes'] if s['type'] == 'quiz')
            self.assertEqual(set(draft['questionAudio']), {q['id'] for q in quiz})
            source_quiz = next(s['questions'] for s in json.loads((SOURCE / 'lesson.json').read_text())['scenes']
                               if s['type'] == 'quiz')
            for q, plan in zip(source_quiz, brief['quiz'], strict=True):
                self.assertEqual(q['id'], plan['id'])
                self.assertEqual(q['skill'], plan['skill'])
                self.assertEqual(q['answer'], [plan['answer']])
                option_counts = [int(option['visual']['image'].split('-')[-1]) for option in q['options'].values()]
                self.assertEqual(option_counts, plan['optionQuantities'])
                self.assertEqual(option_counts['abc'.index(q['answer'][0])], plan['correctQuantity'])
                if 'visual' in q:
                    self.assertEqual(q['visual']['image'], f"shells-{plan['correctQuantity']}")

    def test_generated_sprite_is_counted_once_per_visible_position(self):
        with tempfile.TemporaryDirectory() as directory:
            images = make_test_media(Path(directory) / 'art-fixture')
            for key, expected in [('boats-one-four', range(1, 5)), ('boats-five-seven', range(5, 8)),
                                  ('boats-eight-ten', range(8, 11))]:
                image = images[key]
                row = image.height // len(expected)
                actual = [horizontal_objects(image, row * i + row // 2, BOAT_INK) for i in range(len(expected))]
                self.assertEqual(actual, list(expected))
            for key in ('four-boats', 'four-boats-tagged'):
                colors = {color: count for count, color in images[key].getcolors(50_000)}
                self.assertEqual(colors[BOAT_INK], 4 * 100 * 100)
            self.assertEqual(horizontal_objects(images['six-boats-line'], 157, BOAT_INK), 6)
            self.assertEqual([horizontal_objects(images['six-boats-pairs'], y, BOAT_INK) for y in (57, 157, 257)],
                             [2, 2, 2])
            for n in range(4, 11):
                colors = {color: count for count, color in images[f'shells-{n}'].getcolors(500)}
                self.assertEqual(colors[SHELL_INK], n * 71 * 71)

    def test_opaque_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wooden-boat-single.png'
            Image.new('RGBA', (34, 34), BOAT_INK).save(path)
            with self.assertRaisesRegex(ValueError, 'transparent background'):
                COMPOSITIONS._sprite(path)

    def test_near_opaque_sprite_ignores_invisible_border_noise_for_sizing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scallop-shell-single.png'
            sprite = Image.new('RGBA', (36, 36))
            sprite.paste((185, 74, 52, 254), (3, 4, 32, 33))
            sprite.putpixel((0, 0), (185, 74, 52, 1))
            sprite.save(path)
            result = COMPOSITIONS._sprite(path)
            self.assertEqual(result.size, (29, 29))
            self.assertEqual(result.getpixel((0, 0))[3], 254)
