K.ready({title:'舞台听音弹珠',sub:'听清要哪件道具，转动弹珠，瞄准图再发射。'});

const stagePairs = [['cat','cat'],['cap','cap'],['hat','hat']];
const stageFeedback = {hint:'stage-hint',hint2:'stage-help',praise:'stage-praise'};
const stageHints = ['先重听，再看帽舌、帽球或猫尾巴。','弹珠飞慢了，对准亮起来的图。'];

K.game(K.gameTemplates.magnetMarbles({
  voiceLead:true,
  stepVoiceLead:true,
  art:{
    backdrop:'__IMG:rhythm-stage__',
    sticker:'__IMG:hat-prop__',
    frames:['__IMG:game-stage-marble__'],
    icons:{cat:'__IMG:cat-prop__',cap:'__IMG:cap-prop__',hat:'__IMG:hat-prop__',bag:'__IMG:teaching-bag__'},
  },
  doneText:'道具都听准了，舞台贴纸到手！',
  cues:[
    {...stageFeedback,goal:'a-hat'},
    {...stageFeedback,goal:'a-cat',steps:['a-cat','a-cap']},
    {...stageFeedback,goal:'a-cap',steps:['a-cap','a-hat','a-cat']},
  ],
  levels:[
    {
      pairs:stagePairs,queue:['hat'],targets:[{x:495,value:'cat'},{x:744,value:'hat'}],
      speed:340,drift:0,targetWidth:156,targetHeight:110,listenOnly:true,hints:stageHints,
    },
    {
      pairs:stagePairs,queue:['cat','cap'],targets:[{x:415,value:'hat'},{x:640,value:'cat'},{x:850,value:'cap'}],
      speed:415,drift:11,targetWidth:140,targetHeight:104,listenOnly:true,hints:stageHints,
    },
    {
      pairs:stagePairs,queue:['cap','hat','cat'],
      targets:[{x:365,value:'cap'},{x:548,value:'hat'},{x:732,value:'cat'},{x:912,value:'bag'}],
      speed:505,drift:23,targetWidth:126,targetHeight:100,listenOnly:true,hints:stageHints,
    },
  ],
}));
