K.ready({title:'落牌找竖邻',sub:'听上楼还是下楼。把票号落到同一竖列的邻号旁。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:same-column-27__';},{once:true});
const icons={
  24:'__IMG:ticket-24__',26:'__IMG:ticket-26__',32:'__IMG:ticket-32__',34:'__IMG:ticket-34__',
  42:'__IMG:ticket-42__',46:'__IMG:ticket-46__',53:'__IMG:ticket-53__',56:'__IMG:ticket-56__',
  57:'__IMG:ticket-57__',63:'__IMG:ticket-63__',67:'__IMG:ticket-67__',68:'__IMG:ticket-68__',78:'__IMG:ticket-78__',
  up:'__IMG:rule-up__',down:'__IMG:rule-down__',
};
const proof=Object.fromEntries(Object.entries({
  34:'__IMG:tile-proof-34__',53:'__IMG:tile-proof-53__',68:'__IMG:tile-proof-68__',
  42:'__IMG:tile-proof-42__',56:'__IMG:tile-proof-56__',67:'__IMG:tile-proof-67__',
}).map(([key,src])=>{
  const image=new Image();image.src=src;return [key,image];
}));
const hints=['先看这关是上楼还是下楼。','同一竖列的个位相同，再看相差几。'];
const cue={hint:'tile-hint',hint2:'tile-help',praise:'tile-praise'};
function level(down,bottom,pieces,interval){
  return {symbol:down>0?'down':'up',bottom,pieces,interval,hints,pairs:pieces.map(n=>[n,n-10*down])};
}
const options=K.gameTemplates.fallingTiles({
  art:{icons},voiceLead:true,stepVoiceLead:true,
  cues:[{...cue,steps:['tile-down']},{...cue,steps:['tile-up','tile-up-more']},
    {...cue,steps:['tile-down-again','tile-keep-down','tile-keep-down']}],
  levels:[
    level(1,[null,24,null,null,26,null],[34],1.22),
    level(-1,[null,63,null,null,78,null],[53,68],1.00),
    level(1,[null,32,null,46,null,57],[42,56,67],.79),
  ],doneText:'同一竖列，上下楼都找对了！',
});
options.drawTop=(game,context)=>{
  const {level,w}=game.data;
  if(!w||!w.i)return;
  const image=proof[level.pieces[w.i-1]];
  if(image?.complete&&image.naturalWidth)context.drawImage(image,41,300,333,188);
};
K.game(options);
K.$('[data-arc-input=action]').id='drop-ticket';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
