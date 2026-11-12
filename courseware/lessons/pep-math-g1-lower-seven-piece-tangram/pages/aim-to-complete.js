K.ready({title:'弹珠帮忙送板',sub:'比边和角，瞄准刚好能补上的缺口。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:one-complete-set__';},{once:true});

const pictures={
  large:['__IMG:loose-large__','__IMG:target-large__','__IMG:finished-large__'],
  small:['__IMG:loose-small__','__IMG:target-small__','__IMG:finished-small__'],
  square:['__IMG:loose-square__','__IMG:target-square__','__IMG:finished-square__'],
  corner:['__IMG:loose-corner__','__IMG:target-corner__','__IMG:finished-corner__'],
  medium:['__IMG:loose-medium__','__IMG:target-medium__','__IMG:finished-medium__'],
  slant:['__IMG:loose-slant__','__IMG:target-slant__','__IMG:finished-slant__'],
  'added-large':['__IMG:loose-added-large__','__IMG:target-added-large__','__IMG:finished-added-large__'],
};
const icons={},pairs=[],onTable={},filled={};
for(const [name,[piece,gap,result]] of Object.entries(pictures)){
  const key='p-'+name, target='g-'+name;
  icons[key]=piece;icons[target]=gap;pairs.push([key,target]);
  onTable[key]=new Image();onTable[key].src=piece;
  filled[key]=new Image();filled[key].src=result;
}
const hints=['停一下，比一比边长和角。','想象把板移进虚线，看看会不会露出。'];
const cue={hint:'marble-hint',hint2:'marble-help',praise:'marble-praise'};
function level(targets,queue,targetWidth,targetHeight,speed,drift){
  return {targets:targets.map(([x,key])=>({x,value:'g-'+key})),queue:queue.map(name=>'p-'+name),
    targetWidth,targetHeight,speed,drift,pairs,hints};
}
const options=K.gameTemplates.magnetMarbles({
  art:{backdrop:'__IMG:worktable__',sticker:'__IMG:show-rosette__',icons},
  voiceLead:true,
  cues:[{...cue,goal:'big-gap'},{...cue,goal:'corner-gap'},{...cue,goal:'medium-gap'}],
  levels:[
    level([[430,'large'],[846,'small']],['large','small'],186,128,500,8),
    level([[407,'square'],[852,'corner']],['corner','square'],174,128,485,16),
    level([[389,'slant'],[640,'medium'],[889,'added-large']],['medium','slant','added-large'],160,128,462,24),
  ],doneText:'七巧板的缺口都贴合了！',
});
function show(context,image,left,height){
  if(!image?.complete||!image.naturalWidth)return;
  const width=height*220/192;
  context.fillStyle='#315747';
  K.draw.rr(context,left,422,156,128,13);context.fill();
  context.drawImage(image,left+(156-width)/2,422+(128-height)/2,width,height);
}
options.drawTop=(game,context)=>{
  const {level,progress}=game.data;
  if(!level)return;
  const height=level.targetHeight-16;
  if(!game.auto||game.state==='play')show(context,onTable[level.queue[progress]],65,height);
  if(progress)show(context,filled[level.queue[progress-1]],1082,height);
};
K.game(options);
K.$('[data-arc-input=left]').id='aim-left';
K.$('[data-arc-input=action]').id='launch-piece';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
