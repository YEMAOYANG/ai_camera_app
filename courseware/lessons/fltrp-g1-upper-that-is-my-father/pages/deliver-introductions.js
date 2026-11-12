K.ready({title:'送访客卡到灯影展',sub:'听完介绍再拿卡。看图站和说话者隔多远。'});
const opening = K.$('#ready .pic');
opening.style.objectFit = 'contain';
opening.addEventListener('error', () => { opening.src = '__IMG:welcome__'; }, {once:true});

const hints = ['先重听。这次是拿卡，还是送卡？','先找正在说的人，再看他和灯之间有多远。'];
const feedback = {goal:'delivery-goal',hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise'};

K.game(K.gameTemplates.listenDelivery({
  art:{
    backdrop:'__IMG:lantern-hall__',sticker:'__IMG:friend-a__',
    frames:['__IMG:lantern-van__','__IMG:lantern-van__'],
    icons:{
      'father-a':'__IMG:father-a__','mother-a':'__IMG:mother-a__',
      'grandpa-a':'__IMG:grandpa-a__','grandma-a':'__IMG:grandma-a__','friend-a':'__IMG:friend-a__',
      'father-b':'__IMG:father-b__',
      'near-a':'__IMG:near-a__','far-a':'__IMG:far-a__','near-mother':'__IMG:near-mother__',
      'far-mother':'__IMG:far-mother__','near-b':'__IMG:near-b__','far-b':'__IMG:far-b__',
    },
  },
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'访客卡都到对的图站啦！',
  cues:[
    {...feedback,steps:['pick-father-a','deliver-father-a']},
    {...feedback,steps:['pick-grandma-a','deliver-grandma-a','pick-friend-a','deliver-friend-a']},
    {...feedback,steps:['pick-mother-father','deliver-mother-father','pick-near-b','deliver-near-b','pick-far-b','deliver-far-b']},
  ],
  levels:[
    {
      pickup:[['father-a',5],['mother-a',7]],drop:[['near-a',1],['far-a',5]],
      orders:[['father-a','near-a']],
      lanes:[{row:2,speed:.75,spacing:5.7,phase:.5}],step:.38,hints,
    },
    {
      pickup:[['grandma-a',2],['grandpa-a',4],['friend-a',7]],drop:[['far-a',1],['near-a',7]],
      orders:[['grandma-a','far-a'],['friend-a','near-a']],
      lanes:[{row:1,speed:.92,spacing:5.5,phase:1},{row:3,speed:-1.12,spacing:5,phase:2}],
      step:.31,hints,
    },
    {
      pickup:[['grandpa-a',0],['father-a',3],['father-b',6],['mother-a',8]],
      drop:[['near-mother',1],['far-b',4],['near-b',7],['far-mother',5]],
      orders:[['grandpa-a','far-mother'],['father-b','near-b'],['father-b','far-b']],
      lanes:[
        {row:1,speed:1.12,spacing:5.2,phase:1},{row:2,speed:-1.38,spacing:5.1,phase:3},
        {row:3,speed:1.55,spacing:5,phase:2.5},
      ],
      step:.26,hints,
    },
  ],
}));

const setTeacherState = K.onState;
K.onState = (state, content) => {
  setTeacherState(state, content);
  if (state.pause === false || state.demo === false) {
    for (const anchor of K.$$('.teach-hl')) anchor.classList.remove('teach-hl');
  }
};
