// A point light, flat cutout, and screen are a deliberately simplified model.
// The position and size of the shadow are derived from similar triangles.
K.gameTemplates.shadowStage = config => {
  const {box,text,center,create,bot,sprite,clamp}=Classic;
  const gap=115,source=640,minD=126,maxD=310,minX=350,maxX=930;
  function projection(x,d){return {x:source+(source-x)*gap/d,scale:1+gap/d};}
  function check(l){
    if(!Array.isArray(l.shots)||!l.shots.length||l.shots.length>6||
      !l.shots.every(a=>a.x>=minX&&a.x<=maxX&&a.d>=minD&&a.d<=maxD&&['triangle','circle','square'].includes(a.shape))||
      !(l.tolerance>=10&&l.tolerance<=40))throw new Error('invalid shadow stage');
  }
  function reset(){return {x:640,d:228,i:0,pulse:0,change:0,help:false,locked:null};}
  function figure(c,x,y,size,kind){
    c.beginPath();
    if(kind==='circle')c.arc(x,y,size/2,0,Math.PI*2);
    else if(kind==='square')c.rect(x-size/2,y-size/2,size,size);
    else {c.moveTo(x,y-size*.58);c.lineTo(x+size*.54,y+size*.43);c.lineTo(x-size*.54,y+size*.43);c.closePath();}
  }
  const close=(w,t,tol)=>Math.abs(projection(w.x,w.d).x-projection(t.x,t.d).x)<=tol &&
    Math.abs(projection(w.x,w.d).scale-projection(t.x,t.d).scale)*112<=tol*.6;
  function update(w,l,input,dt,fb){
    w.pulse=Math.max(0,w.pulse-dt);
    if(w.change>0){w.change-=dt;if(w.change<=0)w.locked=null;return;}
    const target=l.shots[w.i];if(!target)return;
    const dir=(input.held('right')?1:0)-(input.held('left')?1:0);
    const shift=(input.held('down')?1:0)-(input.held('up')?1:0);
    if(dir||shift){
      w.x=clamp(w.x+dir*dt*242,minX,maxX);w.d=clamp(w.d+shift*dt*152,minD,maxD);
      if(w.pulse===0){fb.move();fb.fx(w.x,444+w.d*.44);w.pulse=.16;}
    }
    if(input.press('action')){
      const p=projection(w.x,w.d);fb.drop();fb.fx(p.x,281);
      if(close(w,target,l.tolerance*(w.help?1.55:1))){
        w.locked=target;w.change=.67;w.i++;fb.award(p.x,281);
      }else fb.lost(p.x,281);
    }
  }
  function draw(w,l,c,imgs){
    const t=w.locked||l.shots[w.i]||l.shots.at(-1);
    const p=projection(w.x,w.d),goal=projection(t.x,t.d),matched=close(w,t,l.tolerance*(w.help?1.55:1));
    box(c,348,157,584,256,22,'#f8e8bd');
    const shadow=(v,fill,alpha)=>{c.save();c.globalAlpha=alpha;figure(c,v.x,281,112*v.scale,t.shape);c.fillStyle=fill;c.fill();c.restore();};
    shadow(goal,'#b98656',.15);shadow(p,matched?'#4a7f62':'#4b5044',.88);
    c.save();figure(c,goal.x,281,112*goal.scale,t.shape);c.strokeStyle=matched?'#fff8d3':'#9b583d';c.lineWidth=5;c.setLineDash([12,9]);c.stroke();c.restore();
    const y=444+w.d*.44;
    box(c,343,418,594,166,20,'#304a3e');
    c.beginPath();c.moveTo(w.x,y);c.lineTo(source-20,444);c.lineTo(p.x-48,422);
    c.lineTo(p.x+48,422);c.lineTo(source+20,444);c.closePath();c.fillStyle='#f2b96655';c.fill();
    box(c,608,435,64,17,5,'#ba774a');
    if(w.help){c.strokeStyle='#ffe6a0';c.lineWidth=3;c.strokeRect(t.x-25,444+t.d*.44-25,50,50);}
    if(!sprite(c,imgs.frames[0],w.x,y,66,83))box(c,w.x-23,y-28,46,55,14,'#f0b862');
    text(c,w.i+' / '+l.shots.length,640,113,30,'#fff4d8',{stroke:'#304a3e',strokeWidth:5});
  }
  return create(config,{backdrop:'#b47b59',validate:check,reset,goal:l=>l.shots.length,update,draw,
    controls:['left','right',['up','↑','把灯靠近'],['down','↓','把灯拉远'],['action','◎','定格影子']],
    adapt(w,n){w.help=n>=2;},
    player:w=>center(w.x,444+w.d*.44,75,86),
    target(w,l){const t=w.locked||l.shots[w.i]||l.shots.at(-1);return center(projection(t.x,t.d).x,281,175,175);},
    pilot(w,l){
      const t=l.shots[w.i];if(!t||w.change>0)return bot();
      if(close(w,t,l.tolerance*.48))return bot('action');
      return bot(...(Math.abs(t.x-w.x)>4?[t.x<w.x?'left':'right']:[]),
                 ...(Math.abs(t.d-w.d)>3?[t.d<w.d?'up':'down']:[]));
    }
  });
};
