"""Shared real-time mini-game engine for interactive pages.

A page opts in by calling ``K.game({...})`` in its script; ``page.page`` then ships
this engine inside the kit. The engine owns one full-stage canvas (1280x720),
the frame loop, pointer and keyboard input, levels, lives, stars, particles,
banners and speech bubbles, the level and retry cards, and an autopilot. The
autopilot lets the teacher's ``widget_setState`` ``{demo: true}`` play the game
in front of the child (with ``demoOnce`` the engine starts on level 1 and holds
the result of the first successful action; legacy demos loop), and lets a play check finish
every level through ``K.game.autoplay(true)`` and ``K.game.status()``.

Teacher state keys: ``demo`` (bool), ``level`` (1-based, restarts that level),
``restart`` (bool, restarts the current level), ``pause`` (bool). Anything else is
passed to the page's own ``onState(g, state)``.

Custom mechanics may opt in to prerecorded ``narration`` with one cue map
per level (``goal``, ``hint``, ``hint2``, ``praise``). The replay button repeats
the goal. Goals and praise hold the play clock until the classroom permits
playback and the clip ends. A level can specify ``missCues`` as
``{reason: [firstCue, repeatCue]}`` for pages that call ``g.miss(reason)``.
Use ``g.demoAction()`` after a successful demonstration action to hold the
result without awarding stars. It returns false during child play and G6.
Direct games may opt in to ``score: true`` and call ``g.awardPoint()`` for each
successful action. The engine tracks the score and combo across a level,
shows them in the standard HUD, and appends the total to the finish card.

An optional ``observation`` config declares a ``sceneId`` and a ``trials`` map
of trial IDs to ``{top: [enum, ...], side: [enum, ...]}``. On a real child action,
``g.recordObservation(id, {top, side})`` records the first valid result for
that trial in the current level. At finish, ``K.game.observation()`` returns a
detached snapshot and ``mira-game-observation-ready`` fires in the page. It
exports simulated observations only, without scores, identities or upload.
Autoplay, teacher demos, unfinished and partial runs do not export a snapshot.
"""

GAME_CSS = r"""
#cv{touch-action:none}
#gm{position:absolute;left:0;top:0;width:1280px;height:720px;z-index:0;touch-action:none}
.g-anchor{position:absolute;pointer-events:none;z-index:4;border-radius:22px}
.g-replay-cue{position:absolute;top:86px;right:24px;z-index:8;width:94px;height:94px;min-width:94px;padding:0;background:#294c42;color:#fff4d8;border:3px solid #f5d091;box-shadow:0 5px 0 #18312a;touch-action:manipulation}
.g-replay-cue[hidden]{display:none}
.g-replay-cue:focus-visible{outline:4px solid #f5d091;outline-offset:3px}
.g-replay-cue svg{width:54px;height:54px;vertical-align:middle}
#cv .g-template-pad{position:absolute;left:22px;bottom:19px;display:grid;gap:9px;grid-template-columns:repeat(2,94px);z-index:7}
#cv .g-template-pad[hidden]{display:none}
#cv .g-template-pad button{width:94px;height:94px;min-width:94px;padding:0;font-size:43px;background:#294c42;border:3px solid #f4cf8e;box-shadow:0 4px 0 #1b3830;touch-action:none}
#cv .g-template-pad button:disabled{cursor:default}
.g-template-map{display:flex;justify-content:center;gap:12px;margin:8px 0 15px}
.g-template-map i{width:26px;height:26px;border-radius:50%;background:#c3dcd0;border:3px solid #4e806b}
.g-template-map i:first-child{background:#f4ca79}
#hud .g-run-score{padding:0 18px;color:#355749}
#gcard{position:absolute;left:0;top:0;right:0;bottom:0;z-index:20;background:rgba(255,238,196,.86);display:flex;align-items:center;justify-content:center;transition:opacity .35s}
#gcard.gone{opacity:0;visibility:hidden;pointer-events:none}
#gcard .card{background:#fff;border:4px solid var(--line);border-radius:40px;padding:34px 70px 40px;text-align:center;box-shadow:0 20px 44px rgba(120,80,30,.24)}
#gcard h1{font-size:58px;color:var(--ink2);margin-top:4px}
#gcard p{font-size:30px;margin:12px 0 18px;color:var(--ink)}
.gstars{font-size:72px;line-height:1;letter-spacing:10px;margin:0 0 22px}
.gstars b{color:#E8DCC4}
.gstars b.on{color:#FFC531;text-shadow:0 4px 0 #D98B00}
"""

