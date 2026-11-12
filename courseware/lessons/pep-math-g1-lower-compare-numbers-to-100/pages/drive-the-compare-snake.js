K.ready({title:'数牌小蛇',sub:'听清比较规则，开小蛇吃到符合关系的数牌。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:abacus-51-47__';},{once:true});
const values={
  39:'__IMG:snake-39__',46:'__IMG:snake-46__',54:'__IMG:snake-54__',56:'__IMG:snake-56__',
  58:'__IMG:snake-58__',62:'__IMG:snake-62__',69:'__IMG:snake-69__',70:'__IMG:snake-70__',
  73:'__IMG:snake-73__',74:'__IMG:snake-74__',76:'__IMG:snake-76__',79:'__IMG:snake-79__',81:'__IMG:snake-81__',
};
const signs={gt:'__IMG:sign-gt__',lt:'__IMG:sign-lt__',eq:'__IMG:sign-eq__'};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const cards=pictures({...values,...signs,blank:'__IMG:empty-token__'});
const results=pictures({
  '1-1':'__IMG:snake-proof-1-1__','2-1':'__IMG:snake-proof-2-1__','2-2':'__IMG:snake-proof-2-2__',
  '3-1':'__IMG:snake-proof-3-1__','3-2':'__IMG:snake-proof-3-2__','3-3':'__IMG:snake-proof-3-3__',
});
const hints=['再看看空格和右边的基准号。','先看十位，十位相同才看个位。'];
const cue={hint:'snake-hint',hint2:'snake-help',praise:'snake-praise'};
function level(start,seconds,walls,rounds){
  return {start,seconds,walls,rounds,hints};
}
const options=K.gameTemplates.compareSnake({
  art:{icons:values},voiceLead:true,stepVoiceLead:true,
  cues:[{...cue,steps:['snake-46-gt']},{...cue,steps:['snake-62-lt','snake-58-eq']},
    {...cue,steps:['snake-76-gt','snake-79-lt','snake-73-eq']}],
  levels:[
    level(46,.75,[],[{relation:'gt',foods:[[5,4,39],[6,4,54]]}]),
    level(62,.65,[],[{relation:'lt',foods:[[5,3,58],[7,4,69]]},
      {relation:'eq',foods:[[3,3,56],[5,1,58]]}]),
    level(76,.59,[[7,2],[4,2]],[{relation:'gt',foods:[[5,3,79],[7,4,74]]},
      {relation:'lt',foods:[[5,1,73],[3,3,81]]},{relation:'eq',foods:[[8,1,73],[2,1,70]]}]),
  ],doneText:'会按新的基准号继续比较了！',
});
function draw(context,image,x,y,w,h){
  if(image?.complete&&image.naturalWidth)context.drawImage(image,x,y,w,h);
}
options.drawTop=(game,context)=>{
  const {w,level}=game.data;
  if(!w)return;
  context.fillStyle='#284e43';
  K.draw.rr(context,1019,170,239,172,15);
  context.fill();
  const round=level.rounds[w.round];
  if(round){
    draw(context,cards.blank,1029,195,65,61);
    draw(context,cards[round.relation],1099,195,65,61);
    draw(context,cards[w.ref],1169,195,79,61);
  }else draw(context,cards[w.ref],1089,198,104,74);
  if(w.round)draw(context,results[(game.level+1)+'-'+w.round],1019,369,239,93);
};
K.game(options);
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
