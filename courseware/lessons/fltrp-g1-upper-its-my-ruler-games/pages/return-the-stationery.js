K.ready({title:'文具小车送回家',sub:'按住画面带小车走，取到文具后送给发话的人',emoji:'文具工作台'});
(() => {
  const kit = {
    ruler:['__IMG:ruler__','ruler'], eraser:['__IMG:eraser__','eraser'],
    crayon:['__IMG:crayon__','crayon'], case:['__IMG:pencil-case__','pencil case'],
    violet:['__IMG:owner-violet__','露露'], teal:['__IMG:owner-teal__','小满'],
    peach:['__IMG:owner-peach__','朵朵'], trolley:['__IMG:delivery-trolley__','小车']
  };
  const sprites = {};
  for (const [name, [src]] of Object.entries(kit)) {
    const image = new Image(); image.src = src; sprites[name] = image;
  }
  K.startPictureFallback = () => {
    const image = document.createElement('img'); image.className = 'pic';
    image.src = kit.ruler[0]; image.alt = '有刻线的直尺'; return image;
  };
  const demo = [{items:['ruler','eraser'],owners:['teal','violet'],item:'ruler',owner:'violet'}];
  const levels = [
    [{items:['eraser','ruler'],owners:['violet','teal'],item:'ruler',owner:'teal'}],
    [{items:['case','ruler','crayon'],owners:['teal','peach','violet'],item:'crayon',owner:'peach'},
     {items:['ruler','eraser','crayon'],owners:['peach','teal','violet'],item:'ruler',owner:'violet'}],
    [{items:['crayon','ruler','case','eraser'],owners:['peach','violet','teal'],item:'eraser',owner:'teal'},
     {items:['eraser','case','ruler','crayon'],owners:['teal','peach','violet'],item:'case',owner:'peach'}]
  ];
  const clamp = (value,min,max) => Math.max(min,Math.min(max,value));
  const center = (index,count) => 145+(index+0.5)*(990/count);
  const dockY = 351, shelfY = 598, speed = 420;
  const restart = document.getElementById('return-restart');
  const plan = g => g.data.rounds[g.data.index];
  const box = (c,x,y,w,h,fill,border='#dec2a2',radius=22) => {
    K.draw.rr(c,x,y,w,h,radius);
    c.fillStyle=fill; c.fill();
    c.strokeStyle=border; c.lineWidth=3; c.stroke();
  };
  const pic = (c,key,x,y,w,h) => {
    const image=sprites[key];
    if (!image.complete || !image.naturalWidth) {
      K.draw.text(c,kit[key][1],x,y,25,'#254745'); return;
    }
    const scale=Math.min(w/image.naturalWidth,h/image.naturalHeight);
    const sw=image.naturalWidth*scale,sh=image.naturalHeight*scale;
    c.drawImage(image,x-sw/2,y-sh/2,sw,sh);
  };
  const near = (position,x,y,rx,ry) =>
    Math.abs(position.x-x)<=rx && Math.abs(position.y-y)<=ry;
  function obstacles(g) {
    if (g.level===0) return [];
    const t=g.data.age;
    const left={x:355+64*Math.sin(t*1.2),y:417,w:152,h:56};
    return g.level===1 ? [left] :
      [left,{x:917+85*Math.sin(t*1.5+1.1),y:419,w:156,h:56}];
  }
  const blocked = (g,pos) => obstacles(g).some(o=>near(pos,o.x,o.y,o.w/2+29,o.h/2+29));
  function takePosition(g) {
    const s=g.data;
    s.position={x:640,y:510}; s.cargo=null; s.delivered=null; s.age=0;
    s.bad=0; s.cooldown=0; s.wait=0; s.pilot=null;
    g.pointer.active=false;
  }
  function failure(g,kind) {
    const s=g.data;
    if (s.cooldown>0) return;
    g.miss();
    const hints=kind==='item' ?
      ['先看发话牌上的小图，再看取物台。','按外形找同一种文具，再把车开过去。'] :
      ['找是谁开口说了 my，再选窗口。','留意亮着的发话牌，物品要送给发话的人。'];
    g.say(hints[Math.min(s.bad++,1)],'no',2.3);
    s.cooldown=1.05;
  }
  function movement(g,dt) {
    const s=g.data,pos=s.position;
    const xKey=Number(!!g.keys.right)-Number(!!g.keys.left);
    const yKey=Number(!!g.keys.down)-Number(!!g.keys.up);
    const target=g.auto ? s.pilot : xKey||yKey ?
      {x:pos.x+xKey*105,y:pos.y+yKey*105} : g.pointer.active ? g.pointer : null;
    if (!target) return;
    const dx=target.x-pos.x,dy=target.y-pos.y,dist=Math.hypot(dx,dy);
    if (dist<1) return;
    const scale=Math.min(1,speed*dt/dist);
    const next={x:clamp(pos.x+dx*scale,90,1190),y:clamp(pos.y+dy*scale,341,659)};
    if (!blocked(g,next)) s.position=next;
    else if (!blocked(g,{x:next.x,y:pos.y})) pos.x=next.x;
  }
  function pilot(g) {
    const s=g.data,r=plan(g),p=s.position;
    if (!s.cargo) {
      s.pilot={x:center(r.items.indexOf(r.item),r.items.length),y:shelfY}; return;
    }
    if (p.y>=480 && Math.abs(p.x-640)>8) {
      s.pilot={x:640,y:p.y}; return;
    }
    if (p.y>351) { s.pilot={x:640,y:349}; return; }
    s.pilot={x:center(r.owners.indexOf(r.owner),r.owners.length),y:dockY};
  }
  function draw(g,c) {
    c.fillStyle='#fbf2df'; c.fillRect(0,0,1280,720);
    c.fillStyle='#f5e3c5'; c.fillRect(0,345,1280,169);
    box(c,551,349,178,165,'#e3eee4','#b9d1bf',13);
    if (!g.data.rounds) return;
    const s=g.data,r=plan(g),p=s.position;
    box(c,32,25,200,95,'#fffaf0','#dbc39d');
    K.draw.text(c,'第 '+(g.level+1)+' 关',133,51,30,'#5f432f');
    for (let i=0;i<g.levels;i++) {
      c.fillStyle=i<g.level?'#398368':i===g.level?'#cc802e':'#ddd6bd';
      K.draw.circle(c,72+i*25,91,9);
    }
    K.draw.text(c,(s.index+1)+' / '+s.rounds.length,174,92,24,'#5f432f');
    box(c,297,26,680,97,'#fffaf0','#dbc39d');
    const taskText=s.delivered?'文具已归还':s.cargo?'送给发话的人':'先取发话人认领的文具';
    K.draw.text(c,taskText,636,74,35,'#214a47');
    r.owners.forEach((name,i)=>{
      const x=center(i,r.owners.length),active=name===r.owner;
      box(c,x-74,309,148,61,active?'#e3eee4':'#f7e8cf',active?'#7ca58c':'#dac198',13);
      box(c,x-102,193,204,113,active?'#dff3e4':'#fffaf0',active?'#54866c':'#d9c39e');
      const hasDelivery=active&&s.delivered;
      pic(c,name,hasDelivery?x-22:x,248,119,106);
      if (hasDelivery) {
        box(c,x+36,225,56,56,'#f8fff0','#7ca58c',12);
        pic(c,s.delivered,x+64,253,48,45);
      }
      if (active&&!hasDelivery) {
        box(c,x-67,125,134,68,'#eff7ec','#649d83',21);
        pic(c,r.item,x,158,109,57);
      }
    });
    obstacles(g).forEach(o=>{
      box(c,o.x-o.w/2,o.y-o.h/2,o.w,o.h,'#d99652','#8e592e',17);
      c.strokeStyle='#f3c995'; c.lineWidth=5;
      for (let x=o.x-o.w/2+28;x<o.x+o.w/2-18;x+=28) {
        c.beginPath();c.moveTo(x,o.y-13);c.lineTo(x+13,o.y+13);c.stroke();
      }
    });
    r.items.forEach((name,i)=>{
      const x=center(i,r.items.length);
      const moved=s.cargo===name||s.delivered===name;
      box(c,x-92,552,184,111,moved?'#edf6ed':'#fff9ec','#ccad84');
      if (!moved) pic(c,name,x,shelfY+8,155,86);
    });
    box(c,p.x-48,p.y-39,96,77,'#f5d3a2','#93643e',16);
    pic(c,'trolley',p.x,p.y,82,65);
    if (s.cargo) pic(c,s.cargo,p.x,p.y-18,70,40);
  }
  const frame = (x,y,w,h)=>({x:x-w/2,y:y-h/2,w,h});
  K.game({
    levels:levels.length,finishMark:'★★★',doneText:'你先认准文具，再把它交给发话的人。',
    starsFor:()=>3,winPause:1.0,levelName:i=>['听见谁在说','文具和人都会换','绕过两个工作台'][i],
    setup(g) {
      restart.addEventListener('click',()=>g.start(g.level));
      g.follow('#return-speech',()=>g.data.rounds ?
        frame(center(plan(g).owners.indexOf(plan(g).owner),plan(g).owners.length),223,212,201) : null);
      g.follow('#return-shelf',()=>frame(640,605,1030,128));
      g.follow('#return-trolley',()=>g.data.position ?
        frame(g.data.position.x,g.data.position.y,104,86) : null);
    },
    reset(g,i) {
      g.data={rounds:g.auto&&g.autoLoop&&i===0?demo:levels[i],index:0};
      takePosition(g); restart.hidden=g.auto&&g.autoLoop;
    },
    onState(g) { restart.hidden=g.auto&&g.autoLoop; },
    autopilot:pilot,
    update(g,dt) {
      const s=g.data,r=plan(g);
      s.age+=dt; s.cooldown=Math.max(0,s.cooldown-dt);
      if (s.wait>0) {
        s.wait-=dt;
        if (s.wait>0) return;
        if (s.index===s.rounds.length-1) {
          restart.hidden=true;g.win();return;
        }
        s.index++;takePosition(g);return;
      }
      movement(g,dt);
      if (!s.cargo) {
        const i=r.items.findIndex((_,j)=>near(s.position,center(j,r.items.length),shelfY,81,45));
        if (i<0) return;
        if (r.items[i]!==r.item) { failure(g,'item');return; }
        s.cargo=r.item; s.bad=0; s.cooldown=0;
        K.sfx.pick(); g.say('取对了，再找发话的人。','ok',1.35);return;
      }
      const i=r.owners.findIndex((_,j)=>near(s.position,center(j,r.owners.length),dockY+13,77,46));
      if (i<0) return;
      if (r.owners[i]!==r.owner) { failure(g,'owner');return; }
      s.delivered=s.cargo;s.cargo=null;
      g.sparkle(s.position.x,s.position.y); K.sfx.coin();
      g.say('文具还给发话的人啦！','ok',1.7);s.wait=1.45;
    },
    draw,bubbleAt:()=>({x:640,y:493})
  });
})();
