// Slide and rotate each falling piece. A bridge repair only counts when the
// piece covers exactly the cells in an empty opening.
K.gameTemplates.shapeBridge = config => {
  const {box,center,clamp,create,ease,bot,sprite}=Classic;
  const columns=9, rows=3, unit=66, left=343, dockY=380, startY=134;
  const width=cells=>Math.max(...cells.map(([x])=>x))+1;
  const height=cells=>Math.max(...cells.map(([,y])=>y))+1;
  const signature=cells=>cells.map(cell=>cell.join(',')).sort().join('|');
  function rotate(cells){
    const bottom=height(cells)-1;
    return cells.map(([x,y])=>[bottom-y,x]);
  }
  const area=(col,y,cells)=>center(left+(col+width(cells)/2)*unit,y+height(cells)*unit/2,
    width(cells)*unit,height(cells)*unit);

  function validate(level){
    if(!Array.isArray(level.slots)||level.slots.length<2||level.slots.length>4||
       !Number.isFinite(level.seconds)||level.seconds<3||level.seconds>9)throw new Error('invalid bridge level');
    const occupied=new Set();
    for(const slot of level.slots){
      const {col,cells,turns=0}=slot;
      if(!Number.isInteger(col)||col<0||!Number.isInteger(turns)||turns<0||turns>3||
         !Array.isArray(cells)||cells.length<2||cells.length>5||
         !cells.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isInteger)&&
           p[0]>=0&&p[0]<rows&&p[1]>=0&&p[1]<rows)||
         !cells.some(p=>p[0]===0)||!cells.some(p=>p[1]===0)||col+width(cells)>columns){
        throw new Error('invalid bridge opening');
      }
      const linked=[cells[0]];
      for(let i=0;i<linked.length;i++){
        const [x,y]=linked[i];
        for(const p of cells){
          if(Math.abs(x-p[0])+Math.abs(y-p[1])===1&&!linked.includes(p))linked.push(p);
        }
      }
      if(linked.length!==cells.length)throw new Error('bridge pieces must be connected');
      for(const [x,y] of cells){
        const key=(col+x)+','+y;
        if(occupied.has(key))throw new Error('bridge openings must not overlap');
        occupied.add(key);
      }
    }
  }

  function spawn(w,l){
    const slot=l.slots[w.index];
    if(!slot)return;
    w.cells=slot.cells;
    for(let i=0;i<(slot.turns||0);i++)w.cells=rotate(w.cells);
    w.col=Math.floor((columns-width(w.cells))/2);
    w.vx=w.col;w.fall=0;w.repeat=0;w.turnFx=0;
  }

  function reset(level){
    const world={index:0,filled:new Set(),delay:0,help:false};
    spawn(world,level);
    return world;
  }

  function matching(w,l){
    const mask=signature(w.cells);
    return l.slots.findIndex((slot,i)=>!w.filled.has(i)&&slot.col===w.col&&signature(slot.cells)===mask);
  }

  function nextOpening(w,l){
    const intended=l.slots[w.index];
    if(!intended)return l.slots.at(-1);
    let shape=intended.cells;
    const rotations=new Set();
    for(let turn=0;turn<4;turn++){
      rotations.add(signature(shape));
      shape=rotate(shape);
    }
    return l.slots.find((slot,i)=>!w.filled.has(i)&&rotations.has(signature(slot.cells)));
  }

  function update(w,l,input,dt,fb){
    if(w.index===l.slots.length)return;
    if(w.delay>0){
      w.delay-=dt;
      if(w.delay<=0)spawn(w,l);
      return;
    }
    w.repeat=Math.max(0,w.repeat-dt);
    w.turnFx=Math.max(0,w.turnFx-dt);
    const leftward=input.held('left')||input.press('left');
    const rightward=input.held('right')||input.press('right');
    const dx=Number(rightward)-Number(leftward);
    if(dx&&(w.repeat===0||input.press(dx<0?'left':'right'))){
      const col=clamp(w.col+dx,0,columns-width(w.cells));
      if(col!==w.col){
        w.col=col;
        fb.move();
        fb.fx(left+(col+.5)*unit,startY+(dockY-startY)*w.fall);
      }
      w.repeat=.2;
    }
    if(input.press('up')){
      w.cells=rotate(w.cells);
      w.col=Math.min(w.col,columns-width(w.cells));
      w.turnFx=.17;
      fb.jump();
      fb.fx(left+(w.col+.5)*unit,startY+(dockY-startY)*w.fall);
    }
    w.vx=ease(w.vx,w.col,dt,19);
    w.fall+=dt/(l.seconds*(w.help?1.5:1));
    if(w.fall<1&&!input.press('action'))return;
    fb.drop();
    const hit=matching(w,l),px=left+(w.col+width(w.cells)/2)*unit;
    if(hit<0){
      w.delay=.55;
      fb.lost(px,dockY+unit/2);
      return;
    }
    w.filled.add(hit);
    w.index++;
    w.delay=.42;
    fb.award(px,dockY+unit/2);
  }

  function blocks(c,cells,x,y,fill,outline){
    for(const [cx,cy] of cells){
      const bx=x+cx*unit,by=y+cy*unit;
      box(c,bx+2,by+2,unit-4,unit-4,10,fill);
      if(outline){
        c.lineWidth=3;c.strokeStyle=outline;c.stroke();
      }else{
        box(c,bx+13,by+13,unit-26,5,2,'#fff3c17a');
      }
    }
  }

  function draw(w,l,c,imgs,g){
    box(c,left-16,116,columns*unit+32,476,26,'#284837e8');
    for(let col=0;col<=columns;col++){
      box(c,left+col*unit-1,140,2,224,1,'#aac8a32b');
    }
    box(c,left-4,dockY-10,columns*unit+8,rows*unit+20,13,'#92704d');
    box(c,left,dockY,columns*unit,rows*unit,8,'#59776c');
    const mask=signature(w.cells);
    for(const [i,slot] of l.slots.entries()){
      const filled=w.filled.has(i), correct=w.help&&signature(slot.cells)===mask;
      blocks(c,slot.cells,left+slot.col*unit,dockY,filled?'#d49454':correct?'#ffe5a0':'#cbdac8',
        filled?null:correct?'#b56c37':'#edf6e2');
    }
    const finished=w.index===l.slots.length;
    if(finished)w.crossStart??=g.t;
    const cross=finished?clamp((g.t-w.crossStart)/.8,0,1):0;
    sprite(c,imgs.frames[finished?1:0],184+930*cross,487-Math.sin(Math.PI*cross)*110,151,158);
    if(finished||w.delay>0)return;
    blocks(c,w.cells,left+w.col*unit,dockY,'#ffd08935','#ffd79288');
    const y=startY+(dockY-startY)*Math.min(1,w.fall);
    const halfX=width(w.cells)*unit/2,halfY=height(w.cells)*unit/2;
    c.save();
    c.translate(left+w.vx*unit+halfX,y+halfY);
    if(!g.reduce)c.rotate(-Math.PI/2*w.turnFx/.17);
    blocks(c,w.cells,-halfX,-halfY,'#e7a45f',null);
    c.restore();
  }

  const options=create(config,{
    controls:['left','right',['up','↻','旋转木块'],['action','⇣','放下木块']],
    backdrop:'#71958a',validate,reset,update,draw,goal:l=>l.slots.length,
    adapt(w,misses){w.help=misses>=2;},
    player:w=>area(w.vx,startY+(dockY-startY)*Math.min(1,w.fall),w.cells),
    target(w,l){const slot=nextOpening(w,l);return area(slot.col,dockY,slot.cells);},
    goalAnchor:()=>center(left+columns*unit/2,dockY+rows*unit/2,columns*unit,rows*unit),
    pilot(w,l){
      if(w.delay>0||w.index===l.slots.length)return bot();
      const target=nextOpening(w,l);
      if(signature(w.cells)!==signature(target.cells))return bot('up');
      if(w.col===target.col)return bot('action');
      return w.repeat>0?bot():bot(w.col<target.col?'right':'left');
    }
  });
  options.bubbleAt=()=>({x:505,y:647});
  return options;
};
