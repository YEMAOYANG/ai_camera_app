K.ready({title:'把余量相同的两盘配对',sub:'看两张卡各剩多少，横移落块，贴着余量一样的底卡落下。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:twelve-before__';},{once:true});

const cards={
  '11-2':'__IMG:clip-card-11-2__','11-3':'__IMG:clip-card-11-3__','11-4':'__IMG:clip-card-11-4__',
  '12-3':'__IMG:clip-card-12-3__','12-4':'__IMG:clip-card-12-4__','12-5':'__IMG:clip-card-12-5__',
  '13-4':'__IMG:clip-card-13-4__','13-5':'__IMG:clip-card-13-5__',
};
const amounts={7:'__IMG:clip-amount-7__',8:'__IMG:clip-amount-8__',9:'__IMG:clip-amount-9__'};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const views=pictures(cards),results=pictures(amounts);
const diff=key=>{const [n,k]=key.split('-').map(Number);return n-k;};
const all=Object.keys(cards);
const pairs=all.flatMap(a=>all.filter(b=>a!==b&&diff(a)===diff(b)).map(b=>[a,b]));
const hints=['先算每盘还剩几个。','看看原有和取走是不是一起变，或者直接数留下的。'];
const cue={hint:'pair-hint',hint2:'pair-help',praise:'pair-praise'};
const options=K.gameTemplates.fallingTiles({
  art:{backdrop:'__IMG:sort-desk__',sticker:'__IMG:paper-star__',icons:cards},voiceLead:true,
  cues:[{...cue,goal:'pair-first'},{...cue,goal:'pair-second'},{...cue,goal:'pair-third'}],
  levels:[
    {bottom:['11-2',null,null,'11-3',null,null],pieces:['12-3','12-4'],interval:2.45,pairs,hints,symbol:'='},
    {bottom:[null,'11-4',null,'11-2',null,'11-3'],pieces:['12-5','12-3','12-4'],interval:2.15,pairs,hints,symbol:'='},
    {bottom:['12-5',null,'12-3',null,'12-4',null],pieces:['13-5','13-4','11-4'],interval:1.78,pairs,hints,symbol:'='},
  ],doneText:'不同算式的余量相同，都归档好了！',
});
function panel(context,image,x,y,width,height){
  if(!image?.complete||!image.naturalWidth)return;
  context.fillStyle='#2c5140';
  K.draw.rr(context,x,y,width,height,14);context.fill();
  const scale=Math.min((width-12)/image.naturalWidth,(height-12)/image.naturalHeight);
  const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
  context.drawImage(image,x+(width-w)/2,y+(height-h)/2,w,h);
}
options.drawTop=(game,context)=>{
  const {level,progress}=game.data;
  if(!level)return;
  if(!game.auto||game.state==='play')panel(context,views[level.pieces[progress]],46,220,165,165);
  if(progress)panel(context,results[diff(level.pieces[progress-1])],1078,419,157,142);
};
K.game(options);
K.$('[data-arc-input=action]').id='drop-comparison-card';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
