const config = {
  title:'落块配成十',
  sub:'移动上面的方块，和下面的一组挨在一起，正好凑成十。',
  doneText:'凑成十的邮票盘都装好啦。',
  voiceLead:true,
  stepVoiceLead:true,
  art:{
    sticker:'__IMG:post-sticker__',
    icons:{
      1:'__IMG:count-1__',2:'__IMG:count-2__',3:'__IMG:count-3__',4:'__IMG:count-4__',
      5:'__IMG:count-5__',6:'__IMG:count-6__',7:'__IMG:count-7__',8:'__IMG:count-8__',
      9:'__IMG:count-9__',10:'__IMG:count-10__'
    }
  },
  levels:[
    {total:10,bottom:[null,7,null,9,null,null],pieces:[3,1],interval:1.22,
      hints:['要在同一行挨在一起。','慢一点落，看底下一组还差几个。']},
    {total:10,bottom:[1,null,4,null,8,null],pieces:[2,9,6],interval:.88,
      hints:['先数一数这块有几个。','数好缺几个，再让方块落到旁边。']},
    {total:10,bottom:[null,2,null,5,null,6],pieces:[8,5,4],interval:.62,
      hints:['留心浅浅的影子，那是落点。','再等一等，对准同一行的空格。']}
  ],
  cues:[
    {goal:'ten-goal',hint:'ten-hint',hint2:'ten-help',praise:'ten-praise',steps:['ten-goal','ten-goal']},
    {goal:'ten-goal',hint:'ten-hint',hint2:'ten-help',praise:'ten-praise',steps:['ten-goal','ten-goal','ten-goal']},
    {goal:'ten-goal',hint:'ten-hint',hint2:'ten-help',praise:'ten-praise',steps:['ten-goal','ten-goal','ten-goal']}
  ]
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#ops-first-partner'),K.$('#ops-ten-target'));
const activity = K.gameTemplates.fallingTiles(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
