"""Chrome regression for the existing catch and trace games with guided controls.

MIRA_DUI_GAME_FIXTURES points to the candidate HTML built without audio.
Tests exercise cue IDs and the clock gate using controlled playback events.
"""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from courseware.tools import autoplay


RUN = r"""
const assert=require('node:assert/strict');
const {join}=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const directory=process.argv[3];
async function check(browser,id){
  const p=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  const errors=[];
  p.on('pageerror',error=>errors.push(error.message));
  try{
    await p.addInitScript(()=>{
      const frames=[];
      let now=1;
      window.step=(n,stop)=>{
        for(let i=0;i<n;i++){
          for(const frame of frames.splice(0))frame(now);
          now+=1000/60;
          if(stop&&K.game.status().state===stop)return true;
        }
        return false;
      };
      requestAnimationFrame=frame=>frames.push(frame);
      window.heard=[];
      window.endCue=id=>dispatchEvent(new CustomEvent('mira-narration-state',{detail:{cueId:id,status:'ready'}}));
      window.miraNarrate=id=>heard.push(id);
      window.miraCancelNarration=()=>{};
      const drawImage=CanvasRenderingContext2D.prototype.drawImage;
      window.drawn=new Set();
      CanvasRenderingContext2D.prototype.drawImage=function(image,...args){
        if(image.src)drawn.add(image.src);
        return drawImage.call(this,image,...args);
      };
    });
    await p.route(/\/(?:rain|wind|flower|tree|bird|insect)\.png$/,route=>route.abort());
    await p.goto(pathToFileURL(join(directory,id+'.html')).href);
    const step=n=>p.evaluate(n=>window.step(n),n);
    const until=state=>p.evaluate(state=>window.step(7000,state),state);
    const read=()=>p.evaluate(()=>{
      const g=K.game.current,{world:w,round}=g.data;
      return {status:K.game.status(),stars:K.stars,score:g.score,round,
        caught:w?.caught??null,stroke:w?.stroke??null,progress:w?.s??null,y:w?.y??null,
        end:g.data.next,wins:K.log.filter(x=>x.startsWith('win:')),
        demos:K.log.filter(x=>x.startsWith('demo:action:')),errors:K.errs};
    });
    const send=async state=>{
      const log=await p.evaluate(()=>K.log.length);
      await p.evaluate(state=>postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
      await p.waitForFunction(n=>K.log.length>n,log,{polling:20});
    };
    const cue=key=>'dui-'+id+'-'+key;
    const end=async key=>{
      const id=cue(key);
      assert.equal(await p.evaluate(()=>heard.at(-1)),id);
      await p.evaluate(id=>endCue(id),id);
    };
    const clean=async()=>{
      const g=await read();
      assert.deepEqual([g.status.level,g.status.stars,g.stars,g.score,g.round],
        [1,[],0,{total:0,combo:0},0]);
    };
    for(const [width,height] of [[1280,720],[1000,563],[640,360]]){
      await p.setViewportSize({width,height});
      const b=await p.locator('#start-btn').boundingBox();
      assert.ok(b.width>=44&&b.height>=44);
    }
    await send({demo:true,level:1});
    assert.ok(await until('between'));
    const demo=await read();
    assert.deepEqual([demo.status.level,demo.stars,demo.score,demo.wins,demo.demos],
      [1,0,{total:0,combo:0},[],['demo:action:1']]);
    if(id==='p06')assert.equal(demo.caught,1);
    else assert.ok(demo.progress>280);
    await step(400);
    assert.deepEqual(await read(),demo);
    await send({demo:false,level:1});
    await clean();
    const before=await read();
    await step(90);
    assert.deepEqual(await read(),before,'the level clock waits for its recording');
    await end('level1-goal');
    await step(2);
    const replay=p.getByRole('button',{name:'重听老师'});
    const voice=await replay.boundingBox();
    assert.ok(voice.width>=44&&voice.height>=44);
    await replay.tap();
    await end('level1-goal');
    await step(2);
    for(const button of await p.locator('.g-template-pad button').all()){
      const b=await button.boundingBox();
      assert.ok(b.width>=44&&b.height>=44);
    }
    if(id==='p06'){
      assert.ok(await p.evaluate(()=>[...drawn].some(url=>url.includes('dui-backup-'))));
    }
    await p.evaluate(()=>{
      CanvasRenderingContext2D.prototype.fillText=()=>{};
      CanvasRenderingContext2D.prototype.strokeText=()=>{};
    });
    await p.addStyleTag({content:'#ready h1,#ready p,#gcard h1,#gcard p,#gcard button,#finish h1,#finish p,#finish button{color:transparent!important}'});
    if(process.env.MIRA_DUI_SCREENS)await p.screenshot({path:join(process.env.MIRA_DUI_SCREENS,id+'.png')});
    const cdp=await p.context().newCDPSession(p);
    const board=await p.locator('#gm').boundingBox();
    const touch=async(type,point)=>{
      const touchPoints=point?[{x:board.x+point[0]*board.width/1280,y:board.y+point[1]*board.height/720}]:[];
      await cdp.send('Input.dispatchTouchEvent',{type,touchPoints});
      await step(2);
    };
    const hold=async(key,frames)=>{
      await p.keyboard.down(key);await step(frames);await p.keyboard.up(key);await step(1);
    };
    const trace=async points=>{
      await touch('touchStart',points[0]);
      for(let i=1;i<points.length;i++){
        const [x,y]=points[i-1],[u,v]=points[i];
        const count=Math.ceil(Math.hypot(u-x,v-y)/17);
        for(let j=1;j<=count;j++){
          await touch('touchMove',[x+(u-x)*j/count,y+(v-y)*j/count]);
          await step(5);
        }
      }
      await touch('touchEnd');
    };
    if(id==='p06'){
      await hold('ArrowLeft',39);
      await step(185);
      assert.equal((await read()).score.total,0);
      assert.equal(await p.evaluate(()=>heard.at(-1)),cue('hint'));
      await step(310);
      assert.equal(await p.evaluate(()=>heard.at(-1)),cue('hint2'));
    }else{
      await p.getByRole('button',{name:'拿起或放下小车'}).tap();
      await step(2);
      await hold('ArrowLeft',27);
      assert.equal((await read()).progress,0);
      assert.ok(await p.evaluate(id=>heard.includes(id),cue('hint')));
    }

    for(let level=1;level<=3;level++){
      if(id==='p06'){
        for(let wave=0;wave<2;wave++){
          const {x,y,speed}=await p.evaluate(()=>{
            const {plan,round,world}=K.game.current.data;
            return {x:world.centers[plan.rounds[round].answer],y:world.y,speed:world.speed};
          });
          await touch('touchStart',[x,515]);
          await touch('touchEnd');
          await step(Math.ceil((570-y)/speed*60)+74);
          assert.ok((await read()).score.total>=100);
        }
      }else if(level===1){
        await hold('ArrowRight',88);
      }else{
        const plan=await p.evaluate(()=>K.game.current.data.world.paths.map(path=>path.points.map(p=>[p.x,p.y])));
        assert.equal(plan.length,level===2?3:6);
        if(level===2)assert.equal(await p.evaluate(()=>K.game.current.data.world.prefill.length),3);
        for(const points of plan)await trace(points);
      }
      await step(68);
      assert.equal((await read()).status.state,'between',id+' level '+level);
      await end('praise');
      await step(55);
      if(level<3){
        const button=p.locator('#g-next');
        const b=await button.boundingBox();
        assert.ok(b.width>=44&&b.height>=44);
        await button.tap();
        await end('level'+(level+1)+'-goal');
        await step(2);
      }
    }
    const done=await read();
    assert.equal(done.status.state,'done');
    assert.deepEqual(done.wins.map(x=>Number(x.split(':')[1])),[1,2,3]);
    assert.equal(done.stars,done.status.stars.reduce((sum,n)=>sum+n,0));
    assert.ok(done.score.total>0);
    const again=p.locator('#btn-again');
    const b=await again.boundingBox();
    assert.ok(b.width>=44&&b.height>=44);
    await again.tap();
    await clean();
    for(let run=0;run<2;run++){
      const before=(await read()).wins.length;
      await p.evaluate(()=>K.game.autoplay(true));
      assert.ok(await until('done'));
      const finish=await read();
      assert.deepEqual(finish.wins.slice(before).map(x=>Number(x.split(':')[1])),[1,2,3]);
      await again.tap();
      await clean();
    }
    assert.deepEqual((await read()).errors,[]);
    assert.deepEqual(errors,[]);
    console.log(id+': demo, cue gate, keyboard/touch, three manual levels, two bot clears and reset');
  }finally{await p.close();}
}
(async()=>{
  const browser=await chromium.launch({executablePath:process.argv[2]});
  try{for(const id of ['p06','p09'])await check(browser,id);}
  finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class DuiYunGameTests(unittest.TestCase):
    def test_guided_catch_and_trace_in_browser(self):
        directory = os.environ.get('MIRA_DUI_GAME_FIXTURES')
        if not directory:
            self.skipTest('set MIRA_DUI_GAME_FIXTURES to candidate test HTML')
        chrome = os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME)
        result = subprocess.run(
            [shutil.which('node'), '-e', RUN, str(autoplay._playwright_dir()), chrome, str(Path(directory))],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
