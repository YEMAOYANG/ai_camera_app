import json
import re
import subprocess
import unittest

from backend.content.courseware_observation import SNAPSHOT_SCHEMA, scene_card
from courseware.tools.observation_card import embed


class ObservationCardBuildTests(unittest.TestCase):
    def test_card_uses_registered_picture_and_checkpoint_captures_finished_event(self):
        view = {'visible': {'label': '看见杯口', 'image': 'cup'}}
        card = {'title': '杯子观察', 'familyTask': '和家人看看杯子。', 'levels': [
            {'label': '看看', 'trials': [{'id': 'one', 'label': '杯子', 'top': view, 'side': view}]},
        ]}
        image = '/api/classroom-media/stage/media/pic-' + 'f' * 64 + '.png'
        html = embed('<body></body>', card, scene_id='scene-cup', image_urls={'cup': image})
        scene = {'type': 'interactive', 'content': {'html': html}}
        self.assertEqual(scene_card(scene)['levels'][0]['trials'][0]['top']['visible']['image'], image)
        self.assertEqual(view['visible']['image'], 'cup')
        checkpoint = re.search(r'<script>(.*?)</script>', html, re.S)[1]
        check = """
const assert = require('node:assert/strict');
global.window = new EventTarget();
let state = null;
window.K = {game: {observation: () => state}};
""" + checkpoint + """
assert.equal(window.miraActivityCheckpoint.capture(), null);
let notified = 0;
window.addEventListener('mira-activity-state-changed', () => notified++);
window.dispatchEvent(new Event('mira-game-observation-ready'));
assert.equal(notified, 0);
state = """ + json.dumps({'schemaVersion': SNAPSHOT_SCHEMA, 'sceneId': 'scene-cup', 'kind': 'simulation'}) + """;
window.dispatchEvent(new Event('mira-game-observation-ready'));
assert.equal(notified, 1);
assert.equal(window.miraActivityCheckpoint.capture(), state);
assert.equal(window.miraActivityCheckpoint.restore({...state, sceneId: 'wrong'}), false);
assert.equal(window.miraActivityCheckpoint.restore(state), true);
"""
        subprocess.run(['node', '-'], input=check, text=True, check=True, timeout=10)
        with self.assertRaises(ValueError):
            embed('<body></body>', card, scene_id='scene-cup', image_urls={})
