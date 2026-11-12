"""Verify the Classic teacher and child lifecycle in Chrome."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import page
from courseware.tools import autoplay


ROOT = Path(__file__).resolve().parents[3]
RUN = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {chromium} = require(process.argv[1]+'/node_modules/playwright-core');
const fixtures = JSON.parse(fs.readFileSync(0,'utf8'));

async function verify(browser,{name,html,url,levels,hud=false}) {
  const page = await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  const errors = [];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('requestfailed',request=>errors.push(request.url()+': '+request.failure()?.errorText));
  try {
    await page.addInitScript(()=>{
      const pending=[];
      let now=1;
      window.requestAnimationFrame=frame=>pending.push(frame);
      window.advanceGame=(frames,state)=>{
        for(let i=0;i<frames;i++){
          for(const frame of pending.splice(0))frame(now);
          now+=1000/60;
          if(state&&K.game.status().state===state)return true;
        }
        return false;
      };
    });
    await page.goto(url??'about:blank');
    if(html)await page.setContent(html);
    const read = () => page.evaluate(()=>{
      const {state,level,auto,stars} = K.game.status();
      const {total,combo,progress} = K.game.current.data;
      return {state,level,auto,stars,total,combo,progress,sharedStars:K.stars,
        hud:K.$('#star-n')?.textContent??null,
        route:K.$$('.arc-route .arc-node').map(node=>node.className),
        score:K.$('.arc-score').textContent,
        wins:K.log.filter(entry=>entry.startsWith('win:')),
        demo:K.log.filter(entry=>entry.startsWith('demo:action:')),
        next:!!K.$('#g-next')&&!K.$('#gcard').classList.contains('gone')};
    });
    const tick = frames => page.evaluate(frames=>advanceGame(frames),frames);
    const until = async (state,limit) => {
      const reached=await page.evaluate(([state,limit])=>advanceGame(limit,state),[state,limit]);
      assert.ok(reached,name+' never reached '+state+': '+JSON.stringify(await read()));
    };
    const send = async state => {
      const before=await page.evaluate(()=>K.log.length);
      await page.evaluate(state=>postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
      await page.waitForFunction(before=>K.log.length>before,before,{polling:10});
      await tick(1);
    };
    const route = count => Array.from({length:levels},(_,i)=>
      'arc-node'+(i<count?' arc-won':i===count?' arc-current':''));
    const reset = async () => {
      const status=await read();
      assert.deepEqual(
        [status.state,status.level,status.total,status.combo,status.progress,status.stars,
          status.sharedStars,status.hud],
        ['play',1,0,0,0,[],0,hud?'0':null],name+' new run');
      assert.equal(await page.locator('#finish').isVisible(),false,name+' completion overlay');
      return status;
    };

    assert.equal((await read()).state,'ready',name);
    await send({demo:true,level:1});
    await until('between',1800);
    const demo=await read();
    assert.deepEqual([demo.level,demo.progress,demo.total,demo.combo,demo.stars,demo.sharedStars,
      demo.hud,demo.route,demo.demo,demo.wins,demo.next],
      [1,1,0,0,[],0,hud?'0':null,route(0),['demo:action:1'],[],false],name+' teacher action');
    await tick(300);
    assert.deepEqual(await read(),demo,name+' teacher action must stay stopped');
    await send({demo:false,level:1});
    const child=await reset();
    assert.deepEqual([child.auto,child.route,child.score],[false,route(0),'0  /  ×0'],
      name+' hands control to the child');

    await page.evaluate(()=>K.game.autoplay(true));
    await until('between',1800);
    assert.equal((await read()).sharedStars,3,name+' level 1 should award three stars');
    await send({demo:false,level:1});
    assert.equal((await reset()).auto,false,name+' clears a prior award on handoff');

    for(let run=0;run<2;run++){
      const start=(await read()).wins.length;
      await page.evaluate(()=>K.game.autoplay(true));
      await until('done',7200);
      const finish=await read();
      const wins=finish.wins.slice(start).map(win=>win.split(':').slice(1).map(Number));
      assert.deepEqual(wins,finish.stars.map((stars,i)=>[i+1,stars]),name+' one win per level');
      assert.equal(finish.stars.length,levels);
      assert.ok(finish.stars.every(stars=>stars>=1&&stars<=3));
      const shared=finish.stars.reduce((sum,stars)=>sum+stars,0);
      assert.equal(finish.sharedStars,shared,name+' shared stars match the current run');
      assert.equal(finish.hud,hud?String(shared):null,name+' visible stars');
      assert.deepEqual(finish.route,route(levels),name+' all route markers won');
      if(run===1)await page.evaluate(()=>K.game.autoplay(false));
      await page.locator('#btn-again').tap();
      assert.equal((await reset()).auto,run===0,name+' replay preserves the current input mode');
      if(run===1){
        await tick(1);
        const replay=await reset();
        assert.deepEqual([replay.route,replay.score],[route(0),'0  /  ×0'],name+' replay HUD');
      }
    }
    assert.deepEqual(await page.evaluate(()=>K.errs),[],name);
    assert.deepEqual(errors,[],name);
    console.log(name+' | demo, handoff, 2 clears, 2 replay resets');
  } finally {
    await page.close();
  }
}

(async()=>{
  const browser=await chromium.launch({executablePath:process.argv[2]});
  try{
    for(const fixture of fixtures)await verify(browser,fixture);
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


def browser_check(fixtures, node, chromium, playwright):
    return subprocess.run(
        [node, '-e', RUN, str(playwright), str(chromium)],
        input=json.dumps(fixtures), text=True, capture_output=True, timeout=180,
    )


class ClassicLifecycleTests(unittest.TestCase):
    def test_teacher_demo_and_both_star_counters_across_replays(self):
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        node = shutil.which('node')
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')

        catalog = json.loads((ROOT / 'courseware/kit/game_templates/catalog.json').read_text())
        fixtures = []
        anchors = ''.join(f'<div id="game-{role}"></div>' for role in ('goal', 'player', 'target'))
        for template in catalog['templates']:
            if template['status'] != '可用':
                continue
            version = template['versions'][-1]
            config = json.loads((ROOT / version['example']).read_text())
            title = config.pop('title')
            config.pop('template')
            config.pop('draft', None)
            config.pop('art', None)
            levels = len(config['levels'])
            js = f'K.ready({{title:{json.dumps(title)},sub:""}});\n'
            hud = template['id'] == 'bubbleMaze'
            if hud:
                js += f'K.hud({{title:"测试星数",icon:"",levels:{levels}}});\n'
            js += f'K.game({version["entryPoint"]}({json.dumps(config)}));'
            fixtures.append(dict(name=template['id'], html=page.page(title, anchors, '', js),
                                 levels=levels, hud=hud))
        self.assertTrue(fixtures)
        result = browser_check(fixtures, node, chrome, playwright)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
