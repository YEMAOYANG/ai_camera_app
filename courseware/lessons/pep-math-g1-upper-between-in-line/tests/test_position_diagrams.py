"""Verify the same endpoint rule in the pictures, quiz, and game data."""

from hashlib import sha256
import json
from pathlib import Path
import unittest


LESSON = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((LESSON / path).read_bytes())


def game_config(page, template):
    source = (LESSON / 'pages' / f'{page}.js').read_text(encoding='utf-8')
    return json.loads(source.split(f'K.game(K.gameTemplates.{template}(', 1)[1].removesuffix('));\n'))


class PositionDiagramsTest(unittest.TestCase):
    def setUp(self):
        self.lesson = load('lesson.json')
        self.diagrams = load('art-source/position-diagrams.json')['images']

    def test_quiz_has_one_image_with_the_correct_range_or_count(self):
        quiz = next(scene for scene in self.lesson['scenes'] if scene['type'] == 'quiz')
        extractors = {
            'queue-sixth': lambda image: image['rows'][0]['selected'],
            'stamp-interval': lambda image: image['rows'][0]['selected'],
            'adjacent-people': lambda image: len(image['positions']),
            'floor-check': lambda image: image['selected'],
            'exhibit-dots': lambda image: image['count'],
            'photos-inclusive': lambda image: image['rows'][0]['selected'],
        }
        for question in quiz['questions']:
            with self.subTest(question=question['id']):
                stem = self.diagrams[question['visual']['image']]
                context = stem['rows'][0] if stem['kind'] == 'rows' else stem
                positions = context['positions']
                flags = context['flags']
                key = question['id']
                if key == 'queue-sixth':
                    expected = [position for position in positions if position < flags[0]]
                elif key in ('adjacent-people', 'exhibit-dots'):
                    expected = sum(flags[0] < position < flags[1] for position in positions)
                elif key == 'photos-inclusive':
                    expected = [position for position in positions if flags[0] <= position <= flags[1]]
                else:
                    expected = [position for position in positions if flags[0] < position < flags[1]]
                matching = [value for value, option in question['options'].items()
                            if extractors[key](self.diagrams[option['visual']['image']]) == expected]
                self.assertEqual(matching, question['answer'])

    def test_game_routes_and_matches_only_accept_interior_positions(self):
        hop = game_config('hop-between', 'platformHop')
        for level in hop['levels']:
            left, right = self.diagrams[level['prompt']]['flags']
            with self.subTest(platforms=(left, right)):
                self.assertEqual(level['route'], list(range(left + 1, right)))
                self.assertEqual(self.diagrams[level['prompt']]['connector'], 'single neutral span without count marks')
                ids = {platform[-1] for platform in level['platforms']}
                self.assertTrue({f'flag-{left}', f'flag-{right}', *level['route']}.issubset(ids))
                self.assertFalse({left, right}.intersection(ids))

        tiles = game_config('match-the-middle', 'fallingTiles')
        self.assertTrue(any('count-0' in level['pieces'] for level in tiles['levels']))
        for level in tiles['levels']:
            for count, interval in level['pairs']:
                with self.subTest(tile=interval):
                    left, right = self.diagrams[interval]['flags']
                    self.assertEqual(self.diagrams[interval]['positions'], list(range(left + 1, right)))
                    self.assertEqual(self.diagrams[count]['count'], right - left - 1)

    def test_all_playback_images_and_editable_sources_match_registered_hashes(self):
        manifest = load('asset-sources.json')
        assets = {asset['key']: asset for asset in manifest['assets']}
        self.assertEqual(len(assets), len(manifest['assets']))
        for key, image in self.lesson['images'].items():
            self.assertEqual(image['file'], assets[key]['file'])
        for asset in assets.values():
            with self.subTest(image=asset['key']):
                for path_key, hash_key in (('file', 'sha256'), ('source', 'sourceSha256')):
                    self.assertEqual(sha256((LESSON / asset[path_key]).read_bytes()).hexdigest(), asset[hash_key])
        for budget in manifest['sceneImageBudgets'].values():
            actual = sum((LESSON / assets[key]['file']).stat().st_size for key in budget['imageBytes'])
            self.assertEqual(actual, budget['totalPlaybackImageBytes'])
            self.assertLessEqual(actual, budget['targetMaximumBytes'])


if __name__ == '__main__':
    unittest.main()
