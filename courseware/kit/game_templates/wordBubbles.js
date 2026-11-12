// Float a bubble into the picture named by the current recorded cue.
// Cards drift sideways while bubbles travel, so aim where the card is going.
K.gameTemplates.wordBubbles = config => {
  const {box,center,clamp,create,bot,sprite,token,validToken}=Classic;
  const cardY=250, boatY=515, launchY=boatY-45, rise=475, speed=410;
  const flight=(launchY-cardY)/rise, left=260, right=1020;

  function validate({rounds,drift,pace,tolerance}){
    if(!Array.isArray(rounds)||rounds.length<2||rounds.length>5||
       !rounds.every(r=>r&&Array.isArray(r.cards)&&[2,3].includes(r.cards.length)&&
         r.cards.every(validToken)&&new Set(r.cards.map(String)).size===r.cards.length&&r.cards.includes(r.target))||
       !Number.isFinite(drift)||drift<0||drift>60||
       !Number.isFinite(pace)||pace<0.4||pace>1.8||
       !Number.isFinite(tolerance)||tolerance<44||tolerance>62)
      throw new Error('word bubbles need distinct cards with a target and a playable drift');
  }

  function reset(){return {x:640,t:0,round:0,drive:0,shot:null,help:false,caught:null,pulse:0};}

  const slow=w=>w.help?.55:1;
  function cardX(w,l,i,t=w.t){
    const count=l.rounds[w.round].cards.length, gap=count===2?310:238;
    return 640+(i-(count-1)/2)*gap+Math.sin(t*l.pace+i*1.48+w.round*.9)*l.drift;
  }

  function update(w,l,input,dt,fb){
    if(w.round===l.rounds.length)return;
    const dx=Number(input.held('right')||input.press('right'))-Number(input.held('left')||input.press('left'));
    if(dx&&dx!==w.drive){fb.move();fb.fx(w.x,boatY+31,'#b4ede4');}
    w.drive=dx;
    w.x=clamp(w.x+dx*speed*dt,left,right);
    w.pulse=Math.max(0,w.pulse-dt);
    if(input.press('action')&&!w.shot){
      w.shot={x:w.x,y:launchY};
      w.pulse=.22;
      fb.drop();fb.fx(w.x,launchY,'#e9fffb');
    }
    const shot=w.shot;
    // Sample the card at the exact moment of impact, independent of frame rate.
    const travel=shot?Math.min(dt,(shot.y-cardY)/rise):dt;
    w.t+=travel*slow(w);
    if(!shot)return;
    shot.y-=travel*rise;
    if(shot.y>cardY+.00001)return;
    w.shot=null;
    const {cards,target}=l.rounds[w.round];
    const targetX=cardX(w,l,cards.indexOf(target));
    if(Math.abs(shot.x-targetX)>l.tolerance+(w.help?8:0)){
      fb.lost(shot.x,cardY);
      return;
    }
    w.caught={x:targetX,token:target};
    w.round++;
    fb.award(targetX,cardY);
  }

  function bubble(c,x,y,r){
    c.fillStyle='#d4fffa96';K.draw.circle(c,x,y,r);
    c.strokeStyle='#f5fff9';c.lineWidth=4;c.stroke();
    c.fillStyle='#ffffffd5';K.draw.circle(c,x-r*.27,y-r*.37,r*.21);
  }

  function draw(w,l,c,imgs,g){
    box(c,213,132,854,438,53,'#134b55dc');
    box(c,221,141,838,420,48,'#347b7be8');
    box(c,241,452,798,91,40,'#236666');
    for(let i=0;i<6;i++){
      const y=467+i*12;
      c.beginPath();c.moveTo(267,y);
      c.bezierCurveTo(485,y-12,812,y+12,1013,y);
      c.strokeStyle=i%2?'#397e7c':'#4b9291';c.lineWidth=2;c.stroke();
    }
    for(let i=0;i<l.rounds.length;i++){
      const x=640+(i-(l.rounds.length-1)/2)*32;
      c.fillStyle=i<w.round?'#ffdb80':'#9ac8bb';
      K.draw.circle(c,x,160,i===w.round?9:6);
    }
    const round=l.rounds[w.round];
    if(round){
      round.cards.forEach((value,i)=>{
        const x=cardX(w,l,i), guided=w.help&&value===round.target;
        const r=guided?66:56;
        box(c,x-r,cardY-58,r*2,120,28,guided?'#ffd276':'#99cabc');
        box(c,x-51,cardY-50,102,102,24,'#fff1d1');
        token(c,imgs,value,x,cardY,83,83,config.labels);
      });
    }
    if(w.caught){
      const {x}=w.caught;
      const y=round?357:cardY;
      bubble(c,x,y,round?24:56);
      token(c,imgs,w.caught.token,x,y,round?34:85,round?34:85,config.labels);
    }
    const bob=g.reduce?0:Math.sin(g.t*6)*3;
    c.fillStyle='#103e49a0';
    c.beginPath();c.ellipse(w.x,boatY+42,55,10,0,0,Math.PI*2);c.fill();
    // The source frames face right. Turn their nozzle toward the launch point.
    if(!sprite(c,imgs.frames[w.pulse>0?1:0],w.x,boatY+3+bob,114,106,{angle:-Math.PI/2})){
      box(c,w.x-50,boatY-9+bob,100,34,15,'#ffcf84');
      box(c,w.x-9,launchY+bob,18,29,6,'#ffcf84');
      box(c,w.x-23,boatY-28+bob,46,29,14,'#e4fff0');
    }
    if(w.shot)bubble(c,w.shot.x,w.shot.y,19);
    else bubble(c,w.x,launchY+bob,10);
  }

  const options=create(config,{
    backdrop:'#6d967c',validate,reset,update,draw,
    controls:[['left','←','小艇向左'],['right','→','小艇向右'],['action','◎','吹泡泡']],
    goal:l=>l.rounds.length,
    adapt(w,misses){w.help=misses>=2;},
    player:w=>center(w.x,boatY,136,106),
    target(w,l){
      const round=l.rounds[w.round];
      return round?center(cardX(w,l,round.cards.indexOf(round.target)),cardY,112,118):null;
    },
    goalAnchor:()=>center(640,250,790,130),
    pilot(w,l){
      const round=l.rounds[w.round];
      if(!round||w.shot)return bot();
      const x=cardX(w,l,round.cards.indexOf(round.target),w.t+flight*slow(w));
      if(Math.abs(w.x-x)<=10)return bot('action');
      return bot(w.x>x?'left':'right');
    }
  });
  options.bubbleAt=()=>({x:540,y:647});
  return options;
};
