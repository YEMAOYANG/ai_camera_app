"""Held arcade cues wait for classroom audio and discard presses made early."""
import base64
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import wave

from backend.content.textbook_interactive_narration import _helper
from courseware.kit import page
from courseware.tools import autoplay


GAME = r'''
K.ready({title:'听口令',sub:'拿取再送到'});
K.game(K.gameTemplates.arcade({
  levels:[{},{},{}],voiceLead:true,stepVoiceLead:true,
  cues:[{steps:['pickup','deliver'],praise:'praise'},{},{}]
},{
  controls:['right',['action','◎','拿取或交付']],
  backdrop:'#f9e8c6',validate(){},reset(){return {elapsed:0,moves:0};},goal:()=>2,draw(){},
  update(w,level,input,dt,feedback){
    w.elapsed+=dt;
    if(input.held('right'))w.moves++;
    if(input.press('action'))feedback.award(640,360);
  },
  pilot(){return {held:()=>false,press:key=>key==='action'};}
}));
'''

RUN = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2]});
 try{
  const p=await browser.newPage({viewport:{width:700,height:440},hasTouch:true});
  await p.addInitScript(()=>{
   if(window===parent)return;
   const queue=[];let now=1;
   requestAnimationFrame=fn=>queue.push(fn);
   window.step=n=>{for(let i=0;i<n;i++){now+=1000/60;for(const f of queue.splice(0))f(now);}};
   window.received=[];
   window.audioEvents=[];
   addEventListener('message',e=>{if(e.source===parent)received.push(e.data);});
   addEventListener('mira-narration-state',e=>audioEvents.push(e.detail));
  });
  await p.goto('data:text/html,<button>开始上课</button><iframe width="640" height="360" allow="autoplay *"></iframe>');
  const frame=p.locator('iframe');
  await frame.evaluate((node,html)=>{node.srcdoc=html;},JSON.parse(fs.readFileSync(0,'utf8')));
  const f=await (await frame.elementHandle()).contentFrame();
  const wait=(fn,arg)=>f.waitForFunction(fn,arg,{polling:20,timeout:4500});
  await wait(()=>typeof K==='object'&&K.game.current);
  await p.locator('button').tap();
  const send=async data=>{
   const n=await f.evaluate(()=>received.length);
   await frame.evaluate((node,data)=>node.contentWindow.postMessage(data,'*'),data);
   await wait(n=>received.length>n,n);
  };
  const visible=value=>send({type:'MIRA_NARRATION_VISIBILITY',visible:value});
  const set=state=>send({type:'SET_WIDGET_STATE',state});
  const step=n=>f.evaluate(n=>window.step(n),n);
  const read=()=>f.evaluate(()=>{
   const g=K.game.current;
   return {world:g.data.w,progress:g.data.progress,stars:g.stars,errors:K.errs,audioEvents};
  });
  const heard=(cue,status,count=1)=>wait(([cue,status,count])=>audioEvents.filter(
    e=>e.cueId===cue&&e.status===status).length>=count,[cue,status,count]);

  await visible(false);
  await set({demo:true,level:1});await step(140);
  assert.equal((await read()).progress,1);
  await set({demo:false,level:1});await step(900);
  let state=await read();
  assert.equal(state.world.elapsed,0,'the handoff may arrive well before the lesson stops speaking');
  assert.equal(state.progress,0);
  assert.deepEqual(state.stars,[]);
  assert.deepEqual(state.audioEvents.filter(e=>e.cueId),[]);

  await visible(true);await heard('pickup','playing');
  const action=f.getByRole('button',{name:'拿取或交付'});
  await step(2);
  assert.equal(await action.isDisabled(),true);
  const keyboardSurface=f.locator('#play');
  await keyboardSurface.evaluate(el=>{el.tabIndex=0;el.focus();});
  await p.keyboard.down('ArrowRight');await step(12);
  await heard('pickup','ready');await step(12);
  assert.equal((await read()).world.moves,0,'a key held during speech must not move the cart afterwards');
  await p.keyboard.up('ArrowRight');
  await p.keyboard.down('ArrowRight');await step(3);await p.keyboard.up('ArrowRight');
  assert.equal((await read()).world.moves,3);

  await action.tap();await step(1);
  await heard('deliver','playing');
  await visible(false);await step(900);
  assert.equal((await read()).progress,1);
  await visible(true);await visible(true);
  await heard('deliver','playing',2);
  await heard('deliver','ready');await step(2);
  assert.equal((await read()).audioEvents.filter(e=>e.cueId==='deliver'&&e.status==='playing').length,2);

  await f.getByRole('button',{name:'重听老师'}).focus();
  await p.keyboard.press('Space');
  await heard('deliver','playing',3);await step(3);
  assert.equal((await read()).progress,1,'Space on replay is not a delivery');
  await heard('deliver','ready',2);await step(2);
  await action.tap();await step(3);
  await heard('praise','playing');
  assert.equal(await f.locator('#g-next').count(),0);
  await heard('praise','ready');await step(100);
  assert.equal(await f.locator('#g-next').isVisible(),true);
  assert.deepEqual((await read()).errors,[]);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
'''


class ClassicCueHandoffTest(unittest.TestCase):
    def test_arcade_cues_wait_for_parent_and_retry_current_step(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        recording = io.BytesIO()
        with wave.open(recording, 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(bytes(12800))
        url = 'data:audio/wav;base64,' + base64.b64encode(recording.getvalue()).decode()
        html = page.page('听口令', _helper({cue: url for cue in ('pickup', 'deliver', 'praise')}), '', GAME)
        result = subprocess.run(
            [node, '-e', RUN, str(playwright), str(chrome)],
            input=json.dumps(html), text=True, capture_output=True, timeout=32,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
