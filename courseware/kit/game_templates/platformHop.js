// A physical platformer. Only landing on the next value unlocks a checkpoint;
// jumping over a distractor is allowed. Levels supply geometry and the route.
K.gameTemplates.platformHop = config => {
  const {box,text,center,create,bot,sprite,token,validToken}=Classic;
  const gravity=1510, launch=-646;
  function check(l){
    if(!Array.isArray(l.platforms)||l.platforms.length<4||l.platforms.length>12||
      !Array.isArray(l.route)||l.route.length<3||new Set(l.route).size!==l.route.length||
      !(l.speed>=235&&l.speed<=345))throw new Error('invalid platform level');
    if((l.prompt!=null&&!validToken(l.prompt))||(l.startLabel!=null&&!validToken(l.startLabel)))throw new Error('invalid platform prompt');
    const ids=new Map();
    for(const [x,y,w,value] of l.platforms){
      if(![x,y,w].every(Number.isFinite)||x<35||w<72||x+w>1245||y<230||y>585||
          ids.has(value))throw new Error('invalid platform or duplicate label');
      ids.set(value,{x,y,w});
    }
    if(!ids.has('start')||!l.route.every(v=>ids.has(v)&&v!=='start'))throw new Error('platform route missing a landing');
    let from=ids.get('start');
    for(const v of l.route){
      const to=ids.get(v);
      const disc=launch*launch+2*gravity*(to.y-from.y);
      const flight=(Math.sqrt(disc)-launch)/gravity;
      if(disc<0||Math.abs(to.x+to.w*.5-from.x-from.w*.5)>flight*l.speed-14)throw new Error('platform jump out of reach');
      from=to;
    }
  }
  const standing=(p,w)=>w.x>=p[0]-6&&w.x<=p[0]+p[2]+6;
  const mid=p=>p[0]+p[2]/2;
  function reset(l){
    const start=l.platforms.find(p=>p[3]==='start');
    return {x:mid(start),y:start[1],vy:0,platform:start,checkpoint:start,i:0,look:1,
      coyote:0,buffer:0,freeze:0,walk:0,help:false,moving:false};
  }
  function update(w,l,input,dt,fb){
    if(w.freeze>0){
      w.freeze-=dt;if(w.freeze>0)return;
      const p=w.checkpoint;w.x=mid(p);w.y=p[1];w.vy=0;w.platform=p;w.buffer=0;w.coyote=0;
    }
    const dx=(input.held('right')?1:0)-(input.held('left')?1:0);
    if(dx)w.look=dx;
    if(input.press('action')||input.press('up'))w.buffer=.14;
    if(w.platform)w.coyote=w.help?.19:.11;
    if(w.buffer>0&&w.coyote>0){
      w.vy=launch;w.platform=null;w.buffer=0;w.coyote=0;fb.jump();fb.fx(w.x,w.y);
    }
    const previousX=w.x;
    const horizontal=dx*l.speed;
    w.x=Math.max(25,Math.min(1255,w.x+horizontal*dt));
    const wasMoving=w.moving;
    w.moving=w.x!==previousX;
    if(w.moving){
      const frame=Math.floor(w.walk*5);w.walk+=dt;
      if(w.platform&&(!wasMoving||Math.floor(w.walk*5)!==frame)){fb.move();fb.fx(w.x,w.y);}
    }else w.walk=0;
    if(w.platform&&!standing(w.platform,w))w.platform=null;
    if(!w.platform){
      const from=w.y;w.vy+=gravity*dt;w.y+=w.vy*dt;
      const hit=w.vy>=0&&l.platforms.filter(p=>standing(p,w)&&from<=p[1]&&w.y>=p[1]).sort((a,b)=>a[1]-b[1])[0];
      if(hit){
        w.y=hit[1];w.vy=0;w.platform=hit;
        if(hit[3]===l.route[w.i]){w.checkpoint=hit;w.i++;fb.award(w.x,w.y-30);}
        else if(hit!==w.checkpoint){
          w.freeze=.48;fb.lost(w.x,w.y-20);
        }
      }else if(w.y>645){
        w.freeze=.37;fb.lost(w.x,606);
      }
    }
    w.buffer=Math.max(0,w.buffer-dt);w.coyote=Math.max(0,w.coyote-dt);
  }
  function draw(w,l,c,imgs,g){
    const needed=l.route[w.i];
    for(const p of l.platforms){
      const [x,y,width,value]=p;
      box(c,x,y+8,width,51,18,'#4a5c47');
      box(c,x,y,width,29,13,p===w.checkpoint?'#edaf67':w.help&&value===needed?'#daec9d':'#9eb16b');
      if(value!=='start')token(c,imgs,value,mid(p),y+21,width-14,43,l.labels,'#242f23');
      else if(l.startLabel!=null)token(c,imgs,l.startLabel,mid(p),y+21,width-14,43,l.labels,'#242f23');
      else text(c,'⚑',mid(p),y+19,31,'#2c4430');
    }
    const id=!w.platform?2:w.moving?Math.floor(w.walk*9)%2:0;
    if(w.y<643&&!sprite(c,imgs.frames[id],w.x,w.y+2,94,92,{flip:w.look<0,bottom:true})){
      box(c,w.x-25,w.y-47,50,47,18,'#ae6644');
    }
    const prompt=l.prompt===undefined?(needed??'✓'):l.prompt;
    if(prompt!==null){
      box(c,592,18,96,58,16,'#294a40');
      token(c,imgs,prompt,640,46,83,49,l.labels,'#fff2cb');
    }
    if(w.i>0)for(let i=0;i<Math.min(w.i,8);i++)sprite(c,imgs.sticker,442+i*49,86,34,34);
  }
  return create(config,{
    controls:['left','right',['up','↑','跳跃'],['action','↟','跳跃']],backdrop:'#f6ce9c',
    validate:check,reset,goal:l=>l.route.length,update,draw,adapt(w,n){w.help=n>=2;},
    player:w=>center(w.x,w.y-42,92,91),
    target(w,l){const p=l.platforms.find(p=>p[3]===l.route[w.i]);return p&&center(mid(p),p[1]+13,p[2],45);},
    pilot(w,l){
      if(w.freeze>0)return bot();
      const p=l.platforms.find(p=>p[3]===l.route[w.i]);if(!p)return bot();
      const dx=mid(p)-w.x,dir=dx<0?'left':'right';
      return bot(...(w.platform?['action']:[]),...(Math.abs(dx)>5?[dir]:[]));
    }
  });
};
