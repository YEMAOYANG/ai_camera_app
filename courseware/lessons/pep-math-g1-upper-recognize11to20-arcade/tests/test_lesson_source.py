"""Check the authored slides and pictures without invoking a media provider."""

from collections import Counter
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from shutil import copyfile, copytree
from tempfile import TemporaryDirectory
import unittest

from PIL import Image, ImageColor

from backend.content.textbook_interactive_narration import interactive_cues
from courseware.tools import game_audio
from courseware.tools.build import prepare
from courseware.tools.check import check_classroom


LESSON = Path(__file__).resolve().parents[1]


def scan_runs(pixels, colors):
    runs = []
    for index, color in enumerate(pixels):
        if color in colors:
            if not runs or runs[-1][1] != index:
                runs.append([index, index + 1])
            else:
                runs[-1][1] += 1
    return runs


def scan_row(lesson, key, y, colors):
    with Image.open(lesson / 'assets' / f'{key}.png') as image:
        return scan_runs([image.getpixel((x, y)) for x in range(image.width)], colors)


def scan_column(lesson, key, x, colors):
    with Image.open(lesson / 'assets' / f'{key}.png') as image:
        return scan_runs([image.getpixel((x, y)) for y in range(42, 272)], colors)


class LessonSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generated PNGs are private media. Exercise the editable source even in a clean checkout.
        workspace = TemporaryDirectory()
        cls.addClassCleanup(workspace.cleanup)
        cls.source = Path(workspace.name)
        copyfile(LESSON / 'lesson.json', cls.source / 'lesson.json')
        copytree(LESSON / 'pages', cls.source / 'pages')
        spec = spec_from_file_location('draw_diagrams', LESSON / 'assets/draw_diagrams.py')
        drawings = module_from_spec(spec)
        spec.loader.exec_module(drawings)
        drawings.render(cls.source)
        cls.art = json.loads((LESSON / 'codex-image-receipts.json').read_text())['images']
        for record in cls.art:
            src = LESSON / record['asset']
            # A source-only checkout still exercises all config and compiler paths.
            # Separate tests with the actual local art verify its identity and readability.
            if not src.is_file():
                src = cls.source / 'assets/game-bundle.png'
            copyfile(src, cls.source / record['asset'])

    def test_offline_teaching_source_builds_without_release_receipts(self):
        notes = json.loads((LESSON / 'official-notes.json').read_text())
        brief = json.loads((LESSON / 'brief.json').read_text())
        with TemporaryDirectory() as folder:
            draft = prepare(self.source, folder, stage_id='recognize11to20-offline-test', now_ms=1)
            issues = check_classroom(draft['body'], Path(folder) / 'media', notes=notes,
                                     grade=1, teaching=True, roster=draft['roster'])
        # Missing recordings must stay visible as errors. A pre-media draft is not a release.
        self.assertEqual({issue['code'] for issue in issues if issue['severity'] == 'error'},
                         {'speech_audio_missing', 'quiz_questionAudioUrl_missing', 'game_audio_invalid'})
        game_audio.verify_recordings(draft['body'], before_voice=True)
        self.assertTrue(all(len(line['text']) <= 40 for line in draft['lines']))
        self.assertEqual(draft['body']['scenes'][-1]['outlineId'], 'bring-the-method-home')
        outline_ids = {scene['outlineId'] for scene in draft['body']['scenes']}
        self.assertEqual({page['key'] for page in brief['pages']}, outline_ids)
        interactive = [s for s in draft['body']['scenes'] if s['type'] == 'interactive']
        self.assertEqual([s['outlineId'] for s in interactive], ['packing', 'number-track'])
        teachers = {line['id'] for line in draft['lines'] if line['voice'] == 'Ethan'}
        source = json.loads((LESSON / 'lesson.json').read_text())
        references = {s['key']: s['gameAudio'] for s in source['scenes'] if s['type'] == 'interactive'}
        for s in interactive:
            states = [a['state'] for a in s['actions'] if a['type'] == 'widget_setState']
            self.assertEqual(states, [{'demo': True, 'level': 1, 'pause': True},
                                      {'demo': True, 'pause': False},
                                      {'demo': False, 'level': 1, 'pause': False}])
            cues = interactive_cues(s['content']['html'])
            ids = references[s['outlineId']]
            self.assertEqual({cue['id'] for cue in cues}, ids.keys())
            self.assertTrue(set(ids.values()) <= teachers)

    def test_quiz_solutions_use_real_picture_options(self):
        source = json.loads((LESSON / 'lesson.json').read_text())
        quiz = next(scene for scene in source['scenes'] if scene['type'] == 'quiz')
        labels = {
            'arcade-count-garden': '16', 'arcade-undo-box': '十二片散片',
            'arcade-read-eighteen': '左杆一颗，右杆八颗', 'arcade-fill-station': '18',
            'arcade-nearer-stop': '20', 'arcade-page-span': '4',
        }
        self.assertEqual({q['id'] for q in quiz['questions']}, labels.keys())
        positions = Counter()
        for question in quiz['questions']:
            options = question['options']
            self.assertEqual(len({option['visual']['image'] for option in options.values()}), 3)
            self.assertTrue(all(option['visual']['image'] in source['images'] for option in options.values()))
            [correct] = question['answer']
            self.assertEqual(options[correct]['label'], labels[question['id']])
            positions[correct] += 1
        self.assertEqual(positions, {'A': 2, 'B': 2, 'C': 2})

    def test_exchange_picture_conserves_twenty_rods(self):
        mint = {ImageColor.getrgb('#d4e4d7')}
        peach = {ImageColor.getrgb('#f4d6b5')}
        self.assertEqual(len(scan_row(self.source, 'rods-nineteen-arrival', 150, mint)), 10)
        self.assertEqual(len(scan_row(self.source, 'rods-nineteen-arrival', 150, peach)), 9)
        self.assertEqual(len(scan_row(self.source, 'rods-nineteen-arrival', 75, peach)), 1)
        grouped = scan_row(self.source, 'rods-twenty', 150, mint)
        self.assertEqual(len(grouped), 20)
        self.assertGreater(grouped[10][0] - grouped[9][1], 100)
        self.assertEqual(scan_row(self.source, 'rods-twenty', 150, peach), [])

    def test_place_value_and_equal_ticks_are_visible(self):
        tens = {ImageColor.getrgb('#306357')}
        ones = {ImageColor.getrgb('#ab4e2f')}
        self.assertEqual(len(scan_column(self.source, 'counter-twenty', 230, tens)), 2)
        self.assertEqual(scan_column(self.source, 'counter-twenty', 570, ones), [])
        self.assertEqual(len(scan_column(self.source, 'counter-eighteen', 570, ones)), 8)
        ticks = scan_row(self.source, 'line-zero-twenty', 132, ones | {ImageColor.getrgb('#203c35')})
        self.assertEqual(len(ticks), 21)
        self.assertEqual({b[0] - a[0] for a, b in zip(ticks, ticks[1:])}, {46})

    def test_locator_mark_and_unfilled_tick_are_visible(self):
        with Image.open(self.source / 'assets/line-locate-thirteen.png') as image:
            orange = ImageColor.getrgb('#ab4e2f')
            self.assertEqual(image.getpixel((653, 196)), orange)
            self.assertNotEqual(image.getpixel((607, 196)), orange)
        with Image.open(self.source / 'assets/line-gap-nineteen.png') as image:
            self.assertEqual(image.getpixel((636, 197)), ImageColor.getrgb('#306357'))
            self.assertEqual(image.getpixel((665, 197)), ImageColor.getrgb('#fff7e8'))

    def test_registered_diagrams_match_their_sources(self):
        provenance = json.loads((LESSON / 'asset-sources.json').read_text())
        registered = provenance['assets']
        source = json.loads((LESSON / 'lesson.json').read_text())
        art_paths = {record['asset'] for record in self.art}
        self.assertEqual(set(registered), {key for key, image in source['images'].items()
                                           if 'file' in image and image['file'] not in art_paths})
        self.assertEqual(sha256((LESSON / 'assets/draw_diagrams.py').read_bytes()).hexdigest(),
                         provenance['sourceSha256'])
        for asset in registered.values():
            path = self.source / asset['file']
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), asset['sha256'], path.name)
            with Image.open(path) as image:
                self.assertEqual(list(image.size), asset['size'], path.name)

    def test_local_game_art_retains_approved_provenance(self):
        self.assertEqual(len(self.art), 6)
        if not all((LESSON / record['asset']).is_file() for record in self.art):
            self.skipTest('The private imagegen PNGs are not present in this checkout')
        for record in self.art:
            self.assertEqual(record['source'], 'Codex built-in imagegen')
            self.assertEqual(sha256((LESSON / record['asset']).read_bytes()).hexdigest(), record['sha256'])
        for page in ('packing', 'number-track'):
            self.assertLess(sum(record['bytes'] for record in self.art if page in record['usedBy']), 3_000_000)
