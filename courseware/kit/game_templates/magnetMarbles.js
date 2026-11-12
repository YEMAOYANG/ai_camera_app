// Aim a launcher, then bend the marble in flight. Targets can match by sum,
// configured token pairs, or an author-supplied predicate.
K.gameTemplates.magnetMarbles = config => {
  const {box,text,center,create,bot,sprite,clamp,validToken,match,token}=Classic;
  const launchY=534,hitY=229,left=225,right=1055;
  const targetWidth=l=>l.targetWidth??92;
  const targetHeight=l=>l.targetHeight??82;
  function check(l){
    const width=targetWidth(l), height=targetHeight(l);
    const valid=t=>t&&validToken(t.value)&&t.x>=left+width/2&&t.x<=right-width/2;
    if(!Array.isArray(l.targets)||!Array.isArray(l.queue)||!l.queue.length||l.queue.length>7||
      l.targets.length<l.queue.length||l.targets.length>8||!l.targets.every(valid)||!l.queue.every(validToken)||
      !Number.isInteger(width)||width<92||width>200||!Number.isInteger(height)||height<82||height>128||
      !(l.speed>=320&&l.speed<=720)||!(l.drift>=0&&l.drift<=34))throw new Error('invalid marble level');
    const pending=[...l.targets];
    for(const v of l.queue){
      const i=pending.findIndex(t=>match(v,t.value,l));if(i<0)throw new Error('marble queue lacks matching targets');
      pending.splice(i,1);
    }
  }
  const targetX=(t,w,l,time=w.time)=>t.x+Math.sin(time*2.4+t.x*.019)*l.drift;
  function reset(l){return {x:640,y:launchY,angle:0,vx:0,vy:0,i:0,targets:l.targets.map(t=>({...t,used:false})),time:0,
    air:false,delay:0,fx:0,help:false,trail:[],locked:null};}
  function serve(w){w.x=640;w.y=launchY;w.air=false;w.vx=0;w.vy=0;w.trail=[];}
  const candidates=(w,l)=>w.targets.filter(t=>!t.used&&match(l.queue[w.i],t.value,l));
  function update(w,l,input,dt,fb){
    w.time+=dt;w.fx=Math.max(0,w.fx-dt);
    if(w.delay>0){w.delay-=dt;if(w.delay<=0)serve(w);return;}
    if(w.i>=l.queue.length)return;
    const dir=((input.held('right')||input.press('right'))?1:0)-((input.held('left')||input.press('left'))?1:0);
    if(dir&&w.fx===0){w.fx=.13;fb.move();fb.fx(w.x,w.y,'#f3a25f');}
    if(!w.air){
      w.angle=clamp(w.angle+dir*dt*1.7,-.79,.79);
      if(input.press('action')){
        const v=l.speed*(w.help?.83:1);
        w.vx=Math.sin(w.angle)*v;w.vy=-Math.cos(w.angle)*v;w.air=true;
        fb.jump();fb.fx(w.x,w.y);
      }
      return;
    }
    const oldY=w.y;
    w.vx=clamp(w.vx+dir*dt*780,-740,740);
    w.x+=w.vx*dt;w.y+=w.vy*dt;
    if(w.x<left||w.x>right){w.x=clamp(w.x,left,right);w.vx*=-.92;fb.drop();fb.fx(w.x,w.y);}
    w.trail.push([w.x,w.y]);if(w.trail.length>17)w.trail.shift();
    if(oldY>=hitY&&w.y<=hitY){
      const x=w.x, tol=targetWidth(l)/2+(w.help?17:3);
      const hit=w.targets.filter(t=>!t.used&&Math.abs(targetX(t,w,l)-x)<=tol)
        .sort((a,b)=>Math.abs(targetX(a,w,l)-x)-Math.abs(targetX(b,w,l)-x))[0];
      if(hit&&match(l.queue[w.i],hit.value,l)){
        hit.used=true;w.locked=hit;w.i++;w.delay=.32;fb.award(targetX(hit,w,l),hitY);
      }else{
        w.delay=.45;fb.lost(x,hitY);
      }
    }
  }
  function draw(w,l,c,imgs){
    const width=targetWidth(l),height=targetHeight(l);
    box(c,left-12,171,14,388,7,'#b98158');box(c,right-2,171,14,388,7,'#b98158');
    for(const t of w.targets){
      const x=targetX(t,w,l);
      if(t.used){sprite(c,imgs.sticker,x,hitY,55,55);continue;}
      const matched=w.help&&match(l.queue[w.i],t.value,l);
      box(c,x-width/2,hitY-height/2,width,height,21,matched?'#f9d58a':'#b6d4a5');
      box(c,x-width/2+8,hitY-height/2+6,width-16,10,5,'#fff6cb93');
      if(!l.listenOnly)token(c,imgs,t.value,x,hitY,width-16,height-16,l.labels);
      else if(!sprite(c,imgs.icons.get(String(t.value)),x,hitY,width-16,height-16)){
        const count=l.targetFallbackCounts?.[t.value];
        if(Number.isInteger(count)&&count>=1&&count<=12){
          c.fillStyle='#274b43';
          const columns=Math.min(4,count), rows=Math.ceil(count/columns);
          for(let i=0;i<count;i++){
            const row=Math.floor(i/columns),col=i%columns;
            K.draw.circle(c,x+(col-(columns-1)/2)*20,hitY+(row-(rows-1)/2)*20,6);
          }
        }
      }
    }
    if(!w.air){
      for(let n=1;n<=11;n++){c.fillStyle='#ffdda099';K.draw.circle(c,640+Math.sin(w.angle)*n*15,launchY-Math.cos(w.angle)*n*15,4);}
      c.save();c.translate(640,launchY+15);c.rotate(w.angle);
      box(c,-46,-10,92,45,15,'#bb754b');box(c,-35,-16,70,16,8,'#f5c176');c.restore();
    }
    for(let i=0;i<w.trail.length;i++){
      const [x,y]=w.trail[i];c.fillStyle='#ffca6a'+Math.floor(170*i/w.trail.length).toString(16).padStart(2,'0');K.draw.circle(c,x,y,4+i*.6);
    }
    if(w.i<l.queue.length&&w.delay<=0){
      if(!sprite(c,imgs.frames[0],w.x,w.y,76,76)){c.fillStyle='#f6b867';K.draw.circle(c,w.x,w.y,30);}
      if(!l.listenOnly)token(c,imgs,l.queue[w.i],w.x,w.y,46,48,l.labels,'#332c24');
    }
    box(c,580,98,120,58,17,'#305343');
    token(c,imgs,l.listenOnly?'◖))':(l.symbol??l.total??'↔'),640,127,96,54,l.labels,'#fff2cc');
  }
  return create(config,{backdrop:'#213b34',validate:check,reset,goal:l=>l.queue.length,update,draw,
    controls:['left','right',['action','↟','发射弹珠']],adapt(w,n){w.help=n>=2;},
    player:w=>center(w.x,w.y,80,80),target:(w,l)=>{const t=candidates(w,l)[0]||w.locked;return t&&center(targetX(t,w,l),hitY,targetWidth(l),targetHeight(l));},
    pilot(w,l){
      if(w.delay>0)return bot();
      const c=candidates(w,l)[0];if(!c)return bot();
      const flight=(launchY-hitY)/l.speed;
      if(!w.air){
        const a=clamp(Math.atan2(targetX(c,w,l,w.time+flight)-640,launchY-hitY),-.77,.77);
        return Math.abs(a-w.angle)<.032?bot('action'):bot(a<w.angle?'left':'right');
      }
      const time=Math.max(0,(hitY-w.y)/w.vy),desired=targetX(c,w,l,w.time+time);
      const error=desired-w.x-w.vx*time;
      return Math.abs(error)<18?bot():bot(error<0?'left':'right');
    }
  });
};
