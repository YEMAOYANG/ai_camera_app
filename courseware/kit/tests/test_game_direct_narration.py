"""Custom game cues and teacher checkpoints share the player engine."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import page
from courseware.tools import autoplay


JS = r'''
window.heard=[];
window.cueEvent=(cueId,status)=>dispatchEvent(new CustomEvent('mira-narration-state',{detail:{cueId,status}}));
window.miraNarrate=id=>{heard.push(id);cueEvent(id,'playing')};
window.miraCancelNarration=()=>cueEvent(null,'ready');
K.ready({title:'练习',sub:'用空格'});
K.game({
  levels:3,demoOnce:true,winPause:0,
  narration:[1,2,3].map(n=>({goal:'goal-'+n,hint:'hint-'+n,hint2:'strong-'+n,praise:'praise-'+n})),
  reset(g){g.data={elapsed:0,actions:0}},
  autopilot(g){g.taps.push({key:true})},
  update(g,dt){
    g.data.elapsed+=dt;
    if(g.pointer.down)g.miss();
    if(!g.taps.some(tap=>tap.key))return;
    g.data.actions++;
    if(g.demoAction())return;
    g.win();
  },
});
'''


RUN = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2]});
 try{
  const p=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  await p.evaluate(()=>{
    const queue=[];let now=1;
    window.requestAnimationFrame=fn=>queue.push(fn);
    window.step=n=>{for(let i=0;i<n;i++){now+=1000/60;for(const fn of queue.splice(0))fn(now);}};
    window.check=()=>({state:K.game.status(),data:K.game.current.data,heard:[...heard],errors:K.errs});
  });
  await p.setContent(JSON.parse(fs.readFileSync(0,'utf8')));
  await p.locator('#start-btn').tap();
  const game=()=>p.evaluate(()=>check());
  const advance=n=>p.evaluate(n=>step(n),n);
  const end=id=>p.evaluate(id=>cueEvent(id,'ready'),id);
  await p.mouse.move(150,150);
  await p.mouse.down();
  await p.keyboard.press('Space');
  await advance(2);
  assert.equal((await game()).data.elapsed,0);
  await end('unrelated');
  await advance(2);
  assert.equal((await game()).data.elapsed,0);
  await end('goal-1');
  await advance(2);
  await p.mouse.up();
  assert.equal((await game()).state.misses,0,'presses during the goal must not leak into play');
  assert.equal((await game()).data.actions,0);
  const replay=p.getByRole('button',{name:'重听老师'});
  assert.ok((await replay.boundingBox()).width>=44);
  await replay.tap();
  await end('goal-1');
  for(let i=0;i<2;i++){
    await p.mouse.down();
    await advance(1);
    await p.mouse.up();
    await advance(1);
  }
  await p.keyboard.press('Space');
  await advance(2);
  assert.deepEqual((await game()).heard,['goal-1','goal-1','hint-1','strong-1','praise-1']);
  assert.equal(await p.locator('#g-next').count(),0);
  await end('praise-1');
  await advance(1);
  await p.locator('#g-next').tap();
  assert.notEqual(await p.evaluate(()=>document.activeElement.id),'g-next');
  assert.equal((await game()).heard.at(-1),'goal-2');

  await p.evaluate(()=>K.onState({demo:true,level:2}));
  await advance(120);
  let state=await game();
  assert.equal(state.state.level,1);
  assert.equal(state.state.state,'between');
  assert.equal(state.data.actions,1);
  assert.equal(state.heard.at(-1),'goal-2');
  assert.ok(!state.state.stars[1],'the demo must not win the level it interrupted');
  assert.equal(await replay.isVisible(),false);
  await p.evaluate(()=>K.onState({demo:false,level:1}));
  assert.equal((await game()).data.actions,0);
  assert.equal((await game()).heard.at(-1),'goal-1');
  await p.evaluate(()=>{K.game.autoplay(true);K.game.current.start(0)});
  await advance(10);
  state=await game();
  assert.equal(state.state.state,'done');
  assert.deepEqual(state.state.stars,[3,3,3]);
  assert.equal(state.heard.at(-1),'goal-1','autoplay must not speak');
  assert.deepEqual(state.errors,[]);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


class DirectGameNarrationTest(unittest.TestCase):
    def test_replay_hints_praise_and_demo_handoff(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        html = page.page('练习', '', '', JS)
        result = subprocess.run(
            [node, '-e', RUN, str(playwright), str(chrome)], input=json.dumps(html),
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
