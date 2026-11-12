K.ready({title:'生日话语小车',sub:'听一句，走一站。说完再开到小旗边。'});

const feedback = {hint:'maze-hint',hint2:'maze-help',praise:'maze-praise'};
const cues = {A:'maze-bless',B:'maze-give',C:'maze-thanks',D:'maze-welcome'};
const hints = ['先重听。想一想谁在做什么。','亮起来的图就是下一站。'];
const levels = [
  {
    map:['#########','#S.A...E#','#.#.###.#','#....B..#','#########'],
    route:['A','B'],step:.4,listenOnly:true,hints,
  },
  {
    map:['###########','#S..B....E#','#.#.###.#.#','#..C...D..#','#.........#','###########'],
    route:['B','C','D'],step:.34,listenOnly:true,hints,
  },
  {
    map:['#############','#S..A+.....E#','#.##.#####.##','#..B..C..D..#','###.##.##.#.#','#...........#','#############'],
    route:['A','B','C','D'],step:.29,listenOnly:true,hints,
  },
];

K.game(K.gameTemplates.bubbleMaze({
  art:{
    backdrop:'__IMG:maze-backdrop__',sticker:'__IMG:birthday-sticker__',
    frames:['__IMG:maze-rover__','__IMG:maze-bubble__'],
    icons:{A:'__IMG:role-wish__',B:'__IMG:role-give__',C:'__IMG:role-thanks__',D:'__IMG:role-welcome__'},
  },
  voiceLead:true,stepVoiceLead:true,
  doneText:'祝福、礼物、谢谢，都送到啦！',
  cues:levels.map(({route})=>({...feedback,goal:cues[route[0]],steps:[...route.map(id=>cues[id]),'maze-exit']})),
  levels,
}));
