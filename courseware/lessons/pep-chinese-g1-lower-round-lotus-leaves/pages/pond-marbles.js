const pairs = [['listen-lie','lie'],['listen-spread','spread'],['listen-crouch','crouch'],['listen-swim','swim']];
const config = {
  title:'听动作发射露珠弹',
  sub:'先听老师说的动作，再转动发射口，对准那幅图。',
  doneText:'画面都配到了合适的动作。',
  voiceLead:true,
  stepVoiceLead:true,
  art:{
    sticker:'__IMG:lotus-sticker__',
    frames:['__IMG:pond-marble__'],
    icons:{
      lie:'__IMG:drop-on-leaf__',spread:'__IMG:dragonfly-on-leaf__',
      crouch:'__IMG:frog-on-leaf__',swim:'__IMG:fish-under-leaf__'
    }
  },
  levels:[
    {
      pairs,listenOnly:true,targetWidth:150,targetHeight:114,speed:390,drift:10,
      targets:[{x:500,value:'lie'},{x:785,value:'spread'},{x:965,value:'crouch'}],
      queue:['listen-lie','listen-spread'],
      hints:['再听一遍，看看角色的身体在做什么。','露珠弹慢下来了，对着亮起的图试一试。']
    },
    {
      pairs,listenOnly:true,targetWidth:152,targetHeight:110,speed:495,drift:20,
      targets:[{x:395,value:'crouch'},{x:640,value:'swim'},{x:885,value:'spread'}],
      queue:['listen-spread','listen-swim'],
      hints:['先听是在叶上，还是在叶子下边。','对准发亮的那幅图，再发出露珠。']
    },
    {
      pairs,listenOnly:true,targetWidth:148,targetHeight:106,speed:600,drift:27,
      targets:[{x:330,value:'lie'},{x:535,value:'spread'},{x:740,value:'crouch'},{x:945,value:'swim'}],
      queue:['listen-crouch','listen-swim','listen-lie'],
      hints:['动作不同，图里身体的位置也不同。','图卡会动，露珠在路上也能调方向。']
    }
  ],
  cues:[
    {goal:'listen-lie',hint:'action-hint',hint2:'action-help',praise:'action-praise',steps:['listen-lie','listen-spread']},
    {goal:'listen-spread',hint:'action-hint',hint2:'action-help',praise:'action-praise',steps:['listen-spread','listen-swim']},
    {goal:'listen-crouch',hint:'action-hint',hint2:'action-help',praise:'action-praise',steps:['listen-crouch','listen-swim','listen-lie']}
  ]
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#lotus-listen-mark'),K.$('#lotus-first-action'));
const activity = K.gameTemplates.magnetMarbles(config);
activity.onState = (_,state) => {
  if (state.demo === false) {
    K.$$('.teach-hl',K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
