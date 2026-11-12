K.ready({title:'采访邮车送年龄牌',sub:'听年龄去取牌。等路空了，再把牌送到对应同学。'});

const deliveryFeedback = {hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise'};
const hints = ['先重听。看看现在要拿牌，还是去找收件人。','等一等，亮起的格子是这一站。'];

K.game(K.gameTemplates.listenDelivery({
  art:{
    backdrop:'__IMG:delivery-workshop__',sticker:'__IMG:reporter-sticker__',
    frames:['__IMG:reporter-van__','__IMG:reporter-van-loaded__','__IMG:traffic-van__'],
    icons:{
      three:'__IMG:badge-three__',six:'__IMG:badge-six__',seven:'__IMG:badge-seven__',
      nine:'__IMG:badge-nine__',ten:'__IMG:badge-ten__',
      cap:'__IMG:guest-cap__',phones:'__IMG:guest-phones__',scarf:'__IMG:guest-scarf__',
      headband:'__IMG:guest-headband__',bowtie:'__IMG:guest-bowtie__',glasses:'__IMG:guest-glasses__',
    },
  },
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'年龄牌都送到对应同学手里啦！',
  cues:[
    {...deliveryFeedback,steps:['age-six','to-cap']},
    {...deliveryFeedback,steps:['age-nine','to-phones','age-seven','to-scarf']},
    {...deliveryFeedback,steps:['age-ten','to-headband','age-three','to-bowtie','age-six','to-glasses']},
  ],
  levels:[
    {
      pickup:[['six',5],['nine',7]],drop:[['cap',5],['phones',2]],orders:[['six','cap']],
      lanes:[{row:2,speed:.75,spacing:5.7,phase:.5}],step:.38,hints,
    },
    {
      pickup:[['nine',2],['six',4],['seven',7]],drop:[['phones',1],['scarf',4],['cap',7]],
      orders:[['nine','phones'],['seven','scarf']],
      lanes:[{row:1,speed:.92,spacing:5.5,phase:1},{row:3,speed:-1.12,spacing:5,phase:2}],
      step:.31,hints,
    },
    {
      pickup:[['three',0],['six',3],['nine',6],['ten',8]],
      drop:[['headband',1],['bowtie',4],['glasses',7],['scarf',5]],
      orders:[['ten','headband'],['three','bowtie'],['six','glasses']],
      lanes:[
        {row:1,speed:1.12,spacing:5.2,phase:1},{row:2,speed:-1.38,spacing:5.1,phase:3},
        {row:3,speed:1.55,spacing:5,phase:2.5},
      ],
      step:.26,hints,
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
