"""Run the staged preparation games with real audio, touch and image failures.

Set MIRA_PREPARATION_GAME_BUILD to the directory produced by build.prepare.
The directory must contain draft.json and media from the candidate and its
registered recordings.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from courseware.tools import autoplay


RUN = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const path=require('node:path');
const {chromium}=require(process.argv[1]+'/node_modules/playwright-core');
const {pages,media,screens}=JSON.parse(fs.readFileSync(0,'utf8'));
const backups=Object.fromEntries(Object.entries(pages).map(([id,html])=>{
  const metadata=JSON.parse(html.match(/<script id="prep-picture-fallbacks" type="application\/json">([^<]+)<\/script>/)[1]);
  return [id,Object.values(metadata).map(value=>value.src)];
}));
const allBackups=new Set(Object.values(backups).flat());
const types={'.png':'image/png','.wav':'audio/wav'};
const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  const [,kind,id]=url.pathname.split('/');
  if(kind==='outer'&&pages[id]){
    res.setHeader('Content-Type','text/html; charset=utf-8');
    return res.end('<style>body{margin:0}iframe{display:block;border:0}</style><iframe width="640" height="360" allow="autoplay *" src="/game/'+id+url.search+'"></iframe>');
  }
  if(kind==='game'&&pages[id]){
    res.setHeader('Content-Type','text/html; charset=utf-8');
    return res.end(pages[id]);
  }
  const file=url.pathname.match(/^\/api\/classroom-media\/[a-z0-9-]+\/media\/([a-z0-9-]+\.(png|wav))$/)?.[1];
  const referer=new URL(req.headers.referer||'http://localhost');
  if(file&&(!file.endsWith('.png')||!referer.searchParams.has('fault')||allBackups.has(url.pathname))){
    const local=path.join(media,file);
    if(fs.existsSync(local)){
      res.setHeader('Content-Type',types[path.extname(file)]);
      return fs.createReadStream(local).pipe(res);
    }
  }
  res.writeHead(404);res.end();
});

const targets={leftFar:[424,396],rightNear:[989,523],centerFar:[716,388],rightFar:[991,390],stack:[424,387]};
const countStars=stars=>stars.reduce((sum,n)=>sum+n,0);

async function verify(browser,id){
  const page=await browser.newPage({viewport:{width:640,height:360},hasTouch:true});
  page.setDefaultTimeout(6000);
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  try{
    await page.addInitScript(()=>{
      if(window===parent)return;
      let now=1;
      const frames=[];
      window.requestAnimationFrame=frame=>frames.push(frame);
      window.step=(count,until)=>{
        for(let i=0;i<count;i++){
          now+=1000/60;
          for(const frame of frames.splice(0))frame(now);
          if(until&&K.game.status().state===until)return true;
        }
        return false;
      };
      window.cues=[];
      addEventListener('mira-narration-state',e=>cues.push([e.detail.cueId,e.detail.status]));
      const NativeAudio=window.Audio;
      window.Audio=class extends NativeAudio{
        constructor(src){super(src);this.playbackRate=3;}
      };
      window.pictures=new Set();
      const context=CanvasRenderingContext2D.prototype;
      const drawImage=context.drawImage;
      context.drawImage=function(image,...args){
        if(image.src)window.pictures.add(image.src);
        return drawImage.call(this,image,...args);
      };
      if(location.search.includes('fault')){
        context.fillText=()=>{};
        context.strokeText=()=>{};
      }
    });
    const address='http://127.0.0.1:'+server.address().port;
    await page.goto(address+'/outer/'+id);
    let game=page.frames()[1];
    await game.waitForFunction(()=>K.$('#ready img')?.naturalWidth>0,undefined,{polling:25});
    for(const [width,height] of [[1280,720],[1000,563],[640,360]]){
      await page.setViewportSize({width,height});
      await page.locator('iframe').evaluate((el,[w,h])=>{el.width=w;el.height=h;},[width,height]);
      const b=await game.locator('#start-btn').boundingBox();
      assert.ok(b.width>=44&&b.height>=44,id+' start control at '+width);
    }
    await page.goto(address+'/outer/'+id+'?fault');
    game=page.frames()[1];
    await game.addStyleTag({content:'#hud .chip,#stars,#ready h1,#ready p,#ready button,#gcard h1,#gcard p,#gcard button,#finish h1,#finish p,#finish button{color:transparent!important}'});
    await game.waitForFunction(urls=>{
      const cover=K.$('#ready img');
      return cover?.naturalWidth>0&&urls.includes(new URL(cover.src).pathname);
    },backups[id],{polling:25});
    await game.locator('#start-btn').tap();
    const step=n=>game.evaluate(n=>window.step(n),n);
    const until=async state=>assert.ok(await game.evaluate(state=>window.step(5000,state),state),id+' '+state);
    const send=async state=>{
      const start=await game.evaluate(()=>K.log.length);
      await page.locator('iframe').evaluate((el,state)=>el.contentWindow.postMessage({type:'SET_WIDGET_STATE',state},'*'),state);
      await game.waitForFunction(start=>K.log.length>start,start,{polling:20});
    };
    const setVisibility=visible=>page.locator('iframe').evaluate((el,visible)=>
      el.contentWindow.postMessage({type:'MIRA_NARRATION_VISIBILITY',visible},'*'),visible);
    const read=()=>game.evaluate(()=>{
      const g=K.game.current,d=g.data;
      return {status:K.game.status(),score:{...g.score},stars:K.stars,hud:K.$('#star-n').textContent,
        dots:K.$$('#dots i').map(i=>i.className),phase:d.phase??null,age:d.age??d.elapsed??null,
        items:d.items?.map(item=>({key:item.supply.key,target:item.target,x:item.x,y:item.y,placed:item.placed})),
        side:d.classSide, x:d.x,y:d.y,listener:d.listener,sequence:d.sequence,
        wins:K.log.filter(s=>s.startsWith('win:')),
        demos:K.log.filter(s=>s.startsWith('demo:action:')),errors:K.errs};
    });
    const cueCount=key=>game.evaluate(id=>cues.filter(e=>e[0]===id&&e[1]==='ready').length,'prep-'+id+'-'+key);
    const heard=new Set();
    const cue=async(key,before)=>{
      const name='prep-'+id+'-'+key;
      await game.waitForFunction(([name,before])=>cues.filter(e=>e[0]===name&&e[1]==='ready').length>before,[name,before],{polling:20});
      assert.ok(await game.evaluate(name=>cues.some(e=>e[0]===name&&e[1]==='playing'),name),name+' played');
      heard.add(name);
    };
    const reset=async()=>{
      const g=await read();
      assert.deepEqual([g.status.state,g.status.level,g.status.stars,g.stars,g.hud,g.score,g.dots],
        ['play',1,[],0,'0',{total:0,combo:0},['cur','','']],id+' clean start');
    };

    await send({demo:true,level:1});
    await until('between');
    const demo=await read();
    assert.deepEqual([demo.status.level,demo.status.stars,demo.stars,demo.score,demo.wins,demo.demos],
      [1,[],0,{total:0,combo:0},[],['demo:action:1']],id+' single demonstration');
    if(id==='g02')assert.ok(demo.x<350&&demo.y<350);
    if(id==='g04')assert.deepEqual(demo.items.filter(i=>i.placed).map(i=>i.key),['book']);
    if(id==='g06')assert.equal(demo.phase,'waiting');
    await step(400);
    assert.deepEqual(await read(),demo,id+' stays at first action');

    await send({demo:false,level:1});
    await step(180);
    await reset();
    assert.equal((await read()).age??0,0,id+' waits for classroom audio permission');
    assert.deepEqual(await game.evaluate(()=>cues.filter(e=>e[1]==='playing')),[]);
    await setVisibility(true);
    await cue('goal',0);
    await step(2);
    const voice=game.getByRole('button',{name:'重听老师'});
    const box=await voice.boundingBox();
    assert.ok(box.width>=44&&box.height>=44);
    await voice.tap();
    await cue('goal',1);
    assert.ok(await game.evaluate(urls=>pictures.size>=3&&[...pictures].every(src=>urls.includes(new URL(src).pathname)),backups[id]));
    if(screens)await page.screenshot({path:path.join(screens,id+'-image-fallback.png')});

    const cdp=await page.context().newCDPSession(page);
    const board=await game.locator('#gm').boundingBox();
    const touch=async(type,point)=>{
      const touchPoints=point?[{x:board.x+point[0]*board.width/1280,y:board.y+point[1]*board.height/720}]:[];
      await cdp.send('Input.dispatchTouchEvent',{type,touchPoints});
      await step(2);
    };
    const slide=async(from,to,settle=0)=>{
      await touch('touchStart',from);
      await touch('touchMove',to);
      await touch('touchEnd');
      await step(settle);
    };
    const door=async(x,n)=>{
      await touch('touchStart',[x,292]);
      await step(n);
      await touch('touchEnd');
    };
    for(const key of ['hint','hint2']){
      const count=await cueCount(key);
      if(id==='g02')await door(988,2);
      else if(id==='g04'){
        const book=(await read()).items[0];
        await slide([book.x,book.y],[727,540],55);
      }else await slide([640,494],[640,380]);
      await cue(key,count);
    }
    if(id==='g02'){
      const count=await cueCount('goal');
      await send({restart:true});
      await cue('goal',count);
      await step(160);
      for(const key of ['door-hint','door-hint2']){
        const count=await cueCount(key);
        await door(292,160);
        await cue(key,count);
      }
    }

    for(let level=1;level<=3;level++){
      const praise=await cueCount('praise');
      const g=await read();
      assert.equal(g.status.auto,false);
      assert.equal(g.status.level,level);
      if(id==='g02'){
        await step(320);
        await door(g.side?988:292,150);
      }else if(id==='g04'){
        for(const item of g.items)await slide([item.x,item.y],targets[item.target],65);
      }else{
        await step(150*g.sequence.length);
        await slide([640,494],[640,380],100);
        assert.equal((await read()).phase,'speak');
        await slide([640,494],[g.listener?810:470,494],70);
      }
      await cue('praise',praise);
      await step(100);
      if(level<3){
        const next=game.locator('#g-next');
        const bounds=await next.boundingBox();
        assert.ok(bounds.width>=44&&bounds.height>=44);
        const key=level===1?'goal':'challenge', count=await cueCount(key);
        await next.tap();
        await cue(key,count);
      }
    }
    const finish=await read();
    assert.equal(finish.status.state,'done');
    assert.deepEqual(finish.wins.map(win=>Number(win.split(':')[1])),[1,2,3]);
    assert.equal(finish.stars,countStars(finish.status.stars));
    assert.equal(finish.hud,String(finish.stars));
    assert.ok(finish.score.total>=300);
    assert.match(await game.locator('#finish p').textContent(),new RegExp('得分 '+finish.score.total));
    assert.ok(await game.locator('#finish .prep-reward').evaluate(image=>image.naturalWidth>0));
    assert.equal(heard.size,id==='g02'?7:5);
    const again=game.locator('#btn-again');
    const bounds=await again.boundingBox();
    assert.ok(bounds.width>=44&&bounds.height>=44);
    await again.tap();
    await reset();
    for(let run=0;run<2;run++){
      await game.evaluate(()=>K.game.autoplay(true));
      const before=(await read()).wins.length;
      await until('done');
      const final=await read();
      assert.deepEqual(final.wins.slice(before).map(win=>Number(win.split(':')[1])),[1,2,3]);
      assert.equal(final.stars,countStars(final.status.stars));
      await again.tap();
      await reset();
    }
    assert.deepEqual((await read()).errors,[]);
    assert.deepEqual(errors,[]);
    console.log(id+': '+heard.size+' WAV cues, three touch-cleared levels without primary images, two bot clears and clean replay');
  }finally{await page.close();}
}

(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const browser=await chromium.launch({executablePath:process.argv[2]});
  try{for(const id of Object.keys(pages))await verify(browser,id);}
  finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
"""


