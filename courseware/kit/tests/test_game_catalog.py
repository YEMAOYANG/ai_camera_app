"""Build and play the exact presets named by the public template catalog."""
from datetime import date
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import game_templates, page
from courseware.tools import autoplay


ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / 'courseware/kit/game_templates/catalog.json'
ANCHORS = ('game-goal', 'game-player', 'game-target')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


class GameCatalogTests(unittest.TestCase):
    def test_catalog_matches_loader_and_requires_owner_acceptance(self):
        catalog = load(CATALOG)
        templates = catalog['templates']
        self.assertEqual(catalog['schemaVersion'], 1)
        self.assertCountEqual([t['id'] for t in templates], game_templates._CLASSIC + game_templates._MECHANICS)
        entry_points = []
        for template in templates:
            with self.subTest(template=template['id']):
                self.assertIn(template['status'], {'停用', '试玩中', '可用'})
                self.assertTrue(template['knowledgeRules'])
                self.assertTrue(template['controls']['touch'])
                for rule in template['knowledgeRules']:
                    examples = catalog['ruleTypes'][rule]['examples']
                    self.assertTrue(1 <= len(examples) <= 2)
                    self.assertTrue(all(e['grade'] == 1 and e['lesson'] and e['use'] for e in examples))
                versions = template['versions']
                self.assertEqual([v['version'] for v in versions], list(range(1, len(versions) + 1)))
                latest = versions[-1]
                self.assertEqual((template['status'], template['ownerApprovedOn']),
                                 (latest['status'], latest['ownerApprovedOn']))
                for version in versions:
                    approved = version['ownerApprovedOn']
                    self.assertEqual(version['status'] == '可用', approved is not None)
                    if approved:
                        self.assertEqual(date.fromisoformat(approved).isoformat(), approved)
                        self.assertEqual(version['approvalEvidence']['recordedAt'][:10], approved)
                    entry_points.append(version['entryPoint'])
                    self.assertTrue((ROOT / version['source']).is_file())
                    self.assertTrue(version['autopilot'])
                    self.assertEqual(version['teacherAnchors'], list(ANCHORS))
                    preset = load(ROOT / version['example'])
                    self.assertEqual(version['entryPoint'], 'K.gameTemplates.' + preset['template'])
                    levels = version['levels']
                    self.assertEqual(len(preset['levels']), version['exampleLevels'])
                    self.assertTrue(levels['min'] <= len(preset['levels']) <= levels['max'])
        self.assertEqual(len(entry_points), len(set(entry_points)))

    def test_preview_cue_scripts_cover_goals_hints_and_praise(self):
        templates = load(CATALOG)['templates']
        voice = load(ROOT / 'courseware/kit/examples/arcade-voice.json')
        lines = {line['id']: line for line in voice['lines']}
        self.assertEqual(len(lines), len(voice['lines']))
        self.assertEqual(set(voice['cues']), {
            Path(v['preview']['page']).stem for t in templates for v in t['versions'] if v['preview']
        })
        for slug, cues in voice['cues'].items():
            sample = load(ROOT / f'courseware/kit/examples/classic-arcade/{slug}.json')
            self.assertEqual(len(cues), len(sample['levels']))
            for level in cues:
                for event in ('goal', 'hint', 'hint2', 'praise'):
                    self.assertTrue(lines[level[event]]['text'].strip())

    def test_every_catalog_example_builds_and_wins_twice(self):
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        node = shutil.which('node')
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required for catalog playthroughs')

        fixtures = []
        for template in load(CATALOG)['templates']:
            for version in template['versions']:
                config = load(ROOT / version['example'])
                title = config.pop('title')
                config.pop('template')
                config.pop('art', None)  # Run the same rules offline, including broken-image fallback.
                config.pop('draft', None)
                js = f'K.ready({{title:{json.dumps(title)},sub:""}});\n'
                js += f'K.game({version["entryPoint"]}({json.dumps(config)}));'
                html = page.page(title, ''.join(f'<div id="{a}"></div>' for a in ANCHORS), '', js)
                fixtures.append({'name': version['entryPoint'], 'html': html, 'levels': version['exampleLevels'],
                                 'demoOnce': version['teacherDemo'] == 'firstAction'})

        observation = r'''
window.observationSignals=0;window.accepted=[];
window.addEventListener('mira-game-observation-ready',()=>++window.observationSignals);
K.ready({title:'观察',sub:'试放两次'});
K.game(K.gameTemplates.arcade({levels:[{},{},{}],observation:{sceneId:'trial-fixture-42',trials:{
  before:{top:['overhang'],side:['raised']},after:{top:['covered'],side:['flat']}
}}},{
  controls:[['action','◎','试放']],backdrop:'#fff0d0',validate(){},
  reset(){return {count:0};},goal:()=>2,draw(){},pilot(){return {press:k=>k==='action'};},
  update(w,l,input,dt,fb){
    if(!input.press('action')||w.count>=2)return;
    if(!w.count++){
      accepted.push(fb.observe('before',{top:'overhang',side:'wrong'}));
      accepted.push(fb.observe('before',{top:'overhang',side:'raised'}));
    }else{
      accepted.push(fb.observe('before',{top:'overhang',side:'raised'}));
      accepted.push(fb.observe('after',{top:'covered',side:'flat'}));
    }
    fb.award(640,360);
  }
}));'''
        fixtures.append({'name': 'observation', 'html': page.page('观察', '', '', observation),
                         'levels': 3, 'demoOnce': True, 'observation': True})

        voice_lead = r'''
window.cueState=(cueId,status)=>window.dispatchEvent(new CustomEvent('mira-narration-state',{detail:{cueId,status}}));
window.miraNarrate=id=>{if(id!=='missing')cueState(id,'playing');};
K.ready({title:'听口令',sub:'听完再操作'});
K.game(K.gameTemplates.arcade({levels:[{},{},{}],voiceLead:true,
  cues:[{goal:'goal1',praise:'praise'},{goal:'missing'},{}]}, {
  controls:[['action','◎','行动']],backdrop:'#fff0d0',validate(){},reset(){return {};},goal:()=>2,draw(){},
  update(w,l,input,dt,fb){if(input.press('action'))fb.award(640,360);}
}));'''
        fixtures.append({'name': 'voice-lead', 'html': page.page('听口令', '', '', voice_lead), 'voice': True})

        result = subprocess.run([node, str(Path(__file__).with_name('game_catalog.browser.cjs')),
                                 str(playwright), str(chrome)], input=json.dumps(fixtures), text=True,
                                capture_output=True, timeout=100)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
