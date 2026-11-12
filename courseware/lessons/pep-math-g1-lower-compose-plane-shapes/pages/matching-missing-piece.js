K.ready({title:'弹珠送纸片补图',sub:'看待发纸片，瞄准同样的虚线空位。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:edge-check__';},{once:true});

const hints=['先看手里的纸片，再看虚线。','比一比边长和斜边朝向，再慢慢瞄准。'];
const common={goal:'marble-goal',hint:'marble-hint',hint2:'marble-help',praise:'marble-praise'};
const pairs=[
  ['p-narrow','g-narrow'],['p-wide','g-wide'],['p-diag','g-diag'],['p-small','g-small'],
  ['p-slant','g-slant'],['p-equi','g-equi'],['p-peaked','g-peaked'],
];
const options=K.gameTemplates.magnetMarbles({
  art:{
    backdrop:'__IMG:paper-table__',sticker:'__IMG:petal-sticker__',
    icons:{
      'p-narrow':'__IMG:piece-narrow__','g-narrow':'__IMG:gap-narrow__',
      'p-wide':'__IMG:piece-wide__','g-wide':'__IMG:gap-wide__',
      'p-diag':'__IMG:piece-diag__','g-diag':'__IMG:gap-diag__',
      'p-small':'__IMG:piece-small__','g-small':'__IMG:gap-small__',
      'p-slant':'__IMG:piece-slant__','g-slant':'__IMG:gap-slant__',
      'p-equi':'__IMG:piece-equi__','g-equi':'__IMG:gap-equi__',
      'p-peaked':'__IMG:piece-peaked__','g-peaked':'__IMG:gap-peaked__',
    },
  },
  voiceLead:true,
  stepVoiceLead:true,
  cues:[
    {...common,steps:['width-one','width-two']},
    {...common,steps:['half-large','half-small']},
    {...common,steps:['peak','slope','center']},
  ],
  doneText:'每个缺口都补出了完整的图形！',
  levels:[
    {targets:[{x:430,value:'g-narrow'},{x:846,value:'g-wide'}],queue:['p-narrow','p-wide'],
      targetWidth:188,targetHeight:128,speed:500,drift:8,pairs,hints},
    {targets:[{x:407,value:'g-small'},{x:852,value:'g-diag'}],queue:['p-diag','p-small'],
      targetWidth:170,targetHeight:128,speed:478,drift:17,pairs,hints},
    {targets:[{x:387,value:'g-slant'},{x:640,value:'g-equi'},{x:890,value:'g-peaked'}],
      queue:['p-peaked','p-slant','p-equi'],targetWidth:156,targetHeight:126,speed:455,drift:27,pairs,hints},
  ],
});

function loadPictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const picture=new Image();
    picture.src=src;
    return [key,picture];
  }));
}
const largePieces=loadPictures({
  'p-narrow':'__IMG:piece-narrow__','p-wide':'__IMG:piece-wide__','p-diag':'__IMG:piece-diag__',
  'p-small':'__IMG:piece-small__','p-slant':'__IMG:piece-slant__','p-equi':'__IMG:piece-equi__',
  'p-peaked':'__IMG:piece-peaked__',
});
const completed=loadPictures({
  'p-narrow':'__IMG:filled-narrow__','p-wide':'__IMG:filled-wide__','p-diag':'__IMG:filled-diag__',
  'p-small':'__IMG:filled-small__','p-slant':'__IMG:filled-slant__','p-equi':'__IMG:filled-equi__',
  'p-peaked':'__IMG:filled-peaked__',
});
function showPicture(context,picture,left,height){
  if(!picture?.complete||!picture.naturalWidth)return;
  context.fillStyle='#31574a';
  K.draw.rr(context,left,422,156,128,14);
  context.fill();
  const width=height*220/177;
  context.drawImage(picture,left+(156-width)/2,422+(128-height)/2,width,height);
}
options.drawTop=(game,context)=>{
  const {level,progress}=game.data;
  if(!level)return;
  const height=level.targetHeight-16;
  if(!game.auto||game.state==='play')showPicture(context,largePieces[level.queue[progress]],65,height);
  if(progress)showPicture(context,completed[level.queue[progress-1]],1082,height);
};
K.game(options);
K.$('[data-arc-input=action]').id='marble-launch';
const setTeacherState=K.onState;
K.onState=(state,content)=>{
  setTeacherState(state,content);
  if(state.pause===false||state.demo===false){
    for(const anchor of K.$$('.teach-hl'))anchor.classList.remove('teach-hl');
  }
};
