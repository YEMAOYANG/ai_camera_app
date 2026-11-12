import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from courseware.kit import page
from courseware.tools import autoplay, game_preview


CUSTOM = """
window.heard = [];
window.miraNarrate = id => heard.push(id);
K.ready({title:'练习',sub:'按空格'});
K.game(K.gameTemplates.arcade({
  levels:[{},{},{}], cues:[{goal:'goal',steps:['first','second'],praise:'praise'}]
},{
  controls:[['action','○','执行']], backdrop:'#eef3df', validate(){},
  reset(){ return {}; }, goal:()=>2, update(w,l,input,dt,feedback){
    if(input.press('action')) feedback.award(600,350);
  },
  draw(){}, pilot(){return Classic.bot('action');}
}));
"""

PLAY = """
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(path.join(process.env.PW_DIR,'node_modules/playwright-core'));
(async ()=>{
  const [dir,exe] = process.argv.slice(1);
  const browser = await chromium.launch({executablePath:exe});
  try{
    const page = await browser.newPage({viewport:{width:1280,height:720}});
    const open = name => page.goto(pathToFileURL(path.join(dir,name)).href);
    await open('custom.html');
    await page.locator('#start-btn').click();
    assert.deepEqual(await page.evaluate(()=>heard),['first']);
    await page.keyboard.press('Space');
    await page.waitForFunction(()=>heard.length===2);
    await page.locator('.arc-voice').click();
    assert.deepEqual(await page.evaluate(()=>heard),['first','second','second']);

    await page.addInitScript(()=>{
      window.hud = new Set();
      const old = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function(text,x,y,...rest){
        if(x===640 && y===46) hud.add(String(text));
        return old.call(this,text,x,y,...rest);
      };
    });
    await open('prompt.html');
    await page.locator('#start-btn').click();
    await page.waitForFunction(()=>hud.has('−1'));
    assert.deepEqual(await page.evaluate(()=>[...hud]),['−1']);
    assert.deepEqual(await page.evaluate(()=>K.errs),[]);
  }finally{ await browser.close(); }
})().catch(err=>{console.error(err);process.exitCode=1;});
"""


class ArcadeReleaseSupportTest(unittest.TestCase):
    def test_custom_mechanic_receives_current_cues_and_platform_hud_can_hide_answer(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        if not node or not chrome.is_file():
            self.skipTest('Chrome and Node are required')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom = page.page('练习', '', '', CUSTOM)
            self.assertIn('K.gameTemplates.arcade = Classic.create', custom)
            self.assertNotIn('K.gameTemplates.bubbleMaze =', custom)
            (root / 'custom.html').write_text(custom, encoding='utf-8')
            levels = json.loads((game_preview.EXAMPLES / 'platform-hop.json').read_text())['levels']
            levels[0].update(prompt='−1', startLabel=14)
            config = json.dumps({'levels': levels}, ensure_ascii=False)
            script = 'K.ready({title:"提示",sub:"开始"});K.game(K.gameTemplates.platformHop(' + config + '));'
            (root / 'prompt.html').write_text(page.page('提示', '', '', script), encoding='utf-8')
            result = subprocess.run([node, '-e', PLAY, str(root), str(chrome)], text=True,
                                    capture_output=True, timeout=25,
                                    env={**os.environ, 'PW_DIR': str(playwright)})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
