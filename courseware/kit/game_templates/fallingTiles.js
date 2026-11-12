// Horizontal pairs are evaluated when a tile lands. The lesson supplies the
// semantic matching rule, the bottom row, and a queue of playable pieces.
K.gameTemplates.fallingTiles = config => {
  const {box,text,ease,center,create,bot,sprite,validToken,match:fits,token}=Classic;
  const cols=6,rows=7,s=70,ox=430,oy=106;
  const pair=(a,b,l)=>a!=null&&b!=null&&fits(a,b,l);
  const boardFor=l=>Array.from({length:rows},(_,y)=>y===rows-1?[...l.bottom]:Array(cols).fill(null));
  function land(board,x){let y=0;while(y+1<rows&&board[y+1][x]==null)y++;return y;}
  function match(board,x,y,v,l){
    return [-1,1].map(dx=>x+dx).find(nx=>nx>=0&&nx<cols&&pair(v,board[y][nx],l));
  }
  function place(board,x,v,l){
    if(board[0][x]!=null)return null;
    const y=land(board,x),other=match(board,x,y,v,l);
    if(other===undefined){board[y][x]=v;return {x,y};}
    for(let r=y;r>0;r--)board[r][other]=board[r-1][other];
    board[0][other]=null;
    return {x,y,other};
  }
  function validCols(board,v,l){
    return [...Array(cols).keys()].filter(x=>board[0][x]==null&&match(board,x,land(board,x),v,l)!==undefined);
  }
  function check(l){
    if(!Array.isArray(l.bottom)||l.bottom.length!==cols||!l.bottom.every(v=>v===null||validToken(v))||
       !Array.isArray(l.pieces)||!l.pieces.length||l.pieces.length>10||!l.pieces.every(validToken)||
       !(typeof l.matches==='function'||Array.isArray(l.pairs)||Number.isFinite(l.total))||
       !(l.interval>=0.22&&l.interval<=2.5))throw new Error('invalid tile level');
    const board=boardFor(l);
    for(const v of l.pieces){const x=validCols(board,v,l)[0];if(x===undefined)throw new Error('tile queue has no pilot solution');place(board,x,v,l);}
  }
  function spawn(w){w.x=2;w.y=0;w.vx=2;w.vy=-.65;w.elapsed=0;w.repeat=0;}
  function reset(l){
    const w={board:boardFor(l),i:0,delay:0,failureCount:0,flash:0};
    spawn(w);return w;
  }
  function update(w,l,input,dt,feedback){
    w.flash=Math.max(0,w.flash-dt);
    if(w.delay>0){w.delay-=dt;if(w.delay<=0)spawn(w);return;}
    const dx=(input.held('right')||input.press('right')?1:0)-(input.held('left')||input.press('left')?1:0);
    w.repeat=Math.max(0,w.repeat-dt);
    if(dx&&(w.repeat===0||input.press(dx<0?'left':'right'))){
      const nx=w.x+dx;
      if(nx>=0&&nx<cols&&w.board[w.y][nx]==null){w.x=nx;feedback.move();feedback.fx(ox+(nx+.5)*s,oy+(w.y+.5)*s);}
      w.repeat=.17;
    }
    const drop=input.press('action');
    const fast=input.held('down')||input.press('down');
    const interval=l.interval*(w.failureCount>=2?1.65:1)*(fast?.16:1);
    w.elapsed+=dt;
    if(drop||w.elapsed>=interval){
      if(drop)feedback.drop();
      w.elapsed=0;
      if(drop||w.y+1>=rows||w.board[w.y+1][w.x]!=null){
        const v=l.pieces[w.i],result=place(w.board,w.x,v,l);
        w.flash=.24;w.vx=w.x;
        const px=ox+(w.x+.5)*s,py=oy+((result?.y??0)+.5)*s;
        if(result?.other!==undefined){
          w.vy=result.y;w.i++;w.delay=.18;feedback.award(px,py);
        }else{
          // The loose tile remains as an obstacle until the second miss.
          // Rebuild the last reachable puzzle state so no child can get stuck.
          w.delay=.4;feedback.lost(px,py);
        }
        return;
      }
      w.y++;feedback.fx(ox+(w.x+.5)*s,oy+(w.y+.5)*s,'#eed2ab');
    }
    w.vx=ease(w.vx,w.x,dt);w.vy=ease(w.vy,w.y,dt);
  }
  function adapt(w,count){
    w.failureCount=count;
    if(count<2)return;
    const l=w.level;w.board=boardFor(l);
    for(const v of l.pieces.slice(0,w.i))place(w.board,validCols(w.board,v,l)[0],v,l);
  }
  function draw(w,l,c,imgs){
    box(c,ox-13,oy-13,cols*s+26,rows*s+26,18,'#233e36');
    box(c,ox,oy,cols*s,rows*s,6,'#19322e');
    const tile=(v,x,y,alpha=1)=>{
      c.save();c.globalAlpha=alpha;
      box(c,x+3,y+5,s-6,s-6,10,'#8e4f33');
      box(c,x+3,y+2,s-6,s-9,10,(typeof v==='number'?v%2:String(v).length%2)?'#ffce84':'#f6a575');
      box(c,x+12,y+8,s-24,5,3,'#fff0b584');
      token(c,imgs,v,x+s/2,y+s/2,s-12,s-13,l.labels,'#352b21');c.restore();
    };
    for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){
      box(c,ox+x*s+3,oy+y*s+3,s-6,s-6,9,'#304a3c');
      if(w.board[y][x]!=null)tile(w.board[y][x],ox+x*s,oy+y*s);
    }
    if(w.i<l.pieces.length&&w.delay<=0){
      const ghost=land(w.board,w.x);
      tile(l.pieces[w.i],ox+w.x*s,oy+ghost*s,.26);
      tile(l.pieces[w.i],ox+w.vx*s,oy+Math.max(-.15,w.vy)*s);
    }
    box(c,906,166,168,140,20,'#28493b');
    token(c,imgs,l.symbol??l.total??'↔',990,220,135,78,l.labels,'#fff1d3');
    text(c,String(w.i)+' / '+l.pieces.length,990,275,27,'#f7c581');
    if(w.i>0)sprite(c,imgs.sticker,990,380,109,109);
  }
  return create(config,{
    controls:['left','right','down',['action','⇣','快速落下']],backdrop:'#c99b63',validate:check,
    reset(l){return {...reset(l),level:l};},goal:l=>l.pieces.length,
    update,draw,adapt,
    player:w=>center(ox+(w.x+.5)*s,oy+(w.y+.5)*s,s,s),
    target:()=>center(ox+3*s,oy+6.5*s,s*6,s),
    pilot(w,l){
      if(w.delay>0)return bot();
      const good=validCols(w.board,l.pieces[w.i],l);
      const x=good.sort((a,b)=>Math.abs(a-w.x)-Math.abs(b-w.x))[0];
      if(x===undefined)return bot('action');
      if(x===w.x)return bot('action');
      return w.repeat>0?bot():bot(x<w.x?'left':'right');
    }
  });
};
