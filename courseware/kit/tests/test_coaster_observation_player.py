"""Check the observation checkpoint in a built cup game with its real media.

Set MIRA_COASTER_GAME_BUILD to the locally prepared and finished build.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from backend.content.courseware_observation import project_snapshot, scene_card
from courseware.tools import autoplay, game_audio


RUN = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const {media,pages,expected}=JSON.parse(fs.readFileSync(0,'utf8'));
const server=http.createServer((req,res)=>{
  const page=pages[req.url];
  if(page){
    res.setHeader('Content-Type','text/html; charset=utf-8');
    return res.end(page);
  }
  const asset=req.url.match(/^\/api\/classroom-media\/[a-z0-9-]+\/media\/([a-z0-9-]+\.(png|wav))$/)?.[1];
  if(asset&&fs.existsSync(path.join(media,asset))){
    res.setHeader('Content-Type',asset.endsWith('.wav')?'audio/wav':'image/png');
    return fs.createReadStream(path.join(media,asset)).pipe(res);
  }
  res.writeHead(404);res.end();
});

async function run(browser,scene){
  const p=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  const errors=[];
  p.on('pageerror',error=>errors.push(error.message));
  p.on('requestfailed',request=>errors.push(request.url()+': '+request.failure()?.errorText));
  try{
    await p.addInitScript(()=>{
      let now=1;
      const frames=[];
      window.requestAnimationFrame=callback=>frames.push(callback);
      window.step=(n,state)=>{
        for(let i=0;i<n;i++){
          now+=1000/60;
          for(const frame of frames.splice(0))frame(now);
          if(state&&K.game.status().state===state)return true;
        }
        return false;
      };
      window.reports=[];
      window.audioEvents=[];
      addEventListener('mira-activity-state-changed',()=>reports.push(miraActivityCheckpoint.capture()));
      addEventListener('mira-narration-state',e=>audioEvents.push([e.detail.cueId,e.detail.status]));
      const NativeAudio=window.Audio;
      window.Audio=class extends NativeAudio{
        constructor(src){super(src);this.playbackRate=3;}
      };
    });
    await p.goto('http://127.0.0.1:'+server.address().port+scene);
    await p.locator('#start-btn').tap();
    const step=n=>p.evaluate(n=>window.step(n),n);
    const until=state=>p.evaluate(state=>window.step(3800,state),state);
    const send=async state=>{
      const before=await p.evaluate(()=>K.log.length);
      await p.evaluate(state=>postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
      await p.waitForFunction(before=>K.log.length>before,before,{polling:20});
    };
    const read=()=>p.evaluate(()=>{
      const g=K.game.current;
      return {status:K.game.status(),stars:K.stars,progress:g.data.progress,total:g.data.total,
        snapshot:K.game.observation(),reports,wins:K.log.filter(e=>e.startsWith('win:')),
        demos:K.log.filter(e=>e.startsWith('demo:action:')),errors:K.errs};
    });
    const cueEnd=async(cue,count=1)=>{
      await p.waitForFunction(([cue,count])=>audioEvents.filter(e=>e[0]===cue&&e[1]==='ready').length>=count,
        [cue,count],{polling:20});
      assert.ok(await p.evaluate(cue=>audioEvents.some(e=>e[0]===cue&&e[1]==='playing'),cue));
    };
    const goal=scene==='/cup'?'firstTest':'roundGoal';
    await p.evaluate(()=>postMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true},'*'));
    await cueEnd(goal);
    await step(1);
    await p.getByRole('button',{name:'重听老师'}).tap();
    await cueEnd(goal,2);
    if(scene==='/circle'){
      assert.equal((await read()).snapshot,null);
      assert.deepEqual(errors,[]);
      return;
    }

    const noObservation=async count=>{
      const g=await read();
      assert.equal(g.snapshot,null);
      assert.equal(g.reports.length,count);
    };
    await send({demo:true,level:1});
    assert.ok(await until('between'));
    const demo=await read();
    assert.deepEqual([demo.progress,demo.total,demo.stars,demo.wins,demo.demos],
      [1,0,0,[],['demo:action:1']]);
    await step(320);
    assert.deepEqual(await read(),demo);
    await noObservation(0);
    await send({demo:false,level:1});
    const handed=await read();
    assert.deepEqual([handed.status.level,handed.status.auto,handed.stars,handed.total,handed.progress],
      [1,false,0,0,0]);
    await cueEnd(goal,3);
    await step(2);

    async function place(){
      for(let i=0;i<18;i++){
        const delta=await p.evaluate(()=>{
          const center=id=>{const r=document.getElementById(id).getBoundingClientRect();return r.x+r.width/2;};
          return (center('game-target')-center('game-player'))/K.scale;
        });
        if(Math.abs(delta)<16){
          await p.getByRole('button',{name:'把空杯轻放在垫子上'}).tap();
          await step(21);
          return;
        }
        const key=delta<0?'ArrowLeft':'ArrowRight';
        await p.keyboard.down(key);
        await step(Math.max(1,Math.min(42,Math.floor(Math.abs(delta)/4.8))));
        await p.keyboard.up(key);
      }
      assert.fail('the touch drop could not reach the selected mat');
    }
    for(let level=1;level<=3;level++){
      for(let trial=1;trial<=2;trial++){
        await place();
        const result=await read();
        assert.equal(result.status.auto,false);
        assert.equal(result.progress,trial);
        assert.equal(result.status.level,level);
        await noObservation(0);
        await step(100);
      }
      if(level<3){
        await noObservation(0);
        await p.locator('#g-next').tap();
        await step(2);
      }
    }
    const finished=await read();
    assert.equal(finished.status.state,'done');
    assert.equal(finished.stars,9);
    assert.deepEqual(finished.snapshot,expected);
    assert.deepEqual(finished.reports,[expected]);
    assert.equal(await p.locator('.coaster-observation canvas').count(),1);
    await p.locator('#btn-again').tap();
    await noObservation(1);
    assert.equal((await read()).stars,0);
    await step(2);
    await place();
    await noObservation(1);
    await p.evaluate(()=>K.game.autoplay(true));
    assert.ok(await until('done'));
    await noObservation(1);
    await p.locator('#btn-again').tap();
    assert.ok(await until('done'));
    await noObservation(1);
    assert.equal(await p.locator('.coaster-observation').count(),0);
    assert.deepEqual((await read()).errors,[]);
    assert.deepEqual(errors,[]);
  }finally{await p.close();}
}

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({executablePath:process.argv[2]});
  try{await run(browser,'/circle');await run(browser,'/cup');}
  finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
"""


