"""Check storage diagram geometry and lesson contracts before formal image registration."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import unittest

from PIL import Image, ImageColor

from backend.content import courseware_observation
from courseware.kit import page, slides
from courseware.tools import build, check, game_audio, image_atlas, observation_card, quiz_upgrade, verify


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'diagrams'))
from compose import compositions as render_compositions
from render import (
    CASE, EXAMPLE_BAD, EXAMPLE_FITS, FLOOR_Y, INK, LEFT_BLOCK, LID_Y, RIGHT_BLOCK,
    QUIZ_FITS, QUIZ_OUTSIDE, QUIZ_OVERLAP, lid_side,
)


def read(name):
    return json.loads((ROOT / name).read_text())


def inside(rectangle):
    x, y, w, h = rectangle
    left, top, right, bottom = CASE
    return left <= x and top <= y and x + w <= right and y + h <= bottom


def overlap(first, second):
    x, y, w, h = first
    xx, yy, ww, hh = second
    return x < xx + ww and xx < x + w and y < yy + hh and yy < y + h


class StorageModels(unittest.TestCase):
    def test_turning_same_two_pieces_fits_both_without_overlap(self):
        self.assertFalse(inside(EXAMPLE_BAD[0]))
        self.assertEqual(EXAMPLE_BAD[0][2:], EXAMPLE_FITS[0][2:][::-1])
        self.assertEqual(EXAMPLE_BAD[1][2:], EXAMPLE_FITS[1][2:])
        self.assertTrue(all(inside(rectangle) for rectangle in EXAMPLE_FITS))
        self.assertFalse(overlap(*EXAMPLE_FITS))

    def test_quiz_distinguishes_overlap_outside_and_fit(self):
        self.assertTrue(all(inside(rectangle) for rectangle in QUIZ_OVERLAP))
        self.assertTrue(overlap(*QUIZ_OVERLAP))
        self.assertTrue(all(inside(rectangle) for rectangle in QUIZ_FITS))
        self.assertFalse(overlap(*QUIZ_FITS))
        self.assertFalse(inside(QUIZ_OUTSIDE[0]))
        self.assertTrue(inside(QUIZ_OUTSIDE[1]))
        self.assertEqual(QUIZ_FITS[0][2:], QUIZ_OUTSIDE[0][2:][::-1])
        self.assertEqual(QUIZ_FITS[1][2:], QUIZ_OUTSIDE[1][2:])

    def test_lid_levels_both_endpoints_only_when_contents_clear_it(self):
        closed = lid_side(115, 108)
        left_up = lid_side(174, 82)
        right_up = lid_side(115, 175)
        ink = ImageColor.getrgb(INK)
        self.assertEqual(closed.getpixel((66, LID_Y)), ink)
        self.assertEqual(closed.getpixel((420, LID_Y)), ink)
        self.assertEqual(left_up.getpixel((sum(LEFT_BLOCK), FLOOR_Y - 174)), ink)
        self.assertEqual(left_up.getpixel((420, LID_Y)), ink)
        self.assertEqual(right_up.getpixel((66, LID_Y)), ink)
        self.assertEqual(right_up.getpixel((RIGHT_BLOCK[0], FLOOR_Y - 175)), ink)
        self.assertNotEqual(left_up.getpixel((66, LID_Y)), ink)
        self.assertNotEqual(right_up.getpixel((420, LID_Y)), ink)

    def test_art_plan_covers_source_and_each_exact_diagram_has_two_official_sources(self):
        lesson, plan, notes = read('lesson.json'), read('art-plan.json'), read('official-notes.json')
        atlas_keys = []
        for atlas in plan['atlases']:
            image_atlas.validate_plan(atlas)
            atlas_keys.extend(asset['assetKey'] for asset in atlas['assets'])
        generated = set(atlas_keys)
        exact = set(plan['finishedSemanticDiagrams'])
        compositions = set(plan['compositions'])
        self.assertEqual(len(atlas_keys) + len(exact) + len(compositions), len(generated | exact | compositions))
        self.assertEqual(set(lesson['images']), generated | exact | compositions)
        for composition in plan['compositions'].values():
            self.assertLessEqual(set(composition['sources']), generated | exact)
        records = read('asset-sources.json')['assets']
        self.assertEqual(exact, {key for key, row in records.items() if row['kind'] == 'deterministic-lesson-diagram'})
        checks = {entry['assetKey']: entry for entry in notes['factChecks'] if 'assetKey' in entry}
        self.assertLessEqual(exact, set(checks))
        for key in exact:
            file = ROOT / lesson['images'][key]['file']
            with Image.open(file) as image:
                self.assertEqual(image.format, 'PNG')
                image.verify()
            digest = sha256(file.read_bytes()).hexdigest()
            self.assertEqual(records[key]['sha256'], digest)
            self.assertEqual(checks[key]['assetSha256'], digest)
            self.assertEqual({s['resource'] for s in checks[key]['sources']}, {'textbook', 'teachingDesign'})
            for citation in checks[key]['sources']:
                self.assertEqual(sha256(Path(citation['file']).read_bytes()).hexdigest(), citation['sha256'])

    def test_formal_art_references_match_files_and_compositions_rebuild(self):
        lesson, notes = read('lesson.json'), read('official-notes.json')
        records = read('asset-sources.json')['assets']
        self.assertEqual(set(records), set(lesson['images']))
        for key, asset in records.items():
            with self.subTest(asset=key):
                self.assertEqual(asset['file'], lesson['images'][key]['file'])
                self.assertEqual(sha256((ROOT / asset['file']).read_bytes()).hexdigest(), asset['sha256'])
        for fact in notes['factChecks']:
            key = fact.get('assetKey')
            if key:
                self.assertEqual(fact['assetSha256'], records[key]['sha256'])
                self.assertGreaterEqual(len({source['resource'] for source in fact['sources']}), 2)
        for key, image in render_compositions().items():
            output = BytesIO()
            image.save(output, format='PNG', optimize=True)
            self.assertEqual(sha256(output.getvalue()).hexdigest(), records[key]['sha256'])

    def test_scene_anchors_and_game_cues_match_source(self):
        lesson = read('lesson.json')
        urls = {key: '/api/classroom-media/offline-contract/media/pic-' + sha256(key.encode()).hexdigest() + '.png'
                for key in lesson['images']}
        body = {'scenes': []}
        requests = {}
        teacher_ids = set()
        for scene in lesson['scenes']:
            content = {}
            actions = [
                dict(type='speech', id=f"{scene['key']}-{index}", text=beat['say'])
                for index, beat in enumerate(scene.get('script', []), 1) if 'say' in beat
            ]
            teacher_ids.update(action['id'] for action in actions)
            if scene['type'] == 'slide':
                rendered = slides.render(scene['template'], scene['data'], image_urls=urls)
                for beat in scene['script']:
                    if 'spotlight' in beat:
                        self.assertIn(beat['spotlight'], rendered['names'])
            if scene['type'] == 'interactive':
                name = scene['page']
                markup = (ROOT / 'pages' / (name + '.html')).read_text()
                script = (ROOT / 'pages' / (name + '.js')).read_text()
                css_path = ROOT / 'pages' / (name + '.css')
                css = css_path.read_text() if css_path.is_file() else ''
                build._validate_semantic_visual(1, name, markup, css, script)
                self.assertLessEqual(set(re.findall(r'__IMG:([a-z0-9-]+)__', script)), set(urls))
                self.assertFalse(page.defined_ids(markup + script) & page.reserved_ids())
                self.assertEqual([b['setState'] for b in scene['script'] if 'setState' in b], [
                    {'demo': True, 'level': 1, 'pause': True}, {'pause': False},
                    {'demo': False, 'level': 1, 'pause': False},
                ])
                anchors = [b['highlight'] for b in scene['script'] if 'highlight' in b]
                self.assertEqual(len(set(anchors)), 3)
                self.assertTrue(all(a.startswith('#') and a[1:] in page.defined_ids(markup) for a in anchors))
                html = page.page(scene['title'], markup, css, script)
                if 'observationCard' in scene:
                    html = observation_card.embed(html, scene['observationCard'],
                                                  scene_id='scene-' + name, image_urls=urls)
                    self.assertIn('mira-game-observation-ready', html)
                content['html'] = html
                requests['scene-' + name] = scene['gameAudio']
            body['scenes'].append(dict(id='scene-' + scene['key'], type=scene['type'], actions=actions, content=content))
        self.assertEqual(sum(map(len, requests.values())), 16)
        game_audio.compile_cues(body, requests, teacher_ids)
        for scene in body['scenes']:
            if scene['id'] in requests:
                self.assertIn('data-courseware-reused-audio', scene['content']['html'])

    def test_parent_projection_requires_all_actual_camera_pairs(self):
        lesson = read('lesson.json')
        camera = next(scene for scene in lesson['scenes'] if scene['key'] == 'photograph-neat-storage')
        card = camera['observationCard']
        scene_id = 'scene-' + camera['key']
        snapshot = dict(schemaVersion=courseware_observation.SNAPSHOT_SCHEMA,
                        sceneId=scene_id, kind='simulation', levels=[])
        for i, level in enumerate(card['levels'], 1):
            trial = level['trials'][0]
            snapshot['levels'].append(dict(level=i, trials=[dict(
                trialId=trial['id'], top=next(iter(trial['top'])), side=next(iter(trial['side'])),
            )]))
        missing_last = {**snapshot, 'levels': snapshot['levels'][:-1]}
        with self.assertRaisesRegex(ValueError, 'invalid observation snapshot'):
            courseware_observation.project_snapshot(card, scene_id, missing_last)
        projected = courseware_observation.project_snapshot(card, scene_id, snapshot)
        self.assertEqual(projected['kind'], 'simulation')
        self.assertIn('记录实际发现', projected['familyTask'])
        self.assertEqual([level['label'] for level in projected['levels']],
                         ['分袋书包', '透明盖收纳箱', '分格托盘'])
        snapshot['levels'][0]['trials'][0]['side'] = 'storage-side-toybox'
        with self.assertRaisesRegex(ValueError, 'undeclared observation outcome'):
            courseware_observation.project_snapshot(card, scene_id, snapshot)

    def test_narration_and_new_picture_quiz_cover_the_intended_goals(self):
        lesson, brief, notes = read('lesson.json'), read('brief.json'), read('official-notes.json')
        self.assertEqual(notes['objectives'], brief['goals'])
        self.assertEqual(notes['objectives'], [item['goal'] for item in notes['objectiveEvidence']])
        self.assertEqual(len(notes['objectiveEvidence']), 4)
        self.assertTrue(all(item['pageRefs'] for item in notes['objectiveEvidence']))
        self.assertFalse([i for i in check.check_classroom({'scenes': []}, notes=notes, teaching=True) if i['gate'] == 'G0'])
        body = {'scenes': []}
        for scene in lesson['scenes']:
            if scene['type'] == 'quiz':
                questions = scene['questions']
                self.assertEqual([''.join(q['answer']) for q in questions], list('BACBCA'))
                self.assertEqual(len({q['skill'] for q in questions}), 6)
                options = [v['visual']['image'] for q in questions for v in q['options'].values()]
                self.assertEqual(len(set(options)), 18)
                lines = scene['intro'] + [quiz_upgrade._question_text(q['question']) for q in questions]
            else:
                lines = [beat['say'] for beat in scene['script'] if 'say' in beat]
                self.assertGreaterEqual(len(lines), 6 if scene['type'] == 'slide' else 5)
                self.assertGreaterEqual(sum(map(len, lines)), 100 if scene['type'] == 'slide' else 90)
            self.assertTrue(all(0 < len(line) <= 34 for line in lines))
            body['scenes'].append(dict(
                title=scene['title'], type=scene['type'], content={},
                actions=[dict(id=f"{scene['key']}-{i}", type='speech', text=text) for i, text in enumerate(lines, 1)],
            ))
        requests = verify.build_requests(body, notes, teaching=True)
        self.assertEqual(sum(len(r['items']) for r in requests if r['kind'] == 'speech'), 77)
        self.assertEqual(sum(len(r['items']) for r in requests if r['kind'] == 'teaching'), 6)


if __name__ == '__main__':
    unittest.main()
