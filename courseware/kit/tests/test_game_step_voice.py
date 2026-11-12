"""Step narration can hold the game clock without changing older cue users."""
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
window.miraNarrate=id=>{heard.push(id);cueEvent(id,'playing');};
K.ready({title:'听指令',sub:'两步完成'});
K.game(K.gameTemplates.arcade({levels:[{},{},{}],voiceLead:true,stepVoiceLead:OPT_IN,
  cues:[{steps:['pickup','deliver'],praise:'praise'},{},{}]}, {
  controls:[['action','▣','操作']],backdrop:'#fff0d0',validate(){},reset(){return {elapsed:0};},goal:()=>2,draw(){},
  update(world,level,input,dt,feedback){world.elapsed+=dt;if(input.press('action'))feedback.award(640,360);}
}));'''


RUN = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const html=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
 const browser=await chromium.launch({executablePath:process.argv[2]});
 try{
  for(let index=0;index<html.length;index++){
   const p=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
   await p.evaluate(()=>{
    const queue=[];let now=1;
    window.requestAnimationFrame=fn=>queue.push(fn);
    window.step=(n)=>{for(let i=0;i<n;i++){now+=1000/60;for(const fn of queue.splice(0))fn(now);}};
   });
   await p.setContent(html[index]);
   await p.locator('#start-btn').tap();
   await p.evaluate(()=>{cueEvent('pickup','ready');step(1);});
   await p.keyboard.press('Space');
   const afterPickup=await p.evaluate(()=>{step(1);return K.game.current.data.w.elapsed;});
   assert.deepEqual(await p.evaluate(()=>heard),['pickup','deliver']);
   await p.keyboard.press('Space');
   await p.evaluate(()=>step(30));
   const next=await p.evaluate(()=>({progress:K.game.current.data.progress,elapsed:K.game.current.data.w.elapsed}));
   if(index===0){
    assert.equal(next.progress,1);
    assert.equal(next.elapsed,afterPickup);
    await p.evaluate(()=>cueEvent('deliver','ready'));
    await p.keyboard.press('Space');
    await p.evaluate(()=>step(1));
    assert.equal(await p.evaluate(()=>K.game.current.data.progress),2);
   }else{
    assert.equal(next.progress,2,'older step cue callers can keep acting while it plays');
   }
   assert.deepEqual(await p.evaluate(()=>K.errs),[]);
   await p.close();
  }
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


class GameStepVoiceTest(unittest.TestCase):
    def test_step_cue_pauses_only_when_opted_in(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        fixtures = [page.page('听指令', '', '', JS.replace('OPT_IN', flag)) for flag in ('true', 'false')]
        result = subprocess.run([node, '-e', RUN, str(playwright), str(chrome)],
                                input=json.dumps(fixtures), text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