class LearningPreparationGameTests(unittest.TestCase):
    def test_real_cues_touch_and_fallback_in_prepared_games(self):
        built = os.environ.get('MIRA_PREPARATION_GAME_BUILD')
        if not built:
            self.skipTest('set MIRA_PREPARATION_GAME_BUILD to a prepared candidate')
        root = Path(built)
        node = shutil.which('node')
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        self.assertTrue(node and chrome.is_file(), 'node and Chrome are required')
        draft = json.loads((root / 'draft.json').read_text())
        pages = {s['id'].removeprefix('scene-'): s['content']['html']
                 for s in draft['body']['scenes'] if s['type'] == 'interactive'}
        self.assertEqual(set(pages), {'g02', 'g04', 'g06'})
        for html in pages.values():
            without_svg_namespace = html.replace('http://www.w3.org/2000/svg', '')
            self.assertIsNone(re.search(r'(?:https?://|data:|file:|blob:)', without_svg_namespace))
        result = subprocess.run(
            [node, '-e', RUN, str(autoplay._playwright_dir()), str(chrome)],
            input=json.dumps(dict(pages=pages, media=str(root / 'media'),
                                  screens=os.environ.get('MIRA_PREPARATION_GAME_SCREENS'))),
            capture_output=True, text=True, timeout=155,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout, end='')
