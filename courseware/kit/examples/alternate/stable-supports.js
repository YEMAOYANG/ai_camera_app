// Course-owned sample for K.gameTemplates.arcade. The lesson provides supportConfig.
(() => {
  const text=K.draw.text;
  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
  const center=(x,y,w,h)=>({x:x-w/2,y:y-h/2,w,h});
  const bot=(...keys)=>({held:key=>keys.includes(key),press:key=>keys.includes(key)});
  function box(c,x,y,w,h,r,fill){
    K.draw.rr(c,x,y,w,h,r);
    c.fillStyle=fill;
    c.fill();
  }
  const gridX=460, gridY=350, unitX=83, unitZ=67, rack=3;
  const colors=['#4B8676','#BF754B','#647D9D','#A78345'];
  const shapes=new Set(['cube','cylinder','roller','sphere']);
  const hints={
    base:'这个物块会滚，先找底面能放稳的。',
    height:'看侧面，三个顶面还不一样高。',
    line:'三个支点排成了直线，球会往两边滚。',
    spacing:'支点离球底的接触圈太远或太近。',
    outside:'球心还在三角形外，试试从周围托住。',
  };
  const validPosition=point=>Array.isArray(point)&&point.length===2&&point.every(Number.isInteger)&&
    Math.abs(point[0])<=3&&Math.abs(point[1])<=2;
  const same=(a,b)=>a[0]===b[0]&&a[1]===b[1];
  const display=([x,z])=>[gridX+x*unitX,gridY+z*unitZ];
  const rackPosition=i=>[i-2,rack];
  const stableBase=block=>block.shape==='cube'||block.shape==='cylinder';
  const cross=([ax,az],[bx,bz],[cx,cz])=>(bx-ax)*(cz-az)-(bz-az)*(cx-ax);
  const radius=([x,z])=>Math.hypot(x,z);

  function failure(placed, level){
    const [a,b,c]=placed.map(s=>s.at);
    const blocks=placed.map(s=>level.blocks[s.block]);
    if(blocks.some(block=>!stableBase(block)))return 'base';
    if(blocks.some(block=>block.height!==blocks[0].height))return 'height';
    if(cross(a,b,c)===0)return 'line';
    if([a,b,c].some(at=>Math.abs(radius(at)-level.contactRadius)>level.tolerance))return 'spacing';
    const origin=[0,0], sides=[cross(a,b,origin),cross(b,c,origin),cross(c,a,origin)];
    if(!(sides.every(n=>n>0)||sides.every(n=>n<0)))return 'outside';
    return null;
  }

  function findSolution(level){
    const block=level.blocks.findIndex(stableBase);
    if(block<0)return null;
    const positions=level.sockets;
    for(let a=0;a<positions.length-2;a++){
      for(let b=a+1;b<positions.length-1;b++){
        for(let c=b+1;c<positions.length;c++){
          const placement=[positions[a],positions[b],positions[c]].map(at=>({at,block}));
          if(!failure(placement,level))return placement;
        }
      }
    }
    return null;
  }

  function validate(level){
    if(!Array.isArray(level.sockets)||level.sockets.length<3||level.sockets.length>18||
       !level.sockets.every(validPosition)||new Set(level.sockets.map(String)).size!==level.sockets.length||
       !Array.isArray(level.blocks)||level.blocks.length<1||level.blocks.length>4||
       !level.blocks.every(block=>block&&shapes.has(block.shape)&&Number.isInteger(block.height)&&block.height>=1&&block.height<=3)||
       !Number.isFinite(level.contactRadius)||level.contactRadius<1||level.contactRadius>3||
       !Number.isFinite(level.tolerance)||level.tolerance<.05||level.tolerance>.6||
       !Number.isFinite(level.step)||level.step<.10||level.step>.25||!findSolution(level)){
      throw new Error('support layout needs a solvable three-point contact configuration');
    }
  }

  function reset(level){
    return {cursor:[0,0],selection:0,placed:[],solution:findSolution(level),
      cooldown:0,reason:null,solved:false,help:false};
  }

  const directions=[['left',-1,0],['right',1,0],['up',0,-1],['down',0,1]];
  function update(w,l,input,dt,fb){
    if(w.solved)return;
    w.cooldown=Math.max(0,w.cooldown-dt);
    const [x,z]=w.cursor;
    const move=directions.find(([key])=>input.held(key)||input.press(key));
    if(move&&w.cooldown===0){
      w.cursor=[clamp(x+move[1],-3,3),clamp(z+move[2],-2,3)];
      w.cooldown=l.step;
      if(!same([x,z],w.cursor)){fb.move();fb.fx(...display(w.cursor),'#ccebd2');}
    }
    if(!input.press('action'))return;
    const [sx,sz]=w.cursor;
    if(sz===rack){
      const chosen=sx+2;
      if(chosen>=0&&chosen<l.blocks.length){w.selection=chosen;fb.drop();fb.fx(...display(w.cursor));}
      return;
    }
    const placed=w.placed.findIndex(s=>same(s.at,w.cursor));
    if(placed>=0){
      w.selection=w.placed[placed].block;
      w.placed.splice(placed,1);
      w.reason=null;
      fb.move();
      return;
    }
    if(w.placed.length===3||!l.sockets.some(at=>same(at,w.cursor)))return;
    w.placed.push({at:w.cursor,block:w.selection});
    const [px,py]=display(w.cursor);
    fb.drop();fb.fx(px,py,'#ffe4a6');
    if(w.placed.length<3)return;
    w.reason=failure(w.placed,l);
    if(w.reason)fb.lost(px,py);
    else{w.solved=true;fb.award(px,py);}
  }

  function shape(c,block,x,base,width,height,color){
    const top=base-height;
    if(block.shape==='sphere'||block.shape==='roller'){
      c.fillStyle=color;
      c.beginPath();c.ellipse(x,top+height/2,width/2,height/2,0,0,Math.PI*2);c.fill();
      return;
    }
    box(c,x-width/2,top,width,height,block.shape==='cylinder'?width*.20:4,color);
    box(c,x-width/2+5,top+4,width-10,8,4,'#fff3b982');
    for(let i=1;i<block.height;i++){
      const y=top+i*height/block.height;
      box(c,x-width/2+6,y-1,width-12,2,1,'#fff0c96e');
    }
  }

  function circle(c,x,y,r,color){
    c.fillStyle=color;
    K.draw.circle(c,x,y,r);
  }

  function draw(w,l,c,images,g){
    box(c,153,155,614,431,38,'#294b41');
    box(c,168,172,584,331,30,'#315b4b');
    box(c,168,514,584,59,22,'#213e36');
    for(let z=-2;z<=2;z++){
      for(let x=-3;x<=3;x++){
        const [px,py]=display([x,z]);
        circle(c,px,py,3,'#91b2a0');
      }
    }
    c.beginPath();c.ellipse(gridX,gridY,l.contactRadius*unitX,l.contactRadius*unitZ,0,0,Math.PI*2);
    c.fillStyle=w.solved?'#f8ce6c55':'#f6df9841';c.fill();
    c.strokeStyle=w.solved?'#ffe29a':'#b3d2a7';c.lineWidth=3;c.setLineDash([7,8]);c.stroke();c.setLineDash([]);
    circle(c,gridX,gridY,10,w.solved?'#fff3ae':'#f3d59a');
    for(const at of l.sockets){
      const [x,y]=display(at);
      const useful=w.help&&Math.abs(radius(at)-l.contactRadius)<=l.tolerance;
      box(c,x-20,y-17,40,34,12,useful?'#efcb83':'#548374');
      circle(c,x,y,5,useful?'#80512d':'#a9c9b3');
    }
    if(w.placed.length===3){
      const [a,...rest]=w.placed.map(s=>display(s.at));
      c.beginPath();c.moveTo(...a);rest.forEach(p=>c.lineTo(...p));c.closePath();
      c.fillStyle=w.solved?'#f8c9576a':'#ee8f6650';c.fill();
      c.strokeStyle=w.solved?'#fff2ad':'#ffc099';c.lineWidth=4;c.stroke();
    }
    for(const placed of w.placed){
      const [x,y]=display(placed.at), block=l.blocks[placed.block];
      shape(c,block,x,y+17,43,23,colors[placed.block]);
    }
    l.blocks.forEach((block,i)=>{
      const [x,y]=display(rackPosition(i));
      box(c,x-27,y-25,54,49,11,i===w.selection?'#f6d58c':'#467468');
      shape(c,block,x,y+14,36,15+block.height*5,colors[i]);
    });
    const [x,y]=display(w.cursor);
    K.draw.rr(c,x-30,y-27,60,54,12);
    c.lineWidth=4;c.strokeStyle='#fff1b3';c.stroke();

    box(c,795,155,390,430,37,'#fff4d9');
    box(c,816,176,348,302,25,'#f3dbab');
    const floor=438;
    box(c,839,floor,301,12,5,'#aa7956');
    const ballR=63, contactSpan=46;
    const height=w.solved?l.blocks[w.placed[0].block].height:0;
    const ballY=w.solved?floor-34*height-Math.sqrt(ballR**2-contactSpan**2):267;
    const sway=!g.reduce&&['line','outside'].includes(w.reason)?Math.sin(g.t*6)*15:0;
    circle(c,991+sway,ballY,ballR,w.solved?'#E99C3A':'#D9984D');
    circle(c,974+sway,ballY-16,17,'#fff3b4');
    w.placed.forEach((support,i)=>{
      const block=l.blocks[support.block];
      const sideX=w.solved?991+support.at[0]/l.contactRadius*contactSpan:883+i*107;
      shape(c,block,sideX,floor,w.solved?32:55,34*block.height,colors[support.block]);
    });
    const label=w.solved?'球从下方托稳了':w.reason?hints[w.reason]:'把三个支点放在球的下方';
    text(c,label,990,525,20,w.reason?'#8C452E':'#30574A');
  }

  const game=K.gameTemplates.arcade(supportConfig,{
    backdrop:'#d1bb8b',
    controls:['left','right','up','down',['action','◎','选积木或放下支点']],
    validate,reset,update,draw,goal:()=>1,
    adapt(w,misses){w.help=misses>=2;},
    player(w){return center(...display(w.cursor),64,58);},
    target(){return center(gridX,gridY,530,310);},
    goalAnchor(){return center(991,269,115,110);},
    pilot(w){
      const extra=w.placed.find(s=>!w.solution.some(t=>same(s.at,t.at)&&s.block===t.block));
      const next=w.solution.find(s=>!w.placed.some(t=>same(s.at,t.at)));
      const at=extra?.at??(next&&(next.block!==w.selection?rackPosition(next.block):next.at));
      if(!at||w.cooldown>0)return bot();
      const [x,z]=w.cursor;
      if(x!==at[0])return bot(x<at[0]?'right':'left');
      if(z!==at[1])return bot(z<at[1]?'down':'up');
      return bot('action');
    },
  });
  const updateGame=game.update;
  game.update=(g,dt)=>{
    const count=g.data.w.placed.length;
    updateGame(g,dt);
    if(g.data.w.placed.length>count)g.demoAction();
  };
  game.bubbleAt=()=>({x:395,y:650});
  K.game(game);
})();
