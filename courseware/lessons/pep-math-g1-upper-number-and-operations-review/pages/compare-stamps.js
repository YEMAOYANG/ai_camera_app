const config = {
  title:'邮票小蛇比多少',
  sub:'先看右边的参照卡，再听是找更多、找更少，还是一样多。',
  doneText:'邮票小蛇找齐了。',
  voiceLead:true,
  stepVoiceLead:true,
  art:{
    sticker:'__IMG:post-sticker__',
    frames:['__IMG:snake-head__','__IMG:snake-body__','__IMG:snake-tail__'],
    icons:{
      3:'__IMG:count-3__',4:'__IMG:count-4__',5:'__IMG:count-5__',6:'__IMG:count-6__',
      8:'__IMG:count-8__',9:'__IMG:count-9__',11:'__IMG:count-11__',12:'__IMG:count-12__',
      13:'__IMG:count-13__',14:'__IMG:count-14__',15:'__IMG:count-15__',16:'__IMG:count-16__',18:'__IMG:count-18__'
    }
  },
  levels:[
    {
      start:4,seconds:.77,display:'stamps',walls:[],
      rounds:[
        {relation:'gt',foods:[[5,3,6],[7,4,3]]},
        {relation:'gt',foods:[[7,2,8],[3,3,5]]}
      ],
      hints:['再听是找更多还是更少。','看亮起来的一组，慢一点转过去。']
    },
    {
      start:16,seconds:.66,display:'stamps',walls:[[4,2],[6,3]],
      rounds:[
        {relation:'lt',foods:[[5,3,13],[7,4,18]]},
        {relation:'lt',foods:[[3,2,11],[7,2,15]]},
        {relation:'lt',foods:[[7,1,9],[2,4,14]]}
      ],
      hints:['有十的先看十，再看散点。','看亮起来的一组，再绕开木格。']
    },
    {
      start:12,seconds:.54,display:'stamps',walls:[[4,2],[6,3],[6,1]],
      rounds:[
        {relation:'eq',foods:[[5,3,12],[7,4,14]]},
        {relation:'gt',foods:[[3,2,15],[7,2,9]]},
        {relation:'lt',foods:[[7,1,14],[2,4,16]]},
        {relation:'eq',foods:[[5,1,14],[2,2,11]]}
      ],
      hints:['每吃一组，参照卡也会跟着换。','对照新卡和亮起来的点，再决定怎么转。']
    }
  ],
  cues:[
    {goal:'more',hint:'compare-hint',hint2:'compare-help',praise:'compare-praise',steps:['more','more']},
    {goal:'fewer',hint:'compare-hint',hint2:'compare-help',praise:'compare-praise',steps:['fewer','fewer','fewer']},
    {goal:'same',hint:'compare-hint',hint2:'compare-help',praise:'compare-praise',steps:['same','more','fewer','same']}
  ]
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#ops-snake-first-food'));
const activity = K.gameTemplates.compareSnake(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
