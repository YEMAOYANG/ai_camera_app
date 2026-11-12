// Continuous flow through a physical splitter. Every droplet must go into
// a reservoir, and both reservoirs must end with their exact configured volume.
K.gameTemplates.tideGates = config => {
  const {box,text,center,create,bot,sprite}=Classic;
  const tanks=[380,900];
  function fit(rest,left){
    if(left<0)return false;
    if(!rest.length)return left===0;
    return fit(rest.slice(1),left-rest[0])||fit(rest.slice(1),left);
  }
  function check(l){
    if(!Array.isArray(l.capacity)||l.capacity.length!==2||!l.capacity.every(n=>Number.isInteger(n)&&n>=3&&n<=10)||
      !Array.isArray(l.drops)||l.drops.length<4||l.drops.length>10||
      !l.drops.every(n=>Number.isInteger(n)&&n>=1&&n<=5)||
      l.drops.reduce((a,b)=>a+b,0)!==l.capacity[0]+l.capacity[1]||
      !fit(l.drops,l.capacity[0])||!(l.seconds>=.65&&l.seconds<=2.8))throw new Error('tide volume is not solvable');
  }
  function reset(){return {t:0,i:0,fill:[0,0],side:0,route:null,brake:0,used:false,freeze:0,help:false};}
  function pos(w){
    if(w.t<.48)return [640,155+140*w.t/.48];
    const q=Math.min(1,(w.t-.48)/.52);
    return [640+(tanks[w.route??w.side]-640)*q,295+175*q];
  }
  function update(w,l,input,dt,fb){
    if(w.freeze>0){
      w.freeze-=dt;if(w.freeze<=0){const h=w.help;Object.assign(w,reset(),{help:h});}return;
    }
    if(w.i>=l.drops.length)return;
    const side=input.held('left')||input.press('left')?0:input.held('right')||input.press('right')?1:w.side;
    if(side!==w.side){w.side=side;fb.move();fb.fx(640,295);}
    if(input.press('action')&&!w.used){w.brake=.8;w.used=true;fb.jump();const [x,y]=pos(w);fb.fx(x,y);}
    if(w.brake>0)w.brake-=dt;
    w.t+=dt*(w.brake>0?.22:1)/(l.seconds*(w.help?1.26:1));
    if(w.t>=.48&&w.route===null){w.route=w.side;fb.fx(640,295,'#c9f5ee');fb.drop();}
    if(w.t>=1){
      const to=w.route,v=l.drops[w.i];w.fill[to]+=v;
      fb.fx(tanks[to],470,'#c6f5e5');
      if(w.fill[to]>l.capacity[to]){
        w.freeze=.7;fb.lost(tanks[to],465);fb.resetCheckpoint();return;
      }
      w.i++;w.t=0;w.route=null;w.used=false;w.brake=0;
      fb.award(tanks[to],445);
    }
  }
  function draw(w,l,c,imgs){
    c.lineWidth=69;c.lineCap='round';c.lineJoin='round';
    for(let i=0;i<2;i++){
      c.strokeStyle='#23625c';c.beginPath();c.moveTo(640,147);c.lineTo(640,294);c.lineTo(tanks[i],467);c.stroke();
      c.lineWidth=57;c.strokeStyle=i===w.side?'#85c5b4':'#57948a';c.stroke();c.lineWidth=69;
      const x=tanks[i],capacity=l.capacity[i],value=w.fill[i];
      box(c,x-98,406,196,155,20,'#244d45');
      box(c,x-84,463,168,79,13,'#e5f3d2');
      const units=168/capacity;
      for(let n=0;n<Math.min(value,capacity);n++)box(c,x-84+n*units+2,466,units-4,73,5,value>capacity?'#b86852':'#60a99a');
      for(let n=1;n<capacity;n++)box(c,x-85+n*units,469,2,66,1,'#22544870');
      text(c,value+' / '+capacity,x,437,35,'#fff5d3');
      if(value===capacity)sprite(c,imgs.sticker,x,385,43,43);
    }
    const gate=w.side===0?-1:1;
    c.save();c.translate(640,295);c.rotate(-.68*gate);box(c,-11,-48,22,96,8,'#e89b69');c.restore();
    if(w.i<l.drops.length&&!w.freeze){
      const [x,y]=pos(w);
      c.fillStyle='#efffeb';K.draw.circle(c,x,y,31);
      c.fillStyle='#b8e5d9';K.draw.circle(c,x,y,26);text(c,l.drops[w.i],x,y+1,34,'#284e45');
    }
    const upcoming=l.drops.slice(w.i+1,w.i+5);
    upcoming.forEach((v,i)=>{box(c,581+i*42,93,37,36,10,'#e4f3d0');text(c,v,600+i*42,111,23,'#285448');});
  }
  return create(config,{backdrop:'#428377',validate:check,reset,goal:l=>l.drops.length,update,draw,
    controls:[['left','←','开左水闸'],['right','→','开右水闸'],['action','Ⅱ','缓一缓']],
    adapt(w,n){w.help=n>=2;},player:w=>center(...pos(w),70,70),target:()=>center(640,295,100,108),
    pilot(w,l){
      if(w.freeze>0||w.route!==null||w.i>=l.drops.length)return bot();
      const left=l.capacity[0]-w.fill[0],v=l.drops[w.i];
      return bot(fit(l.drops.slice(w.i+1),left-v)?'left':'right');
    }
  });
};