GAME_JS = r"""
K.FONT="'PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans SC',sans-serif";
K.sfx.pop=function(){tone(660,0,0.07,'square',0.05)};
K.sfx.coin=function(){tone(988,0,0.08,'square',0.06);tone(1319,0.07,0.16,'square',0.06)};
K.sfx.jump=function(){tone(330,0,0.08,'triangle',0.16);tone(494,0.06,0.12,'triangle',0.14)};
K.sfx.splash=function(){tone(180,0,0.25,'sawtooth',0.05);tone(120,0.08,0.3,'sine',0.12)};
K.sfx.buzz=function(){tone(150,0,0.32,'sawtooth',0.06);tone(157,0,0.32,'sawtooth',0.05)};
K.sfx.whoosh=function(){tone(700,0,0.12,'sine',0.05);tone(420,0.05,0.14,'sine',0.04)};
K.draw={
 rr:function(c,x,y,w,h,r){r=Math.min(r,w/2,h/2);c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath()},
 circle:function(c,x,y,r){c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fill()},
 star:function(c,x,y,r,color){c.save();c.translate(x,y);c.beginPath();for(var i=0;i<10;i++){var q=i%2?r*0.45:r,a=-Math.PI/2+i*Math.PI/5;c.lineTo(Math.cos(a)*q,Math.sin(a)*q)}c.closePath();c.fillStyle=color||'#FFC531';c.fill();c.restore()},
 heart:function(c,x,y,s,on){c.save();c.translate(x,y);c.beginPath();c.moveTo(0,s*0.9);c.bezierCurveTo(-s*1.6,-s*0.1,-s*0.7,-s*1.3,0,-s*0.45);c.bezierCurveTo(s*0.7,-s*1.3,s*1.6,-s*0.1,0,s*0.9);c.closePath();c.fillStyle=on?'#FF5A6E':'rgba(255,248,231,.85)';c.fill();c.lineWidth=3;c.strokeStyle=on?'#C22E45':'rgba(74,47,27,.35)';c.stroke();c.restore()},
 cloud:function(c,x,y,s){c.save();c.translate(x,y);c.scale(s,s);c.fillStyle='rgba(255,255,255,.92)';[[0,0,34],[30,-14,30],[58,0,28],[28,8,30],[-28,6,24]].forEach(function(p){K.draw.circle(c,p[0],p[1],p[2])});c.restore()},
 apple:function(c,x,y,r,rot){c.save();c.translate(x,y);c.rotate(rot||0);var gr=c.createRadialGradient(-r*0.35,-r*0.4,r*0.15,0,0,r*1.15);gr.addColorStop(0,'#FF8270');gr.addColorStop(0.6,'#E53D2F');gr.addColorStop(1,'#B3241A');c.fillStyle=gr;c.beginPath();c.moveTo(0,-r*0.72);c.bezierCurveTo(r*0.95,-r*1.12,r*1.22,r*0.35,r*0.32,r*0.92);c.quadraticCurveTo(0,r*1.02,-r*0.32,r*0.92);c.bezierCurveTo(-r*1.22,r*0.35,-r*0.95,-r*1.12,0,-r*0.72);c.fill();c.strokeStyle='#6B3E1F';c.lineWidth=r*0.14;c.lineCap='round';c.beginPath();c.moveTo(0,-r*0.68);c.quadraticCurveTo(r*0.08,-r,r*0.18,-r*1.18);c.stroke();c.fillStyle='#4CAF50';c.beginPath();c.ellipse(r*0.46,-r*1.02,r*0.38,r*0.17,-0.5,0,Math.PI*2);c.fill();c.fillStyle='rgba(255,255,255,.55)';c.beginPath();c.ellipse(-r*0.4,-r*0.25,r*0.16,r*0.28,0.5,0,Math.PI*2);c.fill();c.restore()},
 text:function(c,s,x,y,size,color,o){o=o||{};c.font=(o.weight||800)+' '+size+'px '+K.FONT;c.textAlign=o.align||'center';c.textBaseline='middle';if(o.stroke){c.lineJoin='round';c.lineWidth=o.strokeWidth||8;c.strokeStyle=o.stroke;c.strokeText(s,x,y)}c.fillStyle=color||'#4A2F1B';c.fillText(s,x,y)}
};
function gameObservation(config,levels){
 if(config==null)return null;
 const id=value=>typeof value==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(value);
 const fields=['top','side'];
 const trials=Object.entries(config.trials||{});
 const validEnum=values=>Array.isArray(values)&&values.length>=1&&values.length<=8&&values.every(id)&&new Set(values).size===values.length;
 if(!id(config.sceneId)||!Number.isInteger(levels)||levels<1||levels>5||!trials.length||trials.length>8||
    trials.some(([trial,views])=>!id(trial)||!views||Object.keys(views).length!==2||!fields.every(view=>validEnum(views[view])))){
   throw new Error('invalid game observation config');
 }
 const sceneId=config.sceneId, enums=new Map(trials.map(([trial,views])=>[trial,{top:new Set(views.top),side:new Set(views.side)}]));
 const recorded=Array.from({length:levels},()=>new Map());
 let automated=false,snapshot=null;
 return {
   reset(level,auto){
     snapshot=null;
     if(level===0)automated=auto;
     for(let i=level;i<levels;i++)recorded[i].clear();
   },
   automated(){automated=true;snapshot=null;},
   record(level,trial,views){
     const allowed=enums.get(trial),entries=recorded[level];
     if(automated||!allowed||!views||Object.keys(views).length!==2||entries.has(trial)||
        !fields.every(view=>allowed[view].has(views[view])))return false;
     entries.set(trial,{trialId:trial,top:views.top,side:views.side});return true;
   },
   finish(){
     if(automated||recorded.some(entries=>entries.size!==enums.size))return;
     snapshot={schemaVersion:'mira.game.observation.v1',sceneId,kind:'simulation',levels:recorded.map((entries,i)=>
       ({level:i+1,trials:[...enums.keys()].map(trial=>entries.get(trial))}))};
     W.dispatchEvent(new CustomEvent('mira-game-observation-ready'));
   },
   read:()=>snapshot?JSON.parse(JSON.stringify(snapshot)):null,
 };
}
function gameCueLead(g){
 let lead=null, allowed=W.parent===W;
 function launchLead(){
   if(!lead||lead.started||!allowed||g.auto)return;
   lead.started=true;
   lead.remaining=10;
   W.miraCancelNarration?.();
   W.miraNarrate(lead.id);
 }
 W.addEventListener('message',e=>{
   if(e.source!==W.parent||e.data?.type!=='MIRA_NARRATION_VISIBILITY'||typeof e.data.visible!=='boolean')return;
   allowed=e.data.visible;
   if(!allowed&&lead)lead.started=false;
   // The recording helper handles this same parent message before playback.
   if(allowed)W.queueMicrotask(launchLead);
 });
 W.addEventListener('mira-narration-state',e=>{
   const {cueId,status}=e.detail||{};
   if(!lead||lead.id!==cueId)return;
   if(status==='hidden'){allowed=false;lead.started=false;}
   else if(['ready','missing','error'].includes(status))lead=null;
 });
 return {
   start(id){
     if(g.auto||typeof W.miraNarrate!=='function')return;
     lead={id,started:false};launchLead();
   },
   allowed:()=>allowed,
   reset(){lead=null;W.miraCancelNarration?.()},
   blocking(){return !!lead&&!g.auto},
   waiting(dt){
     if(!lead||g.auto)return false;
     if(!lead.started)return true;
     lead.remaining-=dt;
     if(lead.remaining>0)return true;
     lead=null;return false;
   },
 };
}
function gameNarration(config,stage,g){
 if(config==null)return null;
 const isCue=id=>typeof id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(id);
 const validMissCues=groups=>groups==null||typeof groups==='object'&&!Array.isArray(groups)&&
   Object.entries(groups).every(([reason,cues])=>isCue(reason)&&Array.isArray(cues)&&cues.length===2&&cues.every(isCue));
 if(!Array.isArray(config)||config.length!==g.levels||config.some(level=>
   !level||!['goal','hint','hint2','praise'].every(key=>isCue(level[key]))||!validMissCues(level.missCues))){
   throw new Error('invalid game narration config');
 }
 const button=K.el('button','btn g-replay-cue',null,stage);
 button.type='button';button.setAttribute('aria-label','重听老师');button.dataset.gameNativeSpace='';button.hidden=true;
 button.innerHTML='<svg viewBox="0 0 48 48" aria-hidden="true"><path fill="currentColor" d="M5 18h9l10-9v30l-10-9H5z"/><path fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" d="M31 17a10 10 0 0 1 0 14m6-19a17 17 0 0 1 0 24"/></svg>';
 const playback=gameCueLead(g);
 function speak(key){playback.start(config[g.level][key])}
 button.addEventListener('click',()=>{if(g.state==='play')speak('goal')});
 return {
   ...playback,
   speak,
   miss(reason){
     const level=config[g.level], repeat=g.levelMisses>=2, groups=level.missCues;
     const cues=groups&&Object.hasOwn(groups,reason)?groups[reason]:null;
     if(!g.auto&&playback.allowed())W.miraNarrate?.(cues?cues[repeat?1:0]:level[repeat?'hint2':'hint']);
   },
   draw(){button.hidden=g.state!=='play'||g.auto||typeof W.miraNarrate!=='function'},
 };
}
function gameScore(hud){
 const state={total:0,combo:0}, checkpoints=[];
 const badge=hud&&K.el('b','chip g-run-score',null,hud);
 function render(){if(badge)badge.textContent=state.total+'  /  ×'+state.combo;}
 return {
   state,
   reset(level){
     const total=level===0?0:checkpoints[level]??state.total;
     checkpoints.length=level;
     checkpoints.push(total);
     state.total=total;state.combo=0;render();
   },
   award(){
     state.total+=100+Math.min(5,state.combo)*25;
     state.combo++;render();
   },
   miss(){state.combo=0;render();},
 };
}
K.game=function(o){
 const observation=gameObservation(o.observation,o.levels||1);
 var st=K.stage(),c=D.createElement('canvas');c.id='gm';st.insertBefore(c,st.firstChild);
 var x=c.getContext('2d'),sc=0,last=0,card=null,running=true,reduce=false;
 try{reduce=W.matchMedia('(prefers-reduced-motion: reduce)').matches}catch(e){}
 var g={W:1280,H:720,t:0,dt:0,ctx:x,canvas:c,level:0,levels:o.levels||1,maxLives:o.lives||0,lives:o.lives||0,auto:false,paused:false,state:'ready',misses:0,levelMisses:0,stars:[],parts:[],floats:[],timers:[],taps:[],followers:[],keys:{},pointer:{x:640,y:360,down:false,active:false},shakeAmt:0,bannerObj:null,bubbleObj:null,reduce:reduce};g.data={};
 const narration=gameNarration(o.narration,st,g);
 g.inputBlocked=()=>!!narration?.blocking();
 const score=o.score?gameScore(K.$('#hud')):null;
 if(score)g.score=score.state;
 K.game.current=g;
 function size(){var want=Math.max(1,Math.min(2,(K.scale||1)*(W.devicePixelRatio||1)));if(Math.abs(want-sc)>0.05){sc=want;c.width=Math.round(1280*sc);c.height=Math.round(720*sc)}}
 W.addEventListener('resize',size);size();
 function aim(e){var r=st.getBoundingClientRect();if(!r.width)return;g.pointer.x=(e.clientX-r.left)/r.width*1280;g.pointer.y=(e.clientY-r.top)/r.height*720;g.pointer.active=true}
 st.addEventListener('pointerdown',function(e){if(narration?.blocking()||e.target&&e.target.closest&&e.target.closest('button'))return;g.pointer.down=true;aim(e);g.taps.push({x:g.pointer.x,y:g.pointer.y})});
 st.addEventListener('pointermove',function(e){if(e.pointerType==='mouse'||g.pointer.down)aim(e)});
 W.addEventListener('pointerup',function(){g.pointer.down=false});
 W.addEventListener('pointercancel',function(){g.pointer.down=false});
 var KEYS={ArrowLeft:'left',a:'left',A:'left',ArrowRight:'right',d:'right',D:'right',ArrowUp:'up',w:'up',W:'up',ArrowDown:'down',s:'down',S:'down',' ':'jump',Spacebar:'jump'};
 W.addEventListener('keydown',function(e){var k=KEYS[e.key];if(!k||g.state!=='play'||(k==='jump'&&e.target?.closest?.('[data-game-native-space]')))return;e.preventDefault();if(narration?.blocking())return;if(k==='jump'&&!g.keys.jump)g.taps.push({key:true,x:g.pointer.x,y:g.pointer.y});g.keys[k]=true});
 W.addEventListener('keyup',function(e){var k=KEYS[e.key];if(k)g.keys[k]=false});
 g.after=function(sec,fn){g.timers.push({t:sec,fn:fn})};
 g.shake=function(a){if(!reduce)g.shakeAmt=Math.max(g.shakeAmt,a)};
 g.burst=function(px,py,op){op=op||{};var n=op.n||10;if(reduce)n=Math.ceil(n/3);for(var i=0;i<n;i++){var a=Math.random()*Math.PI*2,v=(op.speed||220)*(0.5+Math.random());g.parts.push({k:'dot',x:px,y:py,vx:Math.cos(a)*v,vy:Math.sin(a)*v-(op.lift==null?120:op.lift),g:op.grav==null?600:op.grav,life:op.life||0.6,max:op.life||0.6,size:(op.size||6)*(0.6+Math.random()*0.7),color:op.color||'#FFD166'})}};
 g.sparkle=function(px,py,color){for(var i=0;i<6;i++){var a=i/6*Math.PI*2;g.parts.push({k:'star',x:px,y:py,vx:Math.cos(a)*160,vy:Math.sin(a)*160,g:0,life:0.5,max:0.5,size:10,color:color||'#FFC531'})}};
 g.confetti=function(n){n=n||60;if(reduce)n=Math.ceil(n/4);var cols=['#FF6B6B','#FFD43B','#51CF66','#4DABF7','#CC5DE8','#FF922B'];for(var i=0;i<n;i++)g.parts.push({k:'conf',x:Math.random()*1280,y:-20-Math.random()*200,vx:(Math.random()-0.5)*120,vy:120+Math.random()*140,g:60,life:2.2+Math.random(),max:3.2,size:8+Math.random()*6,rot:Math.random()*6,vr:(Math.random()-0.5)*12,color:cols[i%6]})};
 g.float=function(text,px,py,op){op=op||{};g.floats.push({text:String(text),x:px,y:py,t:0,dur:op.dur||0.9,size:op.size||56,color:op.color||'#E4572E'})};
 g.banner=function(text,sub,dur){g.bannerObj={text:String(text),sub:sub?String(sub):'',t:0,dur:dur||2}};
 g.say=function(text,kind,dur){K.log.push('say:'+(kind||'')+':'+text);g.bubbleObj={text:String(text),kind:kind||'',t:0,dur:dur||1.9}};
 g.miss=function(reason){g.misses++;g.levelMisses++;score?.miss();K.log.push('miss:'+(g.level+1));narration?.miss(reason)};
 g.awardPoint=function(){if(g.state==='play'&&!g.autoLoop)score?.award()};
 g.hurt=function(){if(!g.maxLives||g.state!=='play')return false;g.lives--;g.miss();g.shake(1);K.sfx.buzz();if(g.lives<=0){g.fail(o.failTitle||'再来一次！');return true}return false};
 g.setAuto=function(on,loop){g.auto=!!on;g.autoLoop=!!(on&&loop);if(g.auto){observation?.automated();narration?.reset()}K.log.push('auto:'+(g.auto?1:0)+(g.autoLoop?':loop':''))};
 g.demoAction=function(){
   if(!o.demoOnce||!g.autoLoop||g.state!=='play')return false;
   g.state='between';g.timers=[];K.log.push('demo:action:'+(g.level+1));return true;
 };
 g.recordObservation=function(trial,views){return !!(observation&&!g.auto&&!g.paused&&g.state==='play'&&observation.record(g.level,trial,views))};
 g.observation=function(){return observation?.read()??null};
 g.follow=function(el,fn){if(typeof el==='string')el=K.$(el);if(!el)return null;if(el.parentNode!==st)st.appendChild(el);el.classList.add('g-anchor');g.followers.push({el:el,fn:fn});return el};
 function hideCard(){
   if(!card)return;
   if(card.contains(D.activeElement))D.activeElement.blur();
   card.className='gone';
 }
 function stars(n){var s='<div class="gstars" aria-label="'+n+' 颗星">';for(var i=0;i<3;i++)s+='<b class="'+(i<n?'on':'')+'">★</b>';return s+'</div>'}
 function nextCard(title,sub,n,fn){if(!card){card=K.el('div','',null,st);card.id='gcard'}card.className='';card.innerHTML='<div class="card"><h1>'+title+'</h1><p>'+sub+'</p>'+stars(n)+'<button class="btn xl" id="g-next">下一关 ▶</button></div>';K.$('button',card).addEventListener('click',function(){K.sfx.pick();hideCard();fn()})}
 function retryCard(title,sub,fn){if(!card){card=K.el('div','',null,st);card.id='gcard'}card.className='';card.innerHTML='<div class="card"><h1>'+title+'</h1><p>'+sub+'</p><button class="btn xl" id="g-retry">再试一次 ↺</button></div>';K.$('button',card).addEventListener('click',function(){K.sfx.pick();hideCard();fn()})}
 g.start=function(level){
  hideCard();g.level=Math.max(0,Math.min(g.levels-1,level|0));
  if(g.level===0&&o.demoOnce){g.stars=[];K.stars=0;var counter=K.$('#star-n');if(counter)counter.textContent='0'}
  score?.reset(g.level);observation?.reset(g.level,g.auto);g.state='play';g.levelMisses=0;g.lives=g.maxLives;g.parts=[];g.floats=[];g.timers=[];g.taps=[];g.bubbleObj=null;
  if(narration){g.keys={};g.pointer.down=false;g.pointer.active=false}
  if(K.$('#dots'))K.levels(g.levels,g.level);K.log.push('level:'+(g.level+1));if(o.reset)o.reset(g,g.level);
  var name=o.levelName?o.levelName(g.level):'';if(name)g.banner('第 '+(g.level+1)+' 关',name,o.bannerTime||1.8);
  narration?.reset();narration?.speak('goal');
 };
 g.win=function(){if(g.state!=='play')return;g.state='between';var n=o.starsFor?o.starsFor(g):(g.levelMisses<=1?3:g.levelMisses<=3?2:1);g.stars[g.level]=n;K.sfx.win();g.confetti(70);K.star(n);var lv=g.level;K.log.push('win:'+(lv+1)+':'+n);narration?.speak('praise');
  g.after(o.winPause==null?1.6:o.winPause,function(){if(g.auto&&g.autoLoop){if(!o.demoOnce)g.start(lv);return}if(lv<g.levels-1){if(g.auto){g.start(lv+1);return}nextCard('第 '+(lv+1)+' 关完成！',o.winText?o.winText(lv):'真棒！',n,function(){g.start(lv+1)})}
   else{g.state='done';if(K.$('#dots'))K.levels(g.levels,g.levels);var sub=o.doneText||'';
    if(score)sub+=(sub?'　':'')+'得分 '+score.state.total;
    K.finish({title:o.doneTitle||'全部通关！',sub,mark:o.finishMark,again:function(){g.stars=[];g.start(0)}});observation?.finish()}})};
 g.fail=function(title){if(g.state!=='play')return;g.state='between';K.sfx.no();var lv=g.level;K.log.push('fail:'+(lv+1));g.after(0.7,function(){if(g.auto){g.start(lv);return}retryCard(title||'再来一次！',o.retryText||'别着急，看清楚再来。',function(){g.start(lv)})})};
 K.onStart=function(){g.start(0)};
 K.onState=function(s){s=s||{};if(s.demo!=null)g.setAuto(s.demo,true);if(s.demo===true&&o.demoOnce)g.start(0);else if(s.level!=null)g.start((s.level|0)-1);else if(s.restart)g.start(g.level);if(s.pause!=null)g.paused=!!s.pause;if(o.onState)o.onState(g,s)};
 function stepParts(dt){for(var i=0;i<g.parts.length;i++){var p=g.parts[i];p.life-=dt;p.vy+=p.g*dt;p.x+=p.vx*dt;p.y+=p.vy*dt;if(p.vr)p.rot+=p.vr*dt}
  g.parts=g.parts.filter(function(p){return p.life>0&&p.y<780});g.floats.forEach(function(f){f.t+=dt});g.floats=g.floats.filter(function(f){return f.t<f.dur})}
 function drawParts(){for(var i=0;i<g.parts.length;i++){var p=g.parts[i];x.save();x.globalAlpha=Math.max(0,Math.min(1,p.life/(p.max*0.5)));
  if(p.k==='dot'){x.fillStyle=p.color;K.draw.circle(x,p.x,p.y,p.size)}else if(p.k==='star')K.draw.star(x,p.x,p.y,p.size,p.color);else{x.translate(p.x,p.y);x.rotate(p.rot);x.fillStyle=p.color;x.fillRect(-p.size/2,-p.size/4,p.size,p.size/2)}x.restore()}}
 function drawFloats(){g.floats.forEach(function(f){var p=f.t/f.dur;x.save();x.globalAlpha=1-p;K.draw.text(x,f.text,f.x,f.y-p*40,Math.round(f.size+18*Math.sin(Math.min(1,p*3)*Math.PI)),f.color,{stroke:'#fff'});x.restore()})}
 function drawBanner(){var b=g.bannerObj;if(!b)return;var a=b.t<0.3?b.t/0.3:(b.t>b.dur-0.4?Math.max(0,(b.dur-b.t)/0.4):1),y=330-(1-Math.min(1,b.t/0.4))*30;
  x.save();x.globalAlpha=a;x.font='800 60px '+K.FONT;var w=x.measureText(b.text).width;if(b.sub){x.font='800 32px '+K.FONT;w=Math.max(w,x.measureText(b.sub).width)}w+=100;var h=b.sub?150:104;
  x.fillStyle='rgba(255,253,246,.97)';K.draw.rr(x,640-w/2,y-h/2,w,h,30);x.fill();x.lineWidth=4;x.strokeStyle='#E8C48F';x.stroke();
  K.draw.text(x,b.text,640,b.sub?y-22:y,60,'#6B4423');if(b.sub)K.draw.text(x,b.sub,640,y+40,32,'#A0521C');x.restore()}
 function drawBubble(){var s=g.bubbleObj;if(!s)return;var at=o.bubbleAt?o.bubbleAt(g):{x:640,y:150},a=s.t>s.dur-0.3?Math.max(0,(s.dur-s.t)/0.3):1;
  x.save();x.globalAlpha=a;x.font='800 34px '+K.FONT;var w=x.measureText(s.text).width+56,bx=Math.max(w/2+12,Math.min(1268-w/2,at.x)),by=at.y;
  var bg=s.kind==='no'?'#FFF0E6':(s.kind==='ok'?'#E9F8E5':'#FFFDF6');x.fillStyle=bg;K.draw.rr(x,bx-w/2,by-34,w,68,24);x.fill();x.lineWidth=4;x.strokeStyle=s.kind==='no'?'#F0A070':(s.kind==='ok'?'#7CC77F':'#E8C48F');x.stroke();
  var tx=Math.max(bx-w/2+30,Math.min(bx+w/2-30,at.x));x.fillStyle=bg;x.beginPath();x.moveTo(tx-12,by+32);x.lineTo(tx,by+52);x.lineTo(tx+12,by+32);x.closePath();x.fill();
  K.draw.text(x,s.text,bx,by+1,34,s.kind==='no'?'#B24A1C':(s.kind==='ok'?'#2F7A36':'#6B4423'));x.restore()}
 function frame(now){if(!running)return;
  try{if(!last)last=now;var dt=Math.min(0.05,Math.max(0,(now-last)/1000));last=now;size();
   if(!g.paused){g.t+=dt;g.dt=dt;
    if(!narration?.waiting(dt)){
     for(var i=0;i<g.timers.length;i++){var tm=g.timers[i];tm.t-=dt;if(tm.t<=0){g.timers.splice(i,1);i--;tm.fn()}}
     if(g.state==='play'){if(g.auto&&o.autopilot)o.autopilot(g,dt);if(o.update)o.update(g,dt)}else if(o.idle)o.idle(g,dt);
    }
    stepParts(dt);if(g.bannerObj){g.bannerObj.t+=dt;if(g.bannerObj.t>g.bannerObj.dur)g.bannerObj=null}
    if(g.bubbleObj){g.bubbleObj.t+=dt;if(g.bubbleObj.t>g.bubbleObj.dur)g.bubbleObj=null}
    g.shakeAmt=Math.max(0,g.shakeAmt-dt*1.8)}
   g.taps.length=0;
   narration?.draw();
   g.followers.forEach(function(f){var r=f.fn(g);if(!r)return;f.el.style.left=r.x+'px';f.el.style.top=r.y+'px';f.el.style.width=r.w+'px';f.el.style.height=r.h+'px'});
   x.setTransform(sc,0,0,sc,0,0);x.clearRect(0,0,1280,720);x.save();
   if(g.shakeAmt>0.05)x.translate((Math.random()*2-1)*g.shakeAmt*7,(Math.random()*2-1)*g.shakeAmt*7);
   if(o.draw)o.draw(g,x);drawParts();x.restore();drawFloats();if(o.drawTop)o.drawTop(g,x);drawBubble();drawBanner()
  }catch(err){running=false;K.errs.push('game: '+String(err&&err.message||err));return}
  W.requestAnimationFrame(frame)}
 if(o.setup)o.setup(g);
 W.requestAnimationFrame(frame);
 setTimeout(function(){if(!K.$('#ready'))K.begin()},0);
 return g};
K.game.status=function(){var g=K.game.current;return g?{state:g.state,level:g.level+1,levels:g.levels,auto:g.auto,misses:g.misses,levelMisses:g.levelMisses,lives:g.lives,stars:g.stars.slice()}:null};
K.game.observation=function(){return K.game.current?.observation()??null};
K.game.autoplay=function(on){var g=K.game.current;if(g)g.setAuto(on!==false,false)};
"""


def uses_game(js):
    """A page opts in to the engine by calling K.game(...) in its own script."""
    return 'K.game(' in js