class CoasterObservationPlayerTest(unittest.TestCase):
    def test_finished_player_publishes_only_six_manual_trials(self):
        built = os.environ.get('MIRA_COASTER_GAME_BUILD')
        if not built:
            self.skipTest('set MIRA_COASTER_GAME_BUILD to the finished candidate build')
        root = Path(built)
        body = json.loads((root / 'body.json').read_text())
        game_audio.verify_recordings(body)
        pages = {s['id'].replace('scene-', '/', 1): s['content']['html']
                 for s in body['scenes'] if s['type'] == 'interactive'}
        expected = dict(schemaVersion='mira.game.observation.v1', sceneId='scene-cup', kind='simulation',
                        levels=[dict(level=i, trials=[dict(trialId='before', top=top, side=side),
                                                       dict(trialId='after', top='covers', side='flat')])
                                for i, (top, side) in enumerate([('extends', 'flat'), ('covers', 'raised'),
                                                                 ('extends', 'raised')], 1)])
        scene = next(s for s in body['scenes'] if s['id'] == 'scene-cup')
        media = root / 'media'
        projected = project_snapshot(scene_card(scene), scene['id'], expected)
        images = [trial[view]['image'].rsplit('/', 1)[-1]
                  for level in projected['levels'] for trial in level['trials'] for view in ('top', 'side')]
        self.assertEqual(len(images), 12)
        for name in images:
            self.assertEqual(name, f"pic-{hashlib.sha256((media / name).read_bytes()).hexdigest()}.png")
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        result = subprocess.run(
            [shutil.which('node'), '-e', RUN, str(autoplay._playwright_dir()), chrome],
            input=json.dumps(dict(pages=pages, media=str(media), expected=expected)),
            text=True, capture_output=True, timeout=95,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print('Coaster: original WAV replay, six manual trials with twelve views, one checkpoint; '
              'demo, partial, mixed and automatic runs exported nothing.')
