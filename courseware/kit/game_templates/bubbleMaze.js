// Map symbols: # fixed wall, + bubble-breakable wall, S start, E exit,
// and up to nine alphanumeric tokens supplied by the lesson's sequence.
K.gameTemplates.bubbleMaze = config => {
  const {box,text,ease,center,create,bot,sprite,token}=Classic;
  const dirs={right:[1,0],down:[0,1],left:[-1,0],up:[0,-1]};
  const entries=Object.entries(dirs),s=67;
  function reset(l){
    const map=l.map.map(row=>[...row]);
    let x,y;
    map.forEach((row,iy)=>row.forEach((v,ix)=>{if(v==='S'){x=ix;y=iy;row[ix]='.';}}));
    return {map,x,y,vx:x,vy:y,dir:'right',i:0,hold:0,pew:0,shots:[],time:0,help:false,
      ox:(1280-map[0].length*s)/2,oy:113+(7-map.length)*s/2,
      patrols:(l.patrols||[]).map(p=>({...p,stun:0,x:p.from}))};
  }
  const value=(w,x,y)=>w.map[y]?.[x]??'#';
  const isToken=(l,v)=>l.route.includes(v);
  function path(w,l,allowBreak=true){
    const target=l.route[w.i]??'E',seen=new Set([w.y*32+w.x]),queue=[[w.x,w.y,null]];
    for(let i=0;i<queue.length;i++){
      const [x,y,first]=queue[i];if(value(w,x,y)===target)return first;
      for(const [dir,[dx,dy]] of entries){
        const nx=x+dx,ny=y+dy,v=value(w,nx,ny),id=ny*32+nx;
        if(seen.has(id)||v==='#'||(!allowBreak&&v==='+')||(isToken(l,v)&&v!==target))continue;
        seen.add(id);queue.push([nx,ny,first||{dir,breakable:v==='+'}]);
      }
    }
    return null;
  }
  function check(l){
    if(!Array.isArray(l.map)||l.map.length<4||l.map.length>7||
       !l.map.every(row=>typeof row==='string'&&row.length===l.map[0].length)||
       l.map[0].length<6||l.map[0].length>13||
       !Array.isArray(l.route)||l.route.length<2||l.route.length>9||
       new Set(l.route).size!==l.route.length||!l.route.every(v=>typeof v==='string'&&/^[0-9A-DF-RT-Z]$/.test(v))||
       !(l.step>=.12&&l.step<=.45))throw new Error('invalid maze level');
    const chars=l.map.join('');
    for(const key of ['S','E',...l.route])if(chars.split(key).length!==2)throw new Error('maze needs one '+key);
    if(![...chars].every(v=>'#.SE+'.includes(v)||l.route.includes(v)))throw new Error('unknown maze cell');
    for(const p of l.patrols||[]){
      if(![p.y,p.from,p.to].every(Number.isInteger)||p.from>=p.to||!(p.speed>0&&p.speed<=2.5)||
        ![...Array(p.to-p.from+1).keys()].every(x=>l.map[p.y]?.[x+p.from]==='.'))throw new Error('invalid patrol lane');
    }
    const w=reset(l);
    for(const key of [...l.route,'E']){
      if(!path(w,l))throw new Error('no ordered route to maze token '+key);
      w.y=w.map.findIndex(r=>r.includes(key));w.x=w.map[w.y].indexOf(key);w.map[w.y][w.x]='.';w.i++;
    }
  }
  function px(w,x){return w.ox+(x+.5)*s;}
  function py(w,y){return w.oy+(y+.5)*s;}
  function shoot(w,fb){
    const [dx,dy]=dirs[w.dir];
    w.pew=.28;fb.jump();fb.fx(px(w,w.x)+dx*30,py(w,w.y)+dy*30,'#e2ffdb');
    w.shots.push({x:w.x,y:w.y,dx,dy,t:0,cell:0});
  }
  function update(w,l,input,dt,fb){
    w.time+=dt;w.hold=Math.max(0,w.hold-dt);w.pew=Math.max(0,w.pew-dt);
    const move=entries.find(([dir])=>input.press(dir)||input.held(dir));
    if(move)w.dir=move[0];
    if(w.pew===0&&input.press('action'))shoot(w,fb);
    for(const shot of w.shots){
      shot.t+=dt;
      const next=Math.min(3,Math.floor(shot.t*16));
      while(shot.cell<next&&!shot.dead){
        shot.cell++;
        const x=shot.x+shot.dx*shot.cell,y=shot.y+shot.dy*shot.cell,v=value(w,x,y);
        if(v==='+'||v==='#'){
          if(v==='+'){w.map[y][x]='.';fb.fx(px(w,x),py(w,y),'#ffd5a2');fb.drop();}
          shot.dead=true;
        }
        for(const p of w.patrols)if(p.y===y&&Math.abs(p.x-x)<.72){p.stun=2.4;shot.dead=true;fb.fx(px(w,x),py(w,y),'#deffec');}
      }
    }
    w.shots=w.shots.filter(q=>!q.dead&&q.t<.21);
    for(const p of w.patrols){
      if(p.stun>0){p.stun-=dt;continue;}
      p.phase=(p.phase||0)+dt*p.speed;
      const d=p.to-p.from;
      p.x=p.from+d-Math.abs(p.phase%(2*d)-d);
    }
    if(move&&w.hold===0){
      const [dir,[dx,dy]]=move,x=w.x+dx,y=w.y+dy,v=value(w,x,y);
      w.hold=l.step*(w.help?1.15:1);
      if(!'# +'.includes(v)){
        w.x=x;w.y=y;fb.move();fb.fx(px(w,x),py(w,y));
        if(v===l.route[w.i]){w.i++;w.map[y][x]='.';fb.award(px(w,x),py(w,y));}
        else if(v==='E'&&w.i===l.route.length){w.i++;fb.award(px(w,x),py(w,y));}
        else if(isToken(l,v)||v==='E')fb.lost(px(w,x),py(w,y));
        for(const p of w.patrols)if(p.stun<=0&&p.y===y&&Math.abs(p.x-x)<.48){
          p.stun=1.4;w.hold+=w.help?0:.28;fb.lost(px(w,x),py(w,y));
        }
      }else if(v==='+'&&!input.press('action'))fb.fx(px(w,x),py(w,y),'#f1d4a1');
    }
    w.vx=ease(w.vx,w.x,dt,20);w.vy=ease(w.vy,w.y,dt,20);
  }
  function draw(w,l,c,imgs){
    for(let y=0;y<w.map.length;y++)for(let x=0;x<w.map[y].length;x++){
      const v=w.map[y][x],left=w.ox+x*s,top=w.oy+y*s;
      if(v==='#'||v==='+'){
        box(c,left+1,top+4,s-2,s-2,9,'#664931');
        box(c,left+1,top,s-2,s-5,9,v==='#'?'#476456':'#d88761');
        box(c,left+9,top+5,s-18,5,3,'#ffebbe56');
        if(v==='+')text(c,'◌',px(w,x),py(w,y)-3,38,'#fff2c6');
      }else{
        box(c,left+1,top+1,s-2,s-2,6,'#ffdd9c49');
        if(v==='E'){box(c,left+5,top+5,s-10,s-10,13,'#274a40');text(c,'⚑',px(w,x),py(w,y),38,'#ffda82');}
        if(isToken(l,v)){
          const selected=w.help&&v===l.route[w.i];
          K.draw.star(c,px(w,x),py(w,y),selected?31:29,selected?'#fff8c9':'#f8cd77');
          token(c,imgs,v,px(w,x),py(w,y)+2,52,53,l.labels,'#302e24');
        }
      }
    }
    for(const p of w.patrols){
      box(c,px(w,p.x)-19,py(w,p.y)-18,38,36,15,p.stun>0?'#96e6dc':'#716c9d');
      for(const off of [-7,7]){c.fillStyle='#fffcde';K.draw.circle(c,px(w,p.x)+off,py(w,p.y)-2,3);}
    }
    const angle={right:0,down:Math.PI/2,left:Math.PI,up:-Math.PI/2}[w.dir];
    const x=px(w,w.vx),y=py(w,w.vy);
    if(!sprite(c,imgs.frames[w.pew>.15?1:0],x,y,61,61,{angle}))box(c,x-22,y-21,44,42,14,'#cc6c4d');
    for(const q of w.shots){
      const off=q.t*16;c.lineWidth=3;c.strokeStyle='#f5fff0';c.beginPath();
      c.arc(px(w,q.x+q.dx*off),py(w,q.y+q.dy*off),13,0,2*Math.PI);c.stroke();
    }
    box(c,605,18,70,58,16,'#294a40');
    const next=l.route[w.i];
    token(c,imgs,next===undefined?'⚑':l.listenOnly?'◖))':next,640,46,60,52,l.labels,'#ffe2a0');
  }
  return create(config,{
    controls:['left','right','up','down',['action','◌','喷泡泡']],backdrop:'#9a9f65',
    validate:check,reset,goal:l=>l.route.length+1,update,draw,
    adapt(w,n){w.help=n>=2;},
    player:w=>center(px(w,w.vx),py(w,w.vy),s,s),
    target(w,l){
      const target=l.route[w.i]??'E',y=w.map.findIndex(r=>r.includes(target));
      return y<0?null:center(px(w,w.map[y].indexOf(target)),py(w,y),s,s);
    },
    pilot(w,l){
      const p=path(w,l);
      return p?(p.breakable?(w.pew===0?bot(p.dir,'action'):bot(p.dir)):bot(p.dir)):bot();
    }
  });
};
