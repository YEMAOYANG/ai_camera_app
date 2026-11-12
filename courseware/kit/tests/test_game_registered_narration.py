"""Registered game recordings play after the classroom grants the page audio."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

from backend.content.textbook_interactive_narration import _helper
from courseware.tools import autoplay, build


FIXTURE = Path(__file__).parents[2] / 'tools/tests/fixtures/build_lesson'
CUES = ('goal', 'early', 'early-repeat', 'wrong-door', 'wrong-door-repeat', 'praise')
GAME = r'''
K.ready({title:'回教室',sub:'听铃',img:'__IMG:picture__'});
K.game({
  demoOnce:true,winPause:0,
  narration:[{goal:'goal',hint:'early',hint2:'early-repeat',praise:'praise',
              missCues:{wrongDoor:['wrong-door','wrong-door-repeat']}}],
  reset(g){g.data={elapsed:0}},
  autopilot(g){g.taps.push({key:true})},
  update(g,dt){
    g.data.elapsed+=dt;
    if(g.taps.some(tap=>tap.key)){
      if(!g.demoAction())g.win();
    }else if(g.taps.length){
      g.miss(g.taps[0].x>640?'wrongDoor':undefined);
    }
  },
});
'''

RUN = r'''
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const html=JSON.parse(fs.readFileSync(0,'utf8'));
const server=http.createServer((req,res)=>{
 const recording=req.url.match(/^\/api\/classroom-media\/game-audio\/media\/(recording-[a-f0-9]{64}\.wav)$/);
 if(recording){
  res.setHeader('content-type','audio/wav');
  res.end(fs.readFileSync(path.join(process.argv[3],recording[1])));
 }else if(req.url==='/game'){
  res.setHeader('content-type','text/html; charset=utf-8');res.end(html);
 }else if(req.url==='/'){
  res.setHeader('content-type','text/html; charset=utf-8');
  res.end('<button>开始上课</button><iframe src="/game" width="640" height="360" allow="autoplay *"></iframe>');
 }else{res.writeHead(404);res.end();}
});
(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({executablePath:process.argv[2]});
 try{
  const page=await browser.newPage({hasTouch:true});
  page.setDefaultTimeout(4500);
  await page.addInitScript(()=>{
   let now=1;const queue=[];
   window.requestAnimationFrame=fn=>queue.push(fn);
   window.step=n=>{for(let i=0;i<n;i++){now+=1000/60;for(const fn of queue.splice(0))fn(now);}};
   window.cues=[];
   addEventListener('mira-narration-state',e=>cues.push([e.detail.cueId,e.detail.status]));
  });
  await page.goto('http://127.0.0.1:'+server.address().port);
  await page.getByRole('button',{name:'开始上课'}).tap();
  const frame=page.frames()[1];
  const send=async (message,ack)=>{
   await page.evaluate(message=>document.querySelector('iframe').contentWindow.postMessage(message,'*'),message);
   await frame.waitForFunction(ack,undefined,{polling:20,timeout:4500});
  };
  const step=n=>frame.evaluate(n=>window.step(n),n);
  const elapsed=()=>frame.evaluate(()=>K.game.current.data.elapsed);
  const end=(id,count=1)=>frame.waitForFunction(
   ([id,count])=>cues.filter(event=>event[0]===id&&event[1]==='ready').length===count,
   [id,count],{polling:20,timeout:3000});
  await send({type:'SET_WIDGET_STATE',state:{demo:true}},()=>K.game.current.autoLoop);
  await step(4);
  assert.equal(await frame.evaluate(()=>K.game.status().state),'between');
  await send({type:'SET_WIDGET_STATE',state:{demo:false,level:1}},()=>!K.game.current.autoLoop);
  await step(900);
  assert.equal(await elapsed(),0,'game clock must wait through teacher speech');
  assert.deepEqual(await frame.evaluate(()=>cues.filter(event=>event[0])),[]);
  await send({type:'MIRA_NARRATION_VISIBILITY',visible:true},()=>cues.some(event=>event[0]==='goal'));
  await step(3);
  assert.equal(await elapsed(),0,'game clock must also wait for the recording');
  await end('goal');
  await step(1);
  const tap=x=>frame.locator('#play').tap({position:{x,y:220}});
  await tap(140);await step(1);await end('early');
  await tap(475);await step(1);await end('wrong-door-repeat');
  const replay=frame.getByRole('button',{name:'重听老师'});
  await replay.tap();
  await end('goal',2);
  await send({type:'SET_WIDGET_STATE',state:{restart:true}},()=>K.game.status().levelMisses===0);
  await end('goal',3);
  await tap(475);await step(1);await end('wrong-door');
  await tap(475);await step(1);await end('wrong-door-repeat',2);
  await tap(140);await step(1);await end('early-repeat');
  await page.keyboard.press('Space');await step(2);
  assert.equal(await frame.locator('#finish').count(),0);
  await end('praise');await step(1);
  assert.equal(await frame.evaluate(()=>K.game.status().state),'done');
  assert.deepEqual(await frame.evaluate(()=>K.errs),[]);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>server.close());
'''


class GameRegisteredNarrationTest(unittest.TestCase):
    def test_child_waits_for_classroom_and_hears_the_contextual_cue(self):
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            playwright = autoplay._playwright_dir()
        except RuntimeError:
            playwright = None
        if not node or not playwright or not chrome.is_file():
            self.skipTest('node, playwright-core and Chrome are required')
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'lesson'
            output = Path(directory) / 'build'
            shutil.copytree(FIXTURE, source)
            lesson_path = source / 'lesson.json'
            lesson = json.loads(lesson_path.read_text())
            lesson['audio'] = {}
            for scene in lesson['scenes']:
                scene.pop('startImage', None)
            for index, cue_id in enumerate(CUES):
                recording = source / 'assets' / f'{cue_id}.wav'
                with wave.open(str(recording), 'wb') as audio:
                    audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                    audio.writeframes(bytes([index, 0]) * 2400)
                lesson['audio'][cue_id] = {
                    'file': f'assets/{recording.name}',
                    'sha256': hashlib.sha256(recording.read_bytes()).hexdigest(),
                }
            lesson_path.write_text(json.dumps(lesson))
            (source / 'pages/play.html').write_text(_helper({cue: f'__AUDIO:{cue}__' for cue in CUES}))
            (source / 'pages/play.js').write_text(GAME)
            draft = build.prepare(source, output, stage_id='game-audio')
            html = next(scene['content']['html'] for scene in draft['body']['scenes']
                        if scene['type'] == 'interactive')
            result = subprocess.run(
                [node, '-e', RUN, str(playwright), str(chrome), str(output / 'media')],
                input=json.dumps(html), text=True, capture_output=True, timeout=25,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
