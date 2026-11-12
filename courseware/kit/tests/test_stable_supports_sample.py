"""Chrome checks for the course-owned three-point support sample."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.tools import autoplay


RUN = r"""
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {join}=require('node:path');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
(async()=>{
  const browser=await chromium.launch({executablePath:process.argv[2]});
  const page=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  page.setDefaultTimeout(6500);
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.addInitScript(()=>{
      let now=1;
      const frames=[];
      requestAnimationFrame=cb=>frames.push(cb);
      window.step=(n,stop)=>{
        for(let i=0;i<n;i++){
          for(const fn of frames.splice(0))fn(now);
          now+=1000/60;
          if(stop&&K.game.status().state===stop)return true;
        }
        return false;
      };
    });
    await page.goto(pathToFileURL(process.argv[3]).href);
    assert.deepEqual(errors,[],'sample builds in the page script scope');
    const step=n=>page.evaluate(n=>window.step(n),n);
    const until=state=>page.evaluate(state=>window.step(5500,state),state);
    const read=()=>page.evaluate(()=>{
      const {w,total,combo,progress}=K.game.current.data;
      return {state:K.game.status(),stars:K.stars,cursor:w.cursor,selected:w.selection,
        placed:w.placed,reason:w.reason,solved:w.solved,total,combo,progress,
        wins:K.log.filter(s=>s.startsWith('win:')),demo:K.log.filter(s=>s.startsWith('demo:action:'))};
    });
    const send=async state=>{
      const before=await page.evaluate(()=>K.log.length);
      await page.evaluate(state=>postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
      await page.waitForFunction(before=>K.log.length>before,before,{polling:20});
    };
    await send({demo:true,level:1});
    assert.ok(await until('between'));
    const demo=await read();
    assert.equal(demo.placed.length,1);
    assert.deepEqual([demo.progress,demo.total,demo.stars,demo.wins,demo.demo],[0,0,0,[],['demo:action:1']]);
    await step(350);
    assert.deepEqual(await read(),demo);
    await send({demo:false,level:1});
    await step(2);
    const start=await read();
    assert.deepEqual([start.placed,start.progress,start.total,start.combo,start.stars],[[],0,0,0,0]);
    const pad=page.getByRole('button',{name:'选积木或放下支点'});
    for(const button of await page.locator('.arc-key:visible').all()){
      const b=await button.boundingBox();
      assert.ok(b.width>=44&&b.height>=44);
    }
    const move=async([tx,tz])=>{
      const g=await read();
      const [x,z]=g.cursor;
      for(let i=0;i<Math.abs(tx-x);i++){
        await page.keyboard.press(tx>x?'ArrowRight':'ArrowLeft');
        await step(17);
      }
      for(let i=0;i<Math.abs(tz-z);i++){
        await page.keyboard.press(tz>z?'ArrowDown':'ArrowUp');
        await step(17);
      }
      assert.deepEqual((await read()).cursor,[tx,tz]);
    };
    const action=async(touch=false)=>{
      if(touch)await pad.tap();else await page.keyboard.press('Space');
      await step(2);
    };
    const place=async(at,block,touch=false)=>{
      if((await read()).selected!==block){
        await move([block-2,3]);
        await action();
      }
      await move(at);
      await action(touch);
    };
    const triangle=[[-2,-1],[2,-1],[1,2]];
    const attempts=[
      ['line',[[-3,0],[0,0],[3,0]],[0,0,0]],
      ['spacing',[[-3,0],[2,-1],[1,2]],[0,0,0]],
      ['outside',[[-2,-1],[-1,-2],[1,-2]],[0,0,0]],
      ['base',triangle,[2,0,0]],
      ['height',triangle,[0,1,0]],
    ];
    for(const [reason,points,blocks] of attempts){
      await send({demo:false,level:3});
      await step(2);
      for(let i=0;i<3;i++)await place(points[i],blocks[i],i===2);
      const g=await read();
      assert.deepEqual([g.reason,g.placed.length,g.solved,g.progress,g.total],
        [reason,3,false,0,0],reason);
      assert.equal(g.state.levelMisses,1);
      if(reason==='line'&&process.env.MIRA_SUPPORT_SCREENS){
        await page.screenshot({path:join(process.env.MIRA_SUPPORT_SCREENS,'line.png')});
      }
    }
    await move(triangle[1]);await action();
    await place(triangle[1],0,true);
    assert.equal((await read()).solved,true);
    assert.equal((await read()).progress,1);
    if(process.env.MIRA_SUPPORT_SCREENS){
      await page.screenshot({path:join(process.env.MIRA_SUPPORT_SCREENS,'stable.png')});
    }
    await send({demo:false,level:1});
    await page.evaluate(()=>K.game.autoplay(true));
    for(let run=0;run<2;run++){
      const start=(await read()).wins.length;
      assert.ok(await until('done'));
      const g=await read();
      assert.deepEqual(g.wins.slice(start).map(s=>Number(s.split(':')[1])),[1,2,3]);
      assert.deepEqual(g.state.stars,[3,3,3]);
      assert.equal(g.stars,9);
      await page.locator('#btn-again').tap();
      const replay=await read();
      assert.deepEqual([replay.state.level,replay.placed,replay.total,replay.stars],[1,[],0,0]);
    }
    assert.deepEqual(await page.evaluate(()=>K.errs),[]);
    assert.deepEqual(errors,[]);
    console.log('One demo placement; five distinct rejection paths; touch repair; two full three-level runs.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class StableSupportsSampleTests(unittest.TestCase):
    def test_line_height_spacing_and_side_contacts_do_not_win(self):
        url = os.environ.get('MIRA_SUPPORT_SAMPLE')
        if not url:
            self.skipTest('set MIRA_SUPPORT_SAMPLE to the locally built sample')
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        result = subprocess.run(
            [shutil.which('node'), '-e', RUN, str(autoplay._playwright_dir()), chrome, str(Path(url))],
            text=True, capture_output=True, timeout=75,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
