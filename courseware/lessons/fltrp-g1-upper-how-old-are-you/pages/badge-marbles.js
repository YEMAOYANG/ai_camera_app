K.ready({title:'年龄牌弹珠',sub:'听完整回答，瞄准对应的年龄牌再发射。'});

const numberBadges = {
  three:'__IMG:badge-three__', six:'__IMG:badge-six__', seven:'__IMG:badge-seven__',
  nine:'__IMG:badge-nine__', ten:'__IMG:badge-ten__',
};
const agePairs = Object.keys(numberBadges).map(age => [age, age]);
const hints = ['先重听。听清最后那个数字，再看牌。','看一看亮起的牌，再慢慢瞄准。'];
const feedback = {hint:'marble-hint',hint2:'marble-help',praise:'marble-praise'};

K.game(K.gameTemplates.magnetMarbles({
  art:{
    backdrop:'__IMG:marble-workshop__',sticker:'__IMG:reporter-sticker__',
    frames:['__IMG:amber-marble__'],icons:numberBadges,
  },
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'每张年龄牌都听准啦！',
  cues:[
    {...feedback,goal:'age-six'},
    {...feedback,steps:['age-nine','age-seven']},
    {...feedback,steps:['age-ten','age-three','age-six']},
  ],
  levels:[
    {
      pairs:agePairs,queue:['six'],targets:[{x:536,value:'nine'},{x:744,value:'six'}],
      speed:340,drift:0,targetWidth:156,targetHeight:110,listenOnly:true,hints,
    },
    {
      pairs:agePairs,queue:['nine','seven'],targets:[{x:420,value:'nine'},{x:640,value:'six'},{x:860,value:'seven'}],
      speed:410,drift:10,targetWidth:140,targetHeight:106,listenOnly:true,hints,
    },
    {
      pairs:agePairs,queue:['ten','three','six'],
      targets:[{x:365,value:'nine'},{x:548,value:'ten'},{x:732,value:'three'},{x:912,value:'six'}],
      speed:490,drift:18,targetWidth:128,targetHeight:102,listenOnly:true,hints,
    },
  ],
}));

const setGameState = K.onState;
K.onState = (state, content) => {
  if (state?.demo === false) {
    K.$$('.teach-hl').forEach(element => element.classList.remove('teach-hl'));
  }
  return setGameState.call(K, state, content);
};
