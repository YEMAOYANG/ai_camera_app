K.ready({title:'沿着同一步长走到停止点',sub:'每次减去同样多。找这次剩下的数量，再往前。'});
const start = K.$('#ready .pic');
start.style.objectFit = 'contain';
start.addEventListener('error', () => { start.src = '__IMG:arrow-main__'; }, {once:true});

const cards={
  A:'__IMG:station-12__',B:'__IMG:station-7__',C:'__IMG:station-2__',
  D:'__IMG:station-15__',F:'__IMG:station-10__',G:'__IMG:station-5__',H:'__IMG:station-0__',
  J:'__IMG:station-21__',K:'__IMG:station-9__',L:'__IMG:station-3__'
};
const hints=['先看左边还剩多少，再拿走一整份。','重听每份几个，再找下一站的剩余量。'];
const levels=[
  {total:17,group:5,route:['A','B','C'],legend:['C','A','B'],
    map:['#########','#.....C.#','#....B..#','#...#...#','#..A....#','#S....#E#','#########'],
    listenOnly:true,step:.34,hints},
  {total:20,group:5,route:['D','F','G','H'],legend:['F','H','D','G'],
    map:['#########','#..H....#','#.....G.#','#.F.#...#','#....D..#','#S....#E#','#########'],
    listenOnly:true,step:.29,hints},
  {total:27,group:6,route:['J','D','K','L'],legend:['K','J','L','D'],
    map:['#########','#....L..#','#.K.....#','#..#..D.#','#..J....#','#S....#E#','#########'],
    listenOnly:true,step:.24,hints}
];
const options=K.gameTemplates.bubbleMaze({
  art:{backdrop:'__IMG:backstage-path__',sticker:'__IMG:finish-sticker__',
       frames:['__IMG:pack-cart__'],icons:cards},
  levels,voiceLead:true,stepVoiceLead:true,
  cues:[
    {goal:'route-five',hint:'route-hint',hint2:'route-help',praise:'route-praise',
      steps:['route-five','route-five','route-five','route-stop']},
    {goal:'route-five',hint:'route-hint',hint2:'route-help',praise:'route-praise',
      steps:['route-five','route-five','route-five','route-five','route-stop']},
    {goal:'route-six',hint:'route-hint',hint2:'route-help',praise:'route-praise',
      steps:['route-six','route-six','route-six','route-six','route-stop']}
  ],
  doneText:'每走一步就装满一份。剩下不够就到旗子。'
});
const gallery=Object.fromEntries(Object.entries(cards).map(([key,url])=>{
  const image=new Image();
  image.src=url;
  return [key,image];
}));
function panel(ctx,x,y,width,height){
  ctx.fillStyle='#fff0cf';
  K.draw.rr(ctx,x,y,width,height,18);
  ctx.fill();
}
options.drawTop=(game,ctx)=>{
  const {w,level}=game.data;
  if(!level||!w)return;
  const done=Math.min(w.i,level.route.length);
  const remaining=level.total-done*level.group;
  panel(ctx,45,105,244,144);
  K.draw.text(ctx,String(remaining),101,169,53,'#284c46');
  for(let i=0;i<remaining;i++){
    ctx.fillStyle='#a3403d';K.draw.circle(ctx,157+i%6*18,132+Math.floor(i/6)*18,6);
  }
  panel(ctx,45,273,244,116);
  K.draw.text(ctx,'−'+String(level.group),97,328,40,'#284c46');
  for(let i=0;i<level.group;i++){
    ctx.fillStyle='#a3403d';K.draw.circle(ctx,149+i*19,328,7);
  }
  panel(ctx,45,413,244,98);
  for(let i=0;i<done;i++){
    const x=71+i*51;
    ctx.fillStyle='#e8b967';K.draw.rr(ctx,x,442,34,38,6);ctx.fill();
    ctx.fillStyle='#315e51';K.draw.rr(ctx,x+6,448,22,4,2);ctx.fill();
  }
  panel(ctx,984,110,248,252);
  level.legend.forEach((key,index)=>{
    const image=gallery[key];
    if(image.complete&&image.naturalWidth){
      ctx.drawImage(image,995+index%2*118,121+Math.floor(index/2)*118,106,106);
    }
  });
};
options.onState=(_game,state)=>{
  if(state.pause===false||state.demo===false){
    for(const anchor of K.$$('.teach-hl'))anchor.classList.remove('teach-hl');
  }
};
K.game(options);
