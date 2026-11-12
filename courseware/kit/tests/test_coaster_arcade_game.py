"""Browser regression for the live controls in the two cup-coaster games.

Set MIRA_COASTER_GAME_SOURCE to a staged lesson directory and
MIRA_COASTER_REQUIRE_OBSERVATION=1 to verify an observation-enabled candidate.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import page
from courseware.tools import autoplay


SOURCE = Path(__file__).resolve().parents[3] / 'courseware/lessons/renjiao-science-g1-upper-make-coaster-arcade'

RUN = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const {pages,requireObservation}=JSON.parse(fs.readFileSync(0,'utf8'));

async function openGame(browser, html){
  const p=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  await p.evaluate(()=>{
    const queue=[];let now=1;
    window.requestAnimationFrame=fn=>queue.push(fn);
    window.advanceGame=n=>{
      for(let i=0;i<n;i++){now+=1000/60;for(const fn of queue.splice(0))fn(now);}
    };
  });
  await p.setContent(html);
  await p.evaluate(()=>{
    window.gameReports=[];
    addEventListener('mira-game-observation-ready',()=>gameReports.push(K.game.observation()));
  });
  await p.locator('#start-btn').tap();
  const step=n=>p.evaluate(n=>advanceGame(n),n);
  const read=()=>p.evaluate(()=>{
    const {w,level,progress}=K.game.current.data;
    return {w,level,progress,status:K.game.status(),observation:K.game.observation(),reports:gameReports,errors:K.errs};
  });
  const hold=async (key,n)=>{
    await p.keyboard.down(key);
    await step(n);
    await p.keyboard.up(key);
  };
  const press=async key=>{await p.keyboard.press(key);await step(1);};
  const next=async ()=>{await p.locator('#g-next').tap();await step(2);};
  await step(2);
  return {p,step,read,hold,press,next};
}

async function checkCircle(browser){
  const {p,step,read,hold,press,next}=await openGame(browser,pages.circle);
  try{
    for(let i=0;i<3;i++){
      const target=(await read()).level.radius;
      if(i===0)await hold('ArrowUp',18);
      await press('Space');
      await hold('ArrowRight',20);
      const wrong=await read();
      assert.equal(wrong.w.ink,false);
      assert.equal(wrong.w.angle,0);
      assert.equal(wrong.progress,0);
      assert.equal(wrong.status.levelMisses,1);

      const adjustment=target-wrong.w.radius;
      await hold(adjustment>0?'ArrowUp':'ArrowDown',Math.round(Math.abs(adjustment)/1.8));
      await press('Space');
      assert.equal((await read()).w.radius,target);
      assert.equal((await read()).w.ink,true);
      await hold('ArrowDown',24);
      assert.equal((await read()).w.radius,target,'the rope cannot shorten while drawing');
      const turn=i===1?'ArrowLeft':'ArrowRight';
      await hold(turn,32);
      const part=await read();
      assert.equal(part.w.direction,i===1?-1:1);
      assert.ok(part.w.angle>0&&part.w.angle<2*Math.PI);
      await hold(turn==='ArrowLeft'?'ArrowRight':'ArrowLeft',23);
      assert.equal((await read()).w.angle,part.w.angle,'opposite turn cannot shortcut the circle');
      await hold(turn,730);
      const done=await read();
      assert.equal(done.w.radius,target);
      assert.equal(done.w.angle,2*Math.PI);
      assert.equal(done.progress,done.level.marks.length);
      assert.equal(done.status.auto,false);
      assert.deepEqual(done.errors,[]);
      if(i<2)await next();
      else assert.equal(done.status.state,'done');
    }
  }finally{await p.close();}
}

const expected=[
  {kind:'narrow',covers:false,flat:true},
  {kind:'curled',covers:true,flat:false},
  {kind:'mixed',covers:false,flat:false},
];

async function checkCup(browser){
  const {p,step,read,hold,press,next}=await openGame(browser,pages.cup);
  try{
    const align=async()=>{
      for(let i=0;i<15;i++){
        const delta=await p.evaluate(()=>{
          const center=id=>{const r=document.getElementById(id).getBoundingClientRect();return r.x+r.width/2;};
          return (center('game-target')-center('game-player'))/K.scale;
        });
        if(Math.abs(delta)<16)return;
        await hold(delta<0?'ArrowLeft':'ArrowRight',Math.min(42,Math.max(1,Math.floor(Math.abs(delta)/4.8))));
      }
      assert.fail('moving target never came within reach');
    };
    const drop=async touch=>{
      if(touch)await p.getByRole('button',{name:'把空杯轻放在垫子上'}).tap();
      else await press('Space');
      await step(21);
    };
    for(let i=0;i<3;i++){
      await align();
      await drop(i===0);
      const before=await read();
      assert.deepEqual(before.w.before,expected[i]);
      assert.equal(before.w.after,null);
      assert.equal(before.progress,1);
      assert.equal(before.observation,null);

      await step(60);
      await drop(false);
      const rejected=await read();
      assert.deepEqual(rejected.w.latest,expected[i]);
      assert.equal(rejected.w.after,null,'the same flawed support cannot pass the second trial');
      assert.equal(rejected.progress,1);
      assert.equal(rejected.status.levelMisses,1);
      await step(63);

      await align();
      await drop(i===1);
      const after=await read();
      assert.deepEqual(after.w.before,expected[i]);
      assert.deepEqual(after.w.after,{kind:'ready',covers:true,flat:true});
      assert.equal(after.progress,2);
      assert.equal(after.observation,null,'the last trial is still in progress until the game completes');
      await step(110);
      if(i<2)await next();
    }
    const final=await read();
    assert.equal(final.status.state,'done');
    assert.deepEqual(final.errors,[]);
    const card=p.locator('.coaster-observation canvas');
    const summary=await card.getAttribute('aria-label');
    assert.match(summary,/第1关.*杯底伸出.*第2关.*垫边翘起.*第3关.*杯底伸出、垫边翘起/);
    if(!requireObservation)return;
    const snapshot={
      schemaVersion:'mira.game.observation.v1',sceneId:'scene-cup',kind:'simulation',
      levels:expected.map((before,i)=>({level:i+1,trials:[
        {trialId:'before',top:before.covers?'covers':'extends',side:before.flat?'flat':'raised'},
        {trialId:'after',top:'covers',side:'flat'}
      ]})),
    };
    assert.deepEqual(final.observation,snapshot);
    assert.deepEqual(final.reports,[snapshot]);
    await p.locator('#btn-again').tap();
    assert.equal((await read()).observation,null);
    await p.evaluate(()=>K.onState({demo:true,level:1}));
    await step(850);
    const demo=await read();
    assert.equal(demo.progress,1);
    assert.equal(demo.observation,null);
    await p.evaluate(()=>{K.game.autoplay(true);K.onState({level:1});});
    await step(2300);
    const automatic=await read();
    assert.equal(automatic.status.state,'done');
    assert.equal(automatic.observation,null);
    assert.deepEqual(automatic.reports,[snapshot]);
    assert.equal(await card.count(),0);
  }finally{await p.close();}
}

(async()=>{
  const browser=await chromium.launch({executablePath:process.argv[2]});
  try{await checkCircle(browser);await checkCup(browser);}
  finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
'''


class CoasterArcadeGameTest(unittest.TestCase):
    def test_fixed_radius_and_two_view_trials_with_browser_controls(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        source = Path(os.environ.get('MIRA_COASTER_GAME_SOURCE', SOURCE))
        if not source.is_dir() and 'MIRA_COASTER_GAME_SOURCE' not in os.environ:
            self.skipTest('cup-coaster game sources are not present in this checkout')
        fixtures = {}
        for name in ('circle', 'cup'):
            scene = source / 'pages' / name
            fixtures[name] = page.page(name, scene.with_suffix('.html').read_text(),
                                       scene.with_suffix('.css').read_text(), scene.with_suffix('.js').read_text())
        result = subprocess.run(
            [node, '-e', RUN, str(playwright), str(chrome)],
            input=json.dumps({'pages': fixtures, 'requireObservation': os.environ.get('MIRA_COASTER_REQUIRE_OBSERVATION') == '1'}),
            text=True, capture_output=True, timeout=50,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
