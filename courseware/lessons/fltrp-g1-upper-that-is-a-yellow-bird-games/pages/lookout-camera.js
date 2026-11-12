K.ready({title:'泡泡车找鸟',sub:'听小导游说近还是远，再把泡泡车开到那只鸟旁。'});

const routeFeedback = {
  goal:'maze-exit', hint:'maze-hint', hint2:'maze-help', praise:'maze-praise',
};
const routeHints = ['重听一句。先从小导游站的地方看。','慢一点，亮的那一格就是下一站。'];

K.game(K.gameTemplates.bubbleMaze({
  voiceLead:true,
  stepVoiceLead:true,
  art:{
    backdrop:'__IMG:lookout-background__',
    sticker:'__IMG:yellow-bird__',
    frames:['__IMG:game-scout-rover__','__IMG:game-scout-rover-pop__'],
    icons:{
      A:'__IMG:yellow-bird__', B:'__IMG:yellow-bird__',
      C:'__IMG:black-bird__', D:'__IMG:black-bird__',
    },
  },
  doneText:'每只鸟都找到了，公园贴纸到手！',
  cues:[
    {...routeFeedback,steps:['near-yellow','far-yellow']},
    {...routeFeedback,steps:['far-black','near-black']},
    {...routeFeedback,steps:['near-black','far-yellow','near-yellow','far-black']},
  ],
  levels:[
    {
      map:['#########','#AS....B#','#.#.###.#','#.......#','#......E#','#########'],
      route:['A','B'],step:.36,listenOnly:true,hints:routeHints,
      labels:{A:'黄鸟',B:'黄鸟'},
    },
    {
      map:['#########','#C.S...D#','#.#.###.#','#.......#','#......E#','#########'],
      route:['D','C'],step:.29,listenOnly:true,hints:routeHints,
      patrols:[{y:3,from:2,to:6,speed:1.12}],labels:{C:'黑鸟',D:'黑鸟'},
    },
    {
      map:['#########','#A..S..B#','#.#.###.#','#C.....D#','#.......#','#...E...#','#########'],
      route:['C','B','A','D'],step:.23,listenOnly:true,hints:routeHints,
      patrols:[{y:4,from:2,to:6,speed:1.55}],labels:{A:'黄鸟',B:'黄鸟',C:'黑鸟',D:'黑鸟'},
    },
  ],
}));
