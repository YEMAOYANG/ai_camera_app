// Opt-in arcade layer. The existing K.game lifecycle still owns frames, demos,
// retries and progression. A mechanic consumes the same input for people and bots.
K.gameTemplates = K.gameTemplates || {};
const Classic = (() => {
  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
  const ease = (x, target, dt, speed = 14) => target + (x - target) * Math.exp(-speed * dt);
  const keys = {ArrowLeft:'left', ArrowRight:'right', ArrowUp:'up', ArrowDown:'down', ' ':'action'};
  const controls = {left:['←','向左'], right:['→','向右'], up:['↑','向上'], down:['↓','向下']};
  const notes = [60, null, 64, 67, 69, 67, 64, null, 62, null, 65, 69, 67, 65, 62, null];
  const box = (c,x,y,w,h,r,fill) => { c.fillStyle=fill; K.draw.rr(c,x,y,w,h,r); c.fill(); };
  const text = (c,value,x,y,size=34,color='#253b33',opts) => K.draw.text(c,String(value),x,y,size,color,opts);
  const asset = (url) => { if(!url) return null; const im=new Image(); im.src=url; return im; };
  const ready = im => im && im.complete && im.naturalWidth > 0;
  function sprite(c, im, x, y, width, height, {angle=0,flip=false,bottom=false}={}) {
    if(!ready(im))return false;
    const scale=Math.min(width/im.naturalWidth,height/im.naturalHeight);
    const w=im.naturalWidth*scale,h=im.naturalHeight*scale;
    c.save();c.translate(x,y);c.rotate(angle);if(flip)c.scale(-1,1);
    c.drawImage(im,-w/2,bottom?-h:-h/2,w,h);c.restore();return true;
  }
  function scene(c,im,fill) {
    c.fillStyle=fill;c.fillRect(0,0,1280,720);
    if(ready(im))c.drawImage(im,0,0,1280,720);
  }
  const center = (x,y,w,h) => ({x:x-w/2,y:y-h/2,w,h});
  function input() {
    const held=new Map(), pending=new Set();
    return {
      down(source,key){if(!held.has(source)){held.set(source,key);pending.add(key);}},
      up(source){held.delete(source);},
      clear(){held.clear();pending.clear();},
      read(){
        const keys=new Set(held.values()), presses=new Set(pending);pending.clear();
        return {held:key=>keys.has(key),press:key=>presses.has(key)};
      }
    };
  }
  function bot(...values){return {held:key=>values.includes(key),press:key=>values.includes(key)};}
  function attach(g, o, labels, images, activeCue) {
    const stage=K.stage();
    const surface=stage.classList;
    surface.add('classic-arcade');
    const bar=K.el('div','arc-controls',null,stage);
    const score=K.el('div','arc-score',null,stage);
    const route=K.el('div','arc-route',null,stage);
    const buttons=new Map(), state=input();
    let music=true, activated=false, beat=0, nextBeat=0, cueBusy=false;
    const lead=o.voiceLead?gameCueLead(g):null;
    const aria = (node,label) => node.setAttribute('aria-label',label);
    const button=(parent,kind,mark,label)=>{
      const b=K.el('button',kind,null,parent);b.type='button';b.textContent=mark;aria(b,label);return b;
    };
    const routeNodes = (el) => o.levels.map((_,i) => {
      const node=K.el('b','arc-node',null,el);node.textContent=String(i+1);return node;
    });
    const markers=routeNodes(route);
    const card=K.$('#ready .card');
    if(card){const map=K.el('div','arc-map',null,card);aria(map,'关卡路线');routeNodes(map);card.insertBefore(map,K.$('button',card));}
    const mute=button(bar,'arc-key arc-music','♫','关闭音乐和音效');
    mute.dataset.gameNativeSpace='';
    // This page owns its sound effects; teacher recordings use a separate audio channel.
    for(const [name,play] of Object.entries(K.sfx))K.sfx[name]=(...args)=>{if(music)play(...args);};
    mute.setAttribute('aria-pressed','true');
    mute.addEventListener('click',()=>{music=!music;activated=true;mute.textContent=music?'♫':'♪';mute.setAttribute('aria-pressed',String(music));aria(mute,music?'关闭音乐和音效':'开启音乐和音效');});
    const replay=button(bar,'arc-key arc-voice','◖))','重听老师');
    replay.dataset.gameNativeSpace='';
    replay.hidden=!o.cues?.length;
    const pad=K.el('div','arc-pad',null,bar);
    for(const [key,mark,label] of labels){
      const b=button(pad,'arc-key',mark,label); b.setAttribute('data-arc-input',key);buttons.set(key,b);
      b.addEventListener('pointerdown',e=>{
        if(g.state!=='play'||e.button!==0||lead?.blocking())return;
        e.preventDefault();activated=true;
        try{b.setPointerCapture(e.pointerId);}catch{}
        state.down('pointer'+e.pointerId,key);
      });
      for(const event of ['pointerup','pointercancel','lostpointercapture']){
        b.addEventListener(event,e=>state.up('pointer'+e.pointerId));
      }
      b.addEventListener('click',e=>{
        if(e.detail!==0||g.state!=='play'||lead?.blocking())return; // native button activated by keyboard/AT
        activated=true;state.down('button'+key,key);state.up('button'+key);
      });
    }
    W.addEventListener('keydown',e=>{
      const key=keys[e.key];if(!buttons.has(key)||g.state!=='play'||(key==='action'&&e.target?.closest?.('[data-game-native-space]')))return;
      e.preventDefault();
      if(lead?.blocking())return;
      activated=true;if(!e.repeat)state.down('key'+e.key,key);
    });
    W.addEventListener('keyup',e=>state.up('key'+e.key));
    W.addEventListener('blur',()=>state.clear());
    D.addEventListener('visibilitychange',()=>{if(D.hidden)state.clear();});
    W.addEventListener('mira-narration-state',e=>{
      const {status}=e.detail||{};
      if(status==='playing')cueBusy=true;
      if(['ready','error','hidden','missing'].includes(status))cueBusy=false;
    });
    K.$('#start-btn')?.addEventListener('click',()=>{activated=true;});
    const cancel=()=>{if(lead)lead.reset();else W.miraCancelNarration?.();cueBusy=false;};
    function cue(id,wait=false){
      if(!id||g.auto||typeof W.miraNarrate!=='function')return;
      if(wait&&lead){state.clear();lead.start(id);}
      else W.miraNarrate(id);
    }
    const waiting=dt=>lead?.waiting(dt);
    replay.addEventListener('click',()=>{if(!g.data.end)cue(activeCue(g),true);});
    function show(){
      bar.hidden=g.state!=='play';route.hidden=score.hidden=g.state==='ready'||g.state==='done';
      for(const b of buttons.values())b.disabled=Boolean(lead?.blocking());
      const newScore=String(g.data.total||0)+'  /  ×'+String(g.data.combo||0);
      if(score.textContent!==newScore)score.textContent=newScore;
      markers.forEach((n,i)=>{n.className='arc-node'+(g.stars[i]?' arc-won':i===g.level?' arc-current':'');});
      if(music && activated && !g.auto && !cueBusy && !lead?.blocking() && !D.hidden && g.state==='play' && g.t>=nextBeat){
        const n=notes[beat++%notes.length]; nextBeat=g.t+0.285;
        if(n!=null)tone(440*2**((n-69)/12),0,0.21,'triangle',0.025);
      }
    }
    return {state,show,cue,cancel,waiting,images};
  }

  function create(o, m) {
    if(!Array.isArray(o.levels)||o.levels.length<3||o.levels.length>5)throw new Error('classic games need 3–5 levels');
    o.levels.forEach(m.validate);
    const imgs={backdrop:asset(o.art?.backdrop),sticker:asset(o.art?.sticker),frames:(o.art?.frames||[]).map(asset),
      icons:new Map(Object.entries(o.art?.icons||{}).map(([key,url])=>[key,asset(url)]))};
    const labels=m.controls.map(v=>typeof v==='string'?[v,...controls[v]]:v);
    let ui, score=0, prevLevel=0, base=0, lastCompleted=false;
    let finishExtra;
    function activeCue(g){
      const levelCues=o.cues?.[g.level];
      const step=m.cueIndex?.(g.data.w,g.data.level)??g.data.progress;
      return levelCues?.steps?.[step]??levelCues?.goal;
    }
    const lost = (g,w,x,y) => {
      const d=g.data;g.miss();d.failures++;d.combo=0;g.burst(x,y,{color:'#f1c28d',n:5});
      K.sfx.no();
      const hints=o.levels[g.level].hints;
      const msg=hints?.[d.failures>=2?1:0];
      if(msg)g.say(msg,'no',1.5);
      if(!d.end)ui.cue(o.cues?.[g.level]?.[d.failures>=2?'hint2':'hint']);
      m.adapt?.(w,d.failures);
    };
    function award(g,x,y,n=1){
      const d=g.data;if(d.end||g.state!=='play')return;
      d.progress+=n;
      g.sparkle(x,y,'#ffcf63');
      K.sfx.coin();
      if(g.demoAction())return;
      d.combo++;
      const points=100+Math.min(5,d.combo-1)*25;
      d.total+=points;
      g.float('+'+points,x,Math.max(94,y-28),{size:34,color:'#bd591f'});
      if(d.progress>=m.goal(d.level)){
        d.end=.44;ui.cue(o.cues?.[g.level]?.praise,true);
      }else if(o.cues?.[g.level]?.steps){
        ui.cue(activeCue(g), o.stepVoiceLead === true);
      }
    }
    return {
      levels:o.levels.length,demoOnce:true,winPause:0.85,finishMark:'★',doneText:o.doneText||'',
      observation:o.observation,
      bubbleAt:()=>({x:640,y:104}),
      setup(g){
        ui=attach(g,o,labels,imgs,activeCue);
        for(const [id,role] of [['#game-player','player'],['#game-target','target'],['#game-goal','goalAnchor']]){
          g.follow(id,()=>{
            const anchor=m[role]??(role==='goalAnchor'?m.target:null);
            return g.data.w?anchor?.call(m,g.data.w,g.data.level):null;
          });
        }
      },
      reset(g,l){
        // A retry keeps the score already earned in earlier levels. A replay
        // or a teacher handoff begins with a fresh score and no held input.
        if(lastCompleted||l<prevLevel||g.autoLoop||l===0){score=0;base=0;}
        else if(l>prevLevel){base=score;}
        prevLevel=l;lastCompleted=false;
        finishExtra?.remove();
        finishExtra=null;
        ui.state.clear();ui.cancel();
        const level=o.levels[l];
        g.data={level,w:m.reset(level,l),total:base,combo:0,progress:0,failures:0,end:0};
        if(!g.auto)ui.cue(activeCue(g),true);
      },
      autopilot(g,dt){const d=g.data;d.bot=m.pilot(d.w,d.level,dt);},
      update(g,dt){
        const d=g.data, active=ui.state.read();
        if(ui.waiting(dt))return;
        if(d.end>0){
          d.end-=dt;if(d.end<=0){score=d.total;g.win();}
          return;
        }
        m.update(d.w,d.level,g.auto?d.bot:active,dt,{
          fx: (x,y,color='#fff4bd')=>g.burst(x,y,{n:4,size:4,color,life:.27}),
          move:()=>K.sfx.pop(), jump:()=>K.sfx.jump(), drop:()=>K.sfx.drop(),
          award:(x,y,n)=>award(g,x,y,n), lost:(x,y)=>lost(g,d.w,x,y),
          observe:(trial,views)=>g.recordObservation(trial,views),
          resetCheckpoint:()=>{d.total=base;d.combo=0;d.progress=0;},
        },imgs);
      },
      draw(g,c){
        scene(c,imgs.backdrop,m.backdrop);
        if(g.data.w)m.draw(g.data.w,g.data.level,c,imgs,g);
        ui.show();
        if(g.state==='done'){
          const panel=K.$('#finish .card'),mark=panel&&K.$('.big',panel);
          if(panel&&!panel.classList.contains('arc-done')){
            panel.classList.add('arc-done');
            if(ready(imgs.sticker)){
              const sticker=D.createElement('img');sticker.src=o.art.sticker;sticker.alt='过关贴纸';mark.replaceChildren(sticker);
            }
            K.$('p',panel).textContent=(o.doneText?o.doneText+'　':'')+'得分 '+score;
            finishExtra=m.finishExtra?.(g.observation(),imgs);
            if(finishExtra)panel.insertBefore(finishExtra,K.$('#btn-again',panel));
            lastCompleted=true;
          }
        }
      }
    };
  }
  const validToken = v => (typeof v==='string'&&v.trim().length>0&&[...v].length<=18)||Number.isFinite(v);
  const match = (a,b,l) => typeof l.matches==='function'?!!l.matches(a,b):
    Array.isArray(l.pairs)?l.pairs.some(([left,right])=>left===a&&right===b):
    typeof a==='number'&&typeof b==='number'&&a+b===l.total;
  function token(c,imgs,v,x,y,width,height,labels,color='#253b33'){
    if(!sprite(c,imgs.icons.get(String(v)),x,y,width,height)){
      const label=String(labels?.[v]??v);
      text(c,label,x,y,Math.min(height*.67,width/(Math.max(1,[...label].length)*.64)),color);
    }
  }
  return {clamp,ease,box,text,sprite,center,create,bot,validToken,match,token};
})();
// Course-owned mechanics can use the same progression and accessibility layer.
K.gameTemplates.arcade = Classic.create;
