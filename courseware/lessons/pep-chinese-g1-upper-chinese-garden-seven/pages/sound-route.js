const labels = {A:'★', B:'★', C:'★', D:'★'};
const config = {
  title: '听方位找录音点',
  sub: '看纸偶的朝向，听老师说要去纸偶哪一边。',
  doneText: '小电台的录音点都找齐啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    sticker: '__IMG:star-pin__',
    frames: ['__IMG:rover__', '__IMG:rover-boost__'],
    icons: {A:'__IMG:star-pin__', B:'__IMG:star-pin__', C:'__IMG:star-pin__', D:'__IMG:star-pin__'}
  },
  levels: [
    {
      labels,
      facing: 'east', listenOnly:true, step:0.34, route:['C','A'],
      map:['#########','#...A...#','#.......#','#...#..C#','#.......#','#S.....E#','#########'],
      hints:['先看纸偶朝向哪儿，再重听。','看亮起来的那颗星，开过去试试。']
    },
    {
      labels,
      facing: 'east', listenOnly:true, step:0.27, route:['C','B','D'],
      map:['#########','#.......#','#..##...#','#B..#..C#','#...+...#','#S..D..E#','#########'],
      hints:['停一下，想想纸偶的前后左右。','试着绕过墙，去发亮的地方。']
    },
    {
      labels,
      facing: 'north', listenOnly:true, step:0.22, route:['D','C','A','B'],
      map:['#########','#...A...#','#....+..#','#B..#..C#','#....+..#','#S..D..E#','#########'],
      patrols:[{y:4,from:1,to:3,speed:1.0}],
      hints:['纸偶转身了，先找它现在面对哪里。','再看亮星和巡游路线，慢慢开。']
    }
  ],
  cues: [
    {goal:'go-front', hint:'route-hint', hint2:'route-hint', praise:'route-praise',
      steps:['go-front','go-left','go-exit']},
    {goal:'go-front', hint:'route-hint', hint2:'route-hint', praise:'route-praise',
      steps:['go-front','go-back','go-right','go-exit']},
    {goal:'go-back', hint:'route-hint', hint2:'route-hint', praise:'route-praise',
      steps:['go-back','go-right','go-front','go-left','go-exit']}
  ]
};

K.ready({title:config.title, sub:config.sub});
const facing = K.$('#garden-facing');
K.stage().append(facing, K.$('#garden-compass'));
const activity = K.gameTemplates.bubbleMaze(config);
const reset = activity.reset;
activity.reset = (game, level) => {
  reset(game, level);
  facing.querySelector('img').style.transform = config.levels[level].facing === 'east' ? 'rotate(90deg)' : '';
};
K.game(activity);
