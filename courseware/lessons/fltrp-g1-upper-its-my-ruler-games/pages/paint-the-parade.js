K.ready({title:'跟着传送带涂色',sub:'按住画面推滚轮，先蘸对色，再追着要涂的文具',emoji:'文具工作台'});
(() => {
  const art = {
    schoolbag:['__IMG:schoolbag__','schoolbag'], desk:['__IMG:desk__','desk'],
    book:['__IMG:book__','book'], pencil:['__IMG:wood-pencil__','pencil'],
    pen:['__IMG:ink-pen__','pen'], roller:['__IMG:paint-roller__','滚轮']
  };
  const sprites = {};
  for (const [key, [src]] of Object.entries(art)) {
    const image=new Image(); image.src=src; sprites[key]=image;
  }
  K.startPictureFallback=()=>{
    const image=document.createElement('img');image.className='pic';
    image.src=art.book[0];image.alt='封面和书页清楚的绘本';return image;
  };
  const inks = {red:'#d74748',yellow:'#eebd22',blue:'#2e82cb'};
  const pots = ['red','yellow','blue'];
  const demo=[{options:['book','desk','pencil'],item:'desk',ink:'red'}];
  const levels=[
    [{options:['pencil','book','pen'],item:'pencil',ink:'yellow'}],
    [{options:['desk','schoolbag','pen'],item:'schoolbag',ink:'blue'},
     {options:['pencil','pen','desk'],item:'pen',ink:'red'}],
    [{options:['pen','desk','book'],item:'book',ink:'red'},
     {options:['desk','pencil','schoolbag'],item:'desk',ink:'blue'}]
  ];
  const paintY=382,potY=617, speed=455;
  const beltLeft=28,beltRight=1252,cardHalfWidth=94;
  const firstFullCard=beltLeft+cardHalfWidth+2,lastFullCard=beltRight-cardHalfWidth-2;
  const plan=g=>g.data.rounds[g.data.index];
  const restart=document.getElementById('paint-restart');
  const cache=new Map();
  const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
  const potX=i=>400+i*240;
  const box=(c,x,y,w,h,fill,stroke='#c4b48c',radius=22)=>{
    K.draw.rr(c,x,y,w,h,radius);c.fillStyle=fill;c.fill();c.strokeStyle=stroke;c.lineWidth=3;c.stroke();
  };
  const circle=(c,x,y,r,fill)=>{c.fillStyle=fill;K.draw.circle(c,x,y,r);};
  const frame=(x,y,w,h)=>({x:x-w/2,y:y-h/2,w,h});
  function drawSprite(c,key,x,y,w,h,source=sprites[key]) {
    if (source===sprites[key] && (!source.complete || !source.naturalWidth)) {
      K.draw.text(c,art[key][1],x,y,27,'#324b44');return;
    }
    const iw=source.naturalWidth||source.width,ih=source.naturalHeight||source.height;
    const k=Math.min(w/iw,h/ih);
    c.drawImage(source,x-iw*k/2,y-ih*k/2,iw*k,ih*k);
  }
  function tinted(key,ink) {
    const image=sprites[key], id=key+'|'+ink;
    if (!image.complete||!image.naturalWidth) return image;
    if (cache.has(id)) return cache.get(id);
    const canvas=document.createElement('canvas');canvas.width=160;canvas.height=116;
    const ctx=canvas.getContext('2d');
    drawSprite(ctx,key,80,58,160,116,image);
    ctx.globalCompositeOperation='source-atop';ctx.globalAlpha=0.74;ctx.fillStyle=inks[ink];ctx.fillRect(0,0,160,116);
    cache.set(id,canvas);return canvas;
  }
  function roundStart(g) {
    const s=g.data;
    s.cards=plan(g).options.map((key,i)=>({key,x:255+i*380,coverage:0}));
    s.brush={x:640,y:525};s.ink=null;s.wrong=0;s.wait=0;s.cooldown=0;s.pilot=null;s.age=0;
    g.pointer.active=false;
  }
  function aimBrush(g,dt) {
    const s=g.data,b=s.brush;
    const dx=Number(!!g.keys.right)-Number(!!g.keys.left);
    const dy=Number(!!g.keys.down)-Number(!!g.keys.up);
    const target=g.auto?s.pilot:dx||dy?{x:b.x+dx*110,y:b.y+dy*110}:g.pointer.active?g.pointer:null;
    if (!target) return;
    const x=clamp(target.x,102,1178),y=clamp(target.y,258,645);
    const distance=Math.hypot(x-b.x,y-b.y),part=distance?Math.min(1,dt*speed/distance):0;
    b.x+=(x-b.x)*part;b.y+=(y-b.y)*part;
  }
  function hint(g,reason) {
    const s=g.data;
    if (s.cooldown>0) return;
    const hints=reason==='colour' ?
      ['看一看任务窗的颜色样片。','先回颜料盘，给滚轮蘸上相同的颜色。'] :
      ['再看任务窗是哪件文具。','先让别的物品过去，跟住画里的那一件。'];
    g.miss();g.say(hints[Math.min(s.wrong++,1)],'no',2.3);s.cooldown=1.2;
  }
  function pilot(g) {
    const s=g.data,r=plan(g),card=s.cards.find(o=>o.key===r.item);
    if (s.ink!==r.ink) {s.pilot={x:potX(pots.indexOf(r.ink)),y:potY};return;}
    s.pilot=card.x>1128||card.x<138?{x:770,y:522}:{x:card.x-20,y:paintY};
  }
  function draw(g,c) {
    c.fillStyle='#f4f0de';c.fillRect(0,0,1280,720);
    box(c,24,268,1232,230,'#e7ecdc','#9cb8a5',38);
    c.save();c.strokeStyle='#a5baa6';c.lineWidth=5;c.setLineDash([20,14]);
    for(const y of [279,488]){c.beginPath();c.moveTo(49,y);c.lineTo(1231,y);c.stroke();}
    c.restore();
    if (!g.data.rounds) return;
    const s=g.data,r=plan(g);
    box(c,32,25,202,95,'#fffaf0');
    K.draw.text(c,'第 '+(g.level+1)+' 关',134,51,30,'#536448');
    for (let i=0;i<g.levels;i++) {
      circle(c,72+i*25,91,9,i<g.level?'#398368':i===g.level?'#cc802e':'#ddd6bd');
    }
    K.draw.text(c,(s.index+1)+' / '+s.rounds.length,174,92,24,'#536448');
    box(c,397,22,486,133,'#fffdf4');
    drawSprite(c,r.item,543,89,168,116);
    circle(c,742,88,42,'#faf1d7');circle(c,742,88,33,inks[r.ink]);
    c.save();
    c.beginPath();c.rect(beltLeft,292,beltRight-beltLeft,192);c.clip();
    for (const item of s.cards) {
      const x=item.x;
      const opacity=Math.min(1,(x-firstFullCard)/32,(lastFullCard-x)/32);
      if (opacity<=0) continue;
      c.save();c.globalAlpha=opacity;
      box(c,x-cardHalfWidth,310,cardHalfWidth*2,145,'#fdfcf5','#a7b8a5');
      c.save();c.filter='grayscale(100%)';drawSprite(c,item.key,x,paintY,160,116);c.restore();
      if (item.coverage>0) {
        c.save();c.beginPath();c.rect(x-80,paintY-60,160*item.coverage,120);c.clip();
        drawSprite(c,item.key,x,paintY,160,116,tinted(item.key,r.ink));c.restore();
      }
      c.restore();
    }
    c.restore();
    for (const [i,ink] of pots.entries()) {
      const x=potX(i);
      box(c,x-89,568,178,98,'#fffcf1',ink===s.ink?'#445d51':'#c4b48c');
      circle(c,x,potY,37,inks[ink]);
      if (ink===s.ink) {
        c.strokeStyle='#fffaf1';c.lineWidth=5;c.beginPath();c.arc(x,potY,28,0,Math.PI*2);c.stroke();
      }
    }
    const b=s.brush;
    drawSprite(c,'roller',b.x,b.y,107,97);
    if (s.ink) circle(c,b.x+29,b.y+26,11,inks[s.ink]);
  }
  K.game({
    levels:levels.length,finishMark:'★★★',doneText:'听清物品和颜色，再动手涂。',
    starsFor:()=>3,levelName:i=>['跟住一件用品','换物品也换颜色','传送带走快一点'][i],
    setup(g) {
      restart.addEventListener('click',()=>g.start(g.level));
      g.follow('#paint-mission',()=>frame(640,88,490,137));
      g.follow('#paint-palette',()=>frame(640,617,664,105));
      g.follow('#paint-roller',()=>g.data.brush?frame(g.data.brush.x,g.data.brush.y,111,99):null);
    },
    reset(g,i) {
      g.data={rounds:g.auto&&g.autoLoop&&i===0?demo:levels[i],index:0};
      roundStart(g);restart.hidden=g.auto&&g.autoLoop;
    },
    onState(g) { restart.hidden=g.auto&&g.autoLoop; },
    autopilot:pilot,
    update(g,dt) {
      const s=g.data,r=plan(g);
      s.age+=dt;s.cooldown=Math.max(0,s.cooldown-dt);
      if (s.wait>0) {
        s.wait-=dt;
        s.brush.y=Math.min(525,s.brush.y+speed*dt);
        if (s.wait>0) return;
        if (s.index===s.rounds.length-1) {restart.hidden=true;g.win();return;}
        s.index++;roundStart(g);return;
      }
      aimBrush(g,dt);
      const b=s.brush;
      const pot=pots.findIndex((_,i)=>Math.abs(potX(i)-b.x)<69&&Math.abs(potY-b.y)<45);
      if (pot>=0 && s.ink!==pots[pot]) {s.ink=pots[pot];K.sfx.pick();}
      for (const card of s.cards) {
        card.x-=(96+22*g.level)*dt;
        if (card.x<-100) card.x+=1470;
      }
      const card=s.cards.find(o=>o.x>firstFullCard+12&&o.x<lastFullCard-12&&Math.abs(o.x-b.x)<74&&Math.abs(paintY-b.y)<48);
      if (!card) return;
      if (card.key!==r.item) {hint(g,'item');return;}
      if (s.ink!==r.ink) {hint(g,'colour');return;}
      card.coverage=Math.min(1,card.coverage+dt/(0.72+0.14*g.level));
      if (card.coverage<1) return;
      g.sparkle(card.x,paintY);K.sfx.coin();
      g.say('物品对了，颜色也对了！','ok',1.8);s.wait=1.55;
    },
    draw,bubbleAt:()=>({x:640,y:211})
  });
})();
