"""A repeated RAF timestamp must not pin the claw or award demo credit."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.kit import page
from courseware.tools import autoplay


GAME = r'''
K.ready({title:'小吊车',sub:'看准再放'});
const round={goal:'圆形',cargo:'圆形',cars:['方形','圆形'],drop:[1],hint:'看图形',hint2:'等吊爪对准再放'};
const options=K.gameTemplates.crane({levels:[
  {name:'第一关',rounds:[round],demoRounds:[{...round,cars:['圆形','方形'],drop:[0]}]},
  {name:'第二关',rounds:[round]},
]});
options.demoOnce=DEMO_ONCE;
K.game(options);
'''

RUN = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const samples=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2]});
 try{
  for(const [once,html] of samples){
   const page=await browser.newPage({viewport:{width:640,height:360}});
   await page.evaluate(()=>{
    let now=1;const queue=[];
    requestAnimationFrame=fn=>queue.push(fn);
    window.framePair=()=>{
     const world=()=>K.game.current.data.world;
     now+=1000/60;
     for(const f of queue.splice(0))f(now);
     const before={x:world().x,dir:world().dir};
     for(const f of queue.splice(0))f(now);
     const after={x:world().x,dir:world().dir};
     return {before,after};
    };
    window.gameState=()=>{
     const g=K.game.current,w=g.data.world;
     return {x:w.x,dir:w.dir,landed:[...w.landed],state:g.state,stars:g.stars,errors:K.errs,
             logs:[...K.log]};
    };
   });
   await page.setContent(html);
   const send=async state=>{
    await page.evaluate(state=>postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
    await page.waitForFunction(auto=>K.game.current.autoLoop===auto,state.demo,{polling:20});
   };
   await send({demo:true,level:1});
   await page.evaluate(()=>{for(let i=0;i<740;i++)framePair()});
   const result=await page.evaluate(()=>gameState());
   if(once){
    assert.equal(result.state,'between');
    assert.deepEqual(result.landed,[0]);
    assert.deepEqual(result.stars,[]);
    assert.equal(result.logs.filter(entry=>entry==='demo:action:1').length,1);
    assert.equal(result.logs.filter(entry=>entry.startsWith('win:')).length,0);
   }else{
    assert.ok(result.logs.filter(entry=>entry.startsWith('win:1:')).length>1,'legacy demo still loops');
   }
   await send({demo:false,level:1});
   const boundaries=await page.evaluate(()=>{
    const edges=[];
    for(let i=0;i<550;i++){
     const pair=framePair();
     if(pair.before.x===128||pair.before.x===1152)edges.push(pair);
    }
    return edges;
   });
   assert.ok(boundaries.some(edge=>edge.before.x===128));
   assert.ok(boundaries.some(edge=>edge.before.x===1152));
   for(const {before,after} of boundaries){
    assert.deepEqual(after,before,'zero delta leaves both position and direction unchanged');
    assert.equal(after.dir,after.x===128?1:-1);
   }
   if(once){
    const handoff=await page.evaluate(()=>gameState());
    assert.equal(handoff.state,'play');
    assert.deepEqual(handoff.landed,[]);
    assert.deepEqual(handoff.stars,[]);
   }
   const aiming=await page.evaluate(()=>{
    for(let i=0;i<600;i++){
     if(Math.abs(gameState().x-688)<14)return true;
     framePair();
    }
    return false;
   });
   assert.equal(aiming,true);
   await page.keyboard.press('Space');
   await page.evaluate(()=>{for(let i=0;i<35;i++)framePair()});
   const child=await page.evaluate(()=>gameState());
   assert.deepEqual(child.landed,[1]);
   assert.deepEqual(child.errors,[]);
   await page.close();
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
'''


class CraneCheckpointTest(unittest.TestCase):
    def test_duplicate_animation_timestamp_and_opt_in_demo(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        fixtures = [
            [once, page.page('小吊车', '', '', GAME.replace('DEMO_ONCE', json.dumps(once)))]
            for once in (False, True)
        ]
        result = subprocess.run(
            [node, '-e', RUN, str(playwright), str(chrome)],
            input=json.dumps(fixtures), text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
