// Build speed around an anchor and let go along the tangent. Each leg accepts
// a configured token; art icons and optional labels come from the lesson.
K.gameTemplates.fireflySwing = config => {
  const {box,text,center,create,bot,sprite,validToken,token}=Classic;
  const radius=69, start={x:181,y:363}, colors=['#f1bf65','#8fd1bc','#d5a5e2'];
  function check(l){
    if(!Array.isArray(l.legs)||l.legs.length<2||l.legs.length>4||!(l.omega>=1.5&&l.omega<=3.4))throw new Error('invalid swing route');
    let origins=[start];
    for(const leg of l.legs){
      if(!validToken(leg.goal)||!Array.isArray(leg.targets)||leg.targets.length!==2||
        leg.targets.filter(t=>t.value===leg.goal).length!==1||
        !leg.targets.every(t=>validToken(t.value)&&t.x>=220&&t.x<=1130&&t.y>=175&&t.y<=523)||
        Math.hypot(leg.targets[0].x-leg.targets[1].x,leg.targets[0].y-leg.targets[1].y)<137||
        !origins.every(o=>leg.targets.every(t=>Math.hypot(t.x-o.x,t.y-o.y)>radius+75&&Math.hypot(t.x-o.x,t.y-o.y)<520))){
        throw new Error('swing targets overlap or are out of reach');
      }
      origins=leg.targets;
    }
  }
  function reset(){return {anchor:start,angle:-.6,dir:1,air:false,x:0,y:0,vx:0,vy:0,i:0,time:0,
    flying:0,hold:0,fx:0,delay:0,help:false,trail:[],collected:[]};}
  function orbit(w){
    return [w.anchor.x+Math.cos(w.angle)*radius,w.anchor.y+Math.sin(w.angle)*radius];
  }
  const velocity=w=>[-Math.sin(w.angle)*w.dir,Math.cos(w.angle)*w.dir];
  function update(w,l,input,dt,fb){
    w.time+=dt;w.fx=Math.max(0,w.fx-dt);
    if(w.delay>0){w.delay-=dt;return;}
    const leg=l.legs[w.i];if(!leg)return;
    if(!w.air){
      if(input.held('left')||input.press('left'))w.dir=-1;
      if(input.held('right')||input.press('right'))w.dir=1;
      w.angle+=dt*l.omega*(w.help?.71:1)*w.dir;
      [w.x,w.y]=orbit(w);
      if(input.press('action')){
        const v=velocity(w);
        w.vx=v[0]*500;w.vy=v[1]*500;w.flying=0;w.air=true;w.trail=[];
        fb.jump();fb.fx(w.x,w.y);
      }
      return;
    }
    w.x+=w.vx*dt;w.y+=w.vy*dt;w.flying+=dt;
    w.trail.push([w.x,w.y]);if(w.trail.length>19)w.trail.shift();
    const hit=leg.targets.find(t=>Math.hypot(t.x-w.x,t.y-w.y)<(w.help?66:55));
    if(hit||w.flying>1.16||w.x<35||w.x>1245||w.y<107||w.y>575){
      w.air=false;w.delay=.32;w.trail=[];
      if(hit?.value===leg.goal){
        w.anchor=hit;w.collected.push(hit);w.angle=-.55;w.i++;
        fb.award(hit.x,hit.y);
      }else {fb.lost(w.x,w.y);w.angle+=.27;}
      [w.x,w.y]=orbit(w);
    }
  }
  function draw(w,l,c,imgs){
    for(const old of w.collected)sprite(c,imgs.sticker,old.x,old.y,49,49);
    const leg=l.legs[w.i]||l.legs.at(-1);
    if(w.i<l.legs.length)for(const [i,t] of leg.targets.entries()){
      const glow=w.help&&t.value===leg.goal;
      c.fillStyle=glow?'#ffe79160':'#e7bd6a32';K.draw.circle(c,t.x,t.y,glow?58:53);
      c.fillStyle=colors[t.color??i];K.draw.circle(c,t.x,t.y,39);
      token(c,imgs,t.value,t.x,t.y,64,56,l.labels);
    }
    c.strokeStyle='#9fbca480';c.lineWidth=3;c.beginPath();c.arc(w.anchor.x,w.anchor.y,radius,0,2*Math.PI);c.stroke();
    c.fillStyle='#eabc65';K.draw.circle(c,w.anchor.x,w.anchor.y,12);
    const [x,y]=w.air?[w.x,w.y]:orbit(w);
    if(!w.air){
      const [dx,dy]=velocity(w);c.save();c.strokeStyle='#ffeac690';c.lineWidth=3;c.setLineDash([9,12]);
      c.beginPath();c.moveTo(x,y);c.lineTo(x+dx*154,y+dy*154);c.stroke();c.restore();
    }
    for(let i=0;i<w.trail.length;i++){
      const [tx,ty]=w.trail[i];c.fillStyle='#fce4a788';K.draw.circle(c,tx,ty,2+i*.33);
    }
    const [vx,vy]=w.air?[w.vx,w.vy]:velocity(w),a=Math.atan2(vy,vx);
    const im=imgs.frames[Math.floor(w.time*12)%2];
    if(!sprite(c,im,x,y,89,75,{angle:a})){c.fillStyle='#fcd075';K.draw.circle(c,x,y,16);}
    box(c,577,93,126,62,18,'#24494a');
    token(c,imgs,leg.goal,640,124,95,59,l.labels,'#fff2cb');
  }
  return create(config,{backdrop:'#193842',validate:check,reset,goal:l=>l.legs.length,update,draw,
    controls:[['left','↶','逆时针荡'],['right','↷','顺时针荡'],['action','↗','松手飞出去']],
    adapt(w,n){w.help=n>=2;},player:w=>center(...(w.air?[w.x,w.y]:orbit(w)),84,77),
    target(w,l){const leg=l.legs[w.i],t=leg?.targets.find(t=>t.value===leg.goal);return t&&center(t.x,t.y,105,105);},
    pilot(w,l){
      if(w.air||w.delay>0)return bot();
      const goal=l.legs[w.i]?.targets.find(t=>t.value===l.legs[w.i].goal);
      if(!goal)return bot();
      const angle=w.angle+.031*w.dir, x=w.anchor.x+Math.cos(angle)*radius,y=w.anchor.y+Math.sin(angle)*radius;
      const vx=-Math.sin(angle)*w.dir,vy=Math.cos(angle)*w.dir;
      const dx=goal.x-x,dy=goal.y-y,dist=dx*vx+dy*vy;
      const blocked=l.legs[w.i].targets.some(t=>t!==goal&&(t.x-x)*vx+(t.y-y)*vy>0&&
        (t.x-x)*vx+(t.y-y)*vy<dist&&Math.abs((t.x-x)*vy-(t.y-y)*vx)<55);
      return !blocked&&dist>5&&dist<550&&Math.abs(dx*vy-dy*vx)<22?bot('action'):bot();
    }
  });
};
