K.ready({title:'瞄准能合回原盘的余量',sub:'听原有和借出多少，看图选能合回总数的一盘。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:twelve-before__';},{once:true});

const icons={2:'__IMG:clip-amount-2__',3:'__IMG:clip-amount-3__',4:'__IMG:clip-amount-4__',5:'__IMG:clip-amount-5__',
  7:'__IMG:clip-amount-7__',8:'__IMG:clip-amount-8__',9:'__IMG:clip-amount-9__',10:'__IMG:clip-amount-10__'};
const originals={11:'__IMG:marble-total-11__',12:'__IMG:marble-total-12__',13:'__IMG:marble-total-13__'};
const completed={
  '11-2':'__IMG:joined-11-2__','11-3':'__IMG:joined-11-3__','11-4':'__IMG:joined-11-4__',
  '12-3':'__IMG:joined-12-3__','12-4':'__IMG:joined-12-4__','12-5':'__IMG:joined-12-5__',
  '13-4':'__IMG:joined-13-4__','13-5':'__IMG:joined-13-5__',
};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const groups=pictures(icons),trays=pictures(originals),joins=pictures(completed);
const hints=['先看原来有几个，再看借出了几个。','想一想两份合起来，能不能回到原来的数量。'];
const cue={hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'};
function level(total,queue,values,targetWidth,speed,drift){
  const targets=values.map((value,i)=>({x:[422,640,858][i],value}));
  return {total,queue,targets,targetWidth,targetHeight:124,speed,drift,hints};
}
const options=K.gameTemplates.magnetMarbles({
  art:{backdrop:'__IMG:marble-felt__',sticker:'__IMG:craft-rosette__',icons},
  voiceLead:true,stepVoiceLead:true,
  cues:[{...cue,goal:'aim-first',steps:['eleven-two','eleven-three','eleven-four']},
    {...cue,goal:'aim-second',steps:['twelve-three','twelve-four','twelve-five']},
    {...cue,goal:'aim-third',steps:['thirteen-four','thirteen-five']}],
  levels:[level(11,[2,3,4],[9,8,7],166,496,8),level(12,[3,4,5],[8,9,7],162,482,18),
    level(13,[4,5],[8,10,9],152,458,27)],
  doneText:'借出的和留下的合回每盘原来的数量！',
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
  panel(context,trays[level.total],44,197,166,165);
  if(!game.auto||game.state==='play')panel(context,groups[level.queue[progress]],56,401,155,128);
  if(progress)panel(context,joins[level.total+'-'+level.queue[progress-1]],1072,401,162,135);
};
K.game(options);
K.$('[data-arc-input=action]').id='release-the-marble';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
