const layouts = [
  {map:['#########','#....E..#','#.......#','#...A...#','#SB.....#','#########'],
    route:['A','B'],step:.29},
  {map:['##########','#....D..E#','#..##.##.#','#..C.+...#','#.#...#..#','#S...B...#','##########'],
    route:['B','C','D'],step:.24},
  {map:['###########','#.....D..E#','#..##.##..#','#..B..C...#','#.#..+..#.#','#S...A....#','###########'],
    route:['A','B','C','D'],step:.19},
];
const cues = {A:'route-scrap',B:'route-pulp',C:'route-mesh',D:'route-dry'};
const hints = ['先看看已经到了哪一步，再听听下一步。','湿纸浆要先抄到网上，再等纸干。'];
const title = '旧纸走过纸工坊';
K.ready({title,sub:'看小图，按做纸的顺序到站。'});
const maze = K.game(K.gameTemplates.bubbleMaze({
  title,doneText:'从废纸碎片到晒干的新纸，工序走齐了。',voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:paper-workshop-maze__',sticker:'__IMG:paper-made-badge__',
    frames:['__IMG:paper-scout-idle__','__IMG:paper-scout-bubble__'],
    icons:{A:'__IMG:paper-scraps__',B:'__IMG:paper-pulp__',C:'__IMG:paper-on-mesh__',D:'__IMG:paper-dry__'},
  },
  levels:layouts.map(l=>({...l,hints})),
  cues:layouts.map(l=>({
    goal:cues[l.route[0]],steps:[...l.route.map(step=>cues[step]),'route-exit'],
    hint:'route-hint',hint2:'route-help',praise:'route-praise',
  })),
}));
maze.follow('#paper-next-preview', () => ({x:605,y:18,w:70,h:58}));
