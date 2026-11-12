const orderCards = {
  'order-7-yuan': [700,'yuan','__IMG:order-7-yuan__'],
  'order-13-yuan': [1300,'yuan','__IMG:order-13-yuan__'],
  'order-one-yuan': [100,'jiao','__IMG:order-one-yuan__'],
  'order-one-jiao': [10,'fen','__IMG:order-one-jiao__'],
  'order-twenty-jiao': [200,'yuan','__IMG:order-twenty-jiao__'],
  'order-thirty-fen': [30,'jiao','__IMG:order-thirty-fen__'],
};
const bundles = {
  'target-7-yuan': [700,'yuan','__IMG:target-7-yuan__'],
  'target-13-yuan': [1300,'yuan','__IMG:target-13-yuan__'],
  'target-6-yuan': [600,'yuan','__IMG:target-6-yuan__'],
  'target-ten-jiao': [100,'jiao','__IMG:target-ten-jiao__'],
  'target-ten-fen': [10,'fen','__IMG:target-ten-fen__'],
  'target-nine-jiao': [90,'jiao','__IMG:target-nine-jiao__'],
  'target-two-yuan': [200,'yuan','__IMG:target-two-yuan__'],
  'target-three-jiao': [30,'jiao','__IMG:target-three-jiao__'],
  'target-two-jiao': [20,'jiao','__IMG:target-two-jiao__'],
  'target-three-yuan': [300,'yuan','__IMG:target-three-yuan__'],
};
const orderBoard=K.$('#exchange-order');
const orderPicture=K.$('#exchange-order-picture');
const toTargets=(...tokens)=>tokens.map((value,index)=>({x:tokens.length===3?[392,640,887][index]:[326,534,742,950][index],value}));
const matches=(orderKey,bundleKey)=>{
  const order=orderCards[orderKey], bundle=bundles[bundleKey];
  return Boolean(order&&bundle)&&order[0]===bundle[0]&&order[1]===bundle[1];
};
const levels=[
  {queue:['order-7-yuan','order-13-yuan'],targets:toTargets('target-13-yuan','target-7-yuan','target-6-yuan'),speed:475,drift:3},
  {queue:['order-one-yuan','order-one-jiao'],targets:toTargets('target-ten-fen','target-nine-jiao','target-ten-jiao'),speed:520,drift:9},
  {queue:['order-twenty-jiao','order-thirty-fen'],targets:toTargets('target-two-jiao','target-two-yuan','target-three-yuan','target-three-jiao'),speed:555,drift:13},
].map(level=>({...level,matches,targetWidth:186,targetHeight:126,listenOnly:true,
  hints:['先重听要换成哪种单位，再数靶上的每张或每枚。','比一比总金额，瞄准亮一点的靶。'],
}));
const title='把弹珠送到等额的图靶';
const config={
  title, sub:'听要换多少和换成哪种单位，找等额图靶，再瞄准发射。',
  voiceLead:true, stepVoiceLead:true, doneText:'每组换过以后，金额还是一样多。',
  art:{backdrop:'__IMG:reading-fair-booth__',sticker:'__IMG:book-badge__',frames:['__IMG:glass-marble__'],
    icons:Object.fromEntries(Object.entries(bundles).map(([key,value])=>[key,value[2]]))},
  levels,
  cues:levels.map(level=>({goal:level.queue[0],steps:level.queue,hint:'exchange-hint',hint2:'exchange-help',praise:'exchange-praise'})),
};
K.ready({title,sub:config.sub});
K.stage().append(orderBoard,K.$('#first-exchange-target'));
const game=K.gameTemplates.magnetMarbles(config);
const draw=game.draw;
game.draw=(g,context)=>{
  draw(g,context);
  const key=g.data.level?.queue[g.data.w?.i];
  orderBoard.hidden=g.state!=='play'||!key;
  if(key&&orderPicture.dataset.order!==key){
    orderPicture.src=orderCards[key][2];
    orderPicture.dataset.order=key;
  }
};
game.onState=(_,state)=>{
  if(state.demo===false)K.$$('.teach-hl',K.stage()).forEach(el=>el.classList.remove('teach-hl'));
};
K.game(game);
