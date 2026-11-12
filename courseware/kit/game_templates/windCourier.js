// Adjust the glider's altitude with gusts while it moves forward. Landing
// stations are above, level with, or below the marked reference station.
K.gameTemplates.windCourier = config => {
  const {box,text,center,create,bot,sprite,clamp}=Classic;
  const startX=155,ys=[213,350,487];
  function check(l){
    if(!Array.isArray(l.legs)||l.legs.length<2||l.legs.length>6||
      !l.legs.every(leg=>Number.isInteger(leg.ref)&&leg.ref>=0&&leg.ref<=2&&[-1,0,1].includes(leg.shift)&&
        leg.ref+leg.shift>=0&&leg.ref+leg.shift<=2)||
      !(l.speed>=125&&l.speed<=275)||!(l.tolerance>=32&&l.tolerance<=66))throw new Error('invalid wind courier route');
  }
  function reset(){return {x:startX,y:ys[1],vy:0,i:0,delay:0,brake:0,used:false,help:false,fx:0,time:0};}
  const target=leg=>ys[leg.ref+leg.shift];
  function update(w,l,input,dt,fb){
    w.time+=dt;w.fx=Math.max(0,w.fx-dt);
    if(w.delay>0){
      w.delay-=dt;if(w.delay<=0){w.x=startX;w.used=false;w.vy=0;}
      return;
    }
    const leg=l.legs[w.i];if(!leg)return;
    const dir=(input.held('down')?1:0)-(input.held('up')?1:0);
    if(dir&&w.fx===0){fb.move();fb.fx(w.x-36,w.y);w.fx=.18;}
    if(input.press('action')&&!w.used){w.used=true;w.brake=.9;fb.jump();fb.fx(w.x,w.y);}
    w.brake=Math.max(0,w.brake-dt);
    const drift=Math.sin(w.time*2)*Math.max(0,l.speed-155)*.74;
    w.vy=(w.vy+(dir*1010+drift)*dt)*Math.exp(-5.5*dt);
    w.y=clamp(w.y+w.vy*dt,147,547);
    w.x+=l.speed*(w.brake>0?.38:1)*(w.help?.8:1)*dt;
    if(w.x>=927){
      if(Math.abs(w.y-target(leg))<=l.tolerance*(w.help?1.38:1)){
        w.i++;w.delay=.55;fb.award(w.x,w.y);
      }else{
        w.delay=.55;fb.lost(w.x,w.y);
      }
    }
  }
  function draw(w,l,c,imgs){
    const leg=l.legs[w.i]||l.legs.at(-1);
    for(let i=0;i<3;i++){
      const y=ys[i],reference=i===leg.ref,highlight=w.help&&y===target(leg);
      c.save();c.strokeStyle=reference?'#fff0bc':'#fcf8df90';c.lineWidth=reference?4:2;c.setLineDash([12,10]);
      c.beginPath();c.moveTo(183,y);c.lineTo(899,y);c.stroke();c.restore();
      box(c,897,y-38,188,76,24,highlight?'#f6cb73':reference?'#b85f43':'#345d4f');
      text(c,reference?'⚑':'◯',991,y,41,highlight?'#28463a':'#fff0c9');
    }
    box(c,533,94,214,55,20,'#294b40');
    text(c,leg.shift<0?'⚑  ↑':leg.shift>0?'⚑  ↓':'⚑  →',640,121,35,'#fff0c6');
    if(!sprite(c,imgs.frames[0],w.x,w.y,139,87,{angle:w.vy*.0022})){
      c.fillStyle='#fff2cb';c.beginPath();c.moveTo(w.x+50,w.y);c.lineTo(w.x-48,w.y-24);c.lineTo(w.x-26,w.y);c.lineTo(w.x-48,w.y+24);c.closePath();c.fill();
    }
    for(let i=0;i<w.i;i++)sprite(c,imgs.sticker,433+i*48,575,40,40);
  }
  return create(config,{backdrop:'#f4bf8e',validate:check,reset,goal:l=>l.legs.length,update,draw,
    controls:[['up','↑','吹向上方'],['down','↓','吹向下方'],['action','Ⅱ','减速']],
    adapt(w,n){w.help=n>=2;},player:w=>center(w.x,w.y,140,85),
    target(w,l){const leg=l.legs[w.i]||l.legs.at(-1);return center(991,target(leg),190,80);},
    pilot(w,l){
      const leg=l.legs[w.i];if(!leg||w.delay>0)return bot();
      const delta=target(leg)-w.y-w.vy*.14;
      return Math.abs(delta)<9?bot():bot(delta<0?'up':'down');
    }
  });
};
