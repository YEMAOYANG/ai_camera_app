// Each falling bunch stays whole. Catch it with the cart and choose which
// of two baskets gets it. Every slot must be filled to finish the level.
K.gameTemplates.orchardCatch = config => {
  const {box, center, create, bot, sprite, clamp}=Classic;
  const lanes=[350,640,930], bins=[199,1081], floor=491;
  const colors=['#a64d2f','#286352'], lights=['#ffe0a2','#bfebd9'];
  const startY=259, cartSpeed=460;

  function canFill(batches, target){
    if(target<0)return false;
    const sums=new Set([0]);
    for(const [quantity] of batches){
      for(const previous of [...sums]){
        if(previous+quantity<=target)sums.add(previous+quantity);
      }
    }
    return sums.has(target);
  }

  function validate(level){
    const {capacity,batches,seconds,catchRadius,wind=0}=level;
    if(!Array.isArray(capacity)||capacity.length!==2||
       !capacity.every(n=>Number.isInteger(n)&&n>=1&&n<=8)||
       !Array.isArray(batches)||batches.length<2||batches.length>6||
       !batches.every(batch=>Array.isArray(batch)&&batch.length===2&&
         Number.isInteger(batch[0])&&batch[0]>=1&&batch[0]<=4&&Number.isInteger(batch[1])&&batch[1]>=0&&batch[1]<lanes.length)||
       batches.reduce((sum,[quantity])=>sum+quantity,0)!==capacity[0]+capacity[1]||
       !canFill(batches,capacity[0])||!Number.isFinite(seconds)||seconds<2.4||seconds>7||
       !Number.isFinite(catchRadius)||catchRadius<76||catchRadius>146||
       !Number.isFinite(wind)||Math.abs(wind)>120)throw new Error('orchard bunches must fit both baskets');
  }

  function reset(){
    return {x:640,side:0,index:0,fill:[0,0],fall:0,delay:0.32,help:false,drive:0};
  }

  function falling(world, level){
    const [quantity,lane]=level.batches[world.index]||level.batches.at(-1);
    const landing=lanes[lane];
    const progress=clamp(world.fall,0,1);
    const x=landing+Math.sin(Math.PI*progress)*(level.wind||0);
    return {quantity,landing,x,y:startY+(floor-startY)*progress};
  }

  function update(w,l,input,dt,fb){
    if(w.index===l.batches.length)return;
    const dx=Number(input.held('right')||input.press('right'))-Number(input.held('left')||input.press('left'));
    if(dx&&dx!==w.drive){fb.move();fb.fx(w.x,557,lights[w.side]);}
    w.drive=dx;
    w.x=clamp(w.x+dx*cartSpeed*dt,lanes[0]-60,lanes.at(-1)+60);
    if(input.press('action')){
      w.side=1-w.side;
      fb.drop();
      fb.fx(w.x,524,lights[w.side]);
    }
    if(w.delay>0){w.delay-=dt;return;}
    w.fall+=dt/(l.seconds*(w.help?1.35:1));
    if(w.fall<1)return;
    const {quantity,landing}=falling(w,l);
    w.fall=0;
    w.delay=.65;
    if(Math.abs(w.x-landing)>l.catchRadius+(w.help?32:0)){
      fb.lost(landing,floor);
      return;
    }
    if(w.fill[w.side]+quantity>l.capacity[w.side]){
      fb.lost(bins[w.side],157);
      Object.assign(w,reset(),{help:w.help,delay:1.15});
      fb.resetCheckpoint();
      return;
    }
    w.fill[w.side]+=quantity;
    w.index++;
    fb.fx(bins[w.side],169,lights[w.side]);
    fb.award(landing,floor-39);
  }

  function fruit(c, art, x, y, size){
    if(sprite(c,art,x,y,size,size))return;
    c.fillStyle='#ad492f';K.draw.circle(c,x,y,size*.38);
    c.fillStyle='#fdd090';K.draw.circle(c,x-size*.1,y-size*.1,size*.12);
  }

  function bunch(c, art, count, x, y, size){
    const columns=Math.min(count,2);
    for(let i=0;i<count;i++){
      const row=i<2?0:1, rowCount=row?count-2:columns;
      fruit(c,art,x+(i%2-(rowCount-1)/2)*size*.9,y+(row-(count>2?.5:0))*size*.86,size);
    }
  }

  function drawBasket(c, art, side, capacity, value, active){
    const x=bins[side];
    box(c,x-155,96,310,132,28,active?lights[side]:'#fbefd6');
    box(c,x-149,102,298,120,23,colors[side]);
    box(c,x-141,110,282,104,19,'#fff2d7');
    const cols=Math.min(capacity,4);
    for(let i=0;i<capacity;i++){
      const col=i%4, row=Math.floor(i/4);
      const px=x+(col-(cols-1)/2)*48,py=capacity>4?139+row*46:161;
      box(c,px-20,py-20,40,40,12,i<value?lights[side]:'#e7d7b9');
      if(i<value)fruit(c,art,px,py,36);
      else{c.strokeStyle='#ab987b';c.lineWidth=2;c.stroke();}
    }
    if(active){
      c.fillStyle=colors[side];
      c.beginPath();c.moveTo(x-12,229);c.lineTo(x+12,229);c.lineTo(x,245);c.closePath();c.fill();
    }
  }

  function draw(w,l,c,imgs,g){
    const art=imgs.icons.get('fruit');
    for(let side=0;side<2;side++)drawBasket(c,art,side,l.capacity[side],w.fill[side],side===w.side);

    const future=l.batches.slice(w.index+1);
    if(future.length){
      const gap=73,width=future.length*gap;
      box(c,640-width/2-12,112,width+24,94,24,'#314c3fe8');
      future.forEach(([quantity],i)=>{
        const x=640-width/2+gap*(i+.5);
        box(c,x-31,124,62,70,16,'#fff1d3');
        bunch(c,art,quantity,x,159,27);
      });
    }

    box(c,244,473,792,105,39,'#4a604cdd');
    const dropping=falling(w,l);
    lanes.forEach(x=>{
      const active=w.index<l.batches.length&&x===dropping.landing;
      box(c,x-54,490,108,9,4,active?'#ffe4a7':'#91ab85');
      if(active)box(c,x-30,505,60,6,3,'#dcb378');
    });
    const bounce=!g.reduce&&w.drive?3*Math.sin(g.t*20):0;
    if(!sprite(c,imgs.frames[0],w.x,521+bounce,220,126)){
      box(c,w.x-83,499,166,54,16,'#895c37');
      box(c,w.x-72,505,144,41,12,'#eed298');
      c.fillStyle='#523c2a';
      K.draw.circle(c,w.x-56,553,12);K.draw.circle(c,w.x+56,553,12);
    }
    box(c,w.x-28,556,56,10,5,colors[w.side]);
    box(c,w.x-18,558,36,6,3,lights[w.side]);
    if(w.index===l.batches.length)return;
    const {x,y,quantity}=dropping;
    box(c,x-55,y-37,110,74,28,w.delay>0?'#fff2d8c7':'#fff5de');
    bunch(c,art,quantity,x,y,35);
  }

  const options=create(config,{
    backdrop:'#678770',validate,reset,update,draw,
    controls:[['left','←','小车向左'],['right','→','小车向右'],['action','⇄','换篮']],
    goal:l=>l.batches.length,
    adapt(w,misses){w.help=misses>=2;},
    player:w=>center(w.x,521,200,126),
    target(w,l){const {x,y}=falling(w,l);return center(x,y,110,74);},
    goalAnchor:w=>center(bins[w.side],163,310,135),
    pilot(w,l){
      if(w.index>=l.batches.length)return bot();
      const {quantity,landing}=falling(w,l);
      const side=canFill(l.batches.slice(w.index+1),l.capacity[0]-w.fill[0]-quantity)?0:1;
      const keys=[];
      if(Math.abs(w.x-landing)>16)keys.push(w.x>landing?'left':'right');
      if(w.side!==side)keys.push('action');
      return bot(...keys);
    }
  });
  options.bubbleAt=()=>({x:565,y:644});
  return options;
};
