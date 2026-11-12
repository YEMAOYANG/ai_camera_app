const groups = {
  'result-polished':'polish', 'result-tap':'tap', 'result-bent-up':'bend',
  'result-bent-down':'bend', 'result-flat-tip':'hammer', 'result-polish-pair':'polish',
};
const item = (x,y,token) => ({x,y,token,group:groups[token]});
const dock = (x,y,group) => ({x,y,group,sample:'station-'+group});
const levels = [
  {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.3,
    items:[item(3,2,'result-polished'),item(2,3,'result-tap')],
    docks:[dock(5,1,'polish'),dock(5,2,'tap')]},
  {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.24,
    items:[item(4,2,'result-bent-up'),item(4,4,'result-flat-tip'),item(3,3,'result-bent-down')],
    docks:[dock(6,2,'bend'),dock(7,4,'hammer'),dock(6,3,'bend')]},
  {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.2,
    items:[item(4,3,'result-polish-pair'),item(7,4,'result-tap'),item(4,2,'result-flat-tip'),item(4,5,'result-bent-up')],
    docks:[dock(7,3,'polish'),dock(8,4,'tap'),dock(8,2,'hammer'),dock(7,5,'bend')]},
];
const hints = ['这张卡留下了什么？再看看工位上的工具。','比一比是看到形变，还是听到声音。'];
const title = '观察记录送回工位';
const sub = '开小车，把结果送回做这个观察的工位。';
K.ready({title,sub});
K.game(K.gameTemplates.sortingDepot({
  title,sub,doneText:'四种观察的结果都送回了对应工位。',voiceLead:true,
  levels:levels.map(level=>({...level,hints})),
  cues:['station-first','station-shape','station-all'].map(goal=>({
    goal,hint:'station-hint',hint2:'station-help',praise:'station-praise',
  })),
  art:{
    backdrop:'__IMG:metal-sort-workbench__',sticker:'__IMG:metal-evidence-badge__',
    frames:['__IMG:metal-trolley-idle__','__IMG:metal-trolley-roll__'],
    icons:{
      'result-polished':'__IMG:result-polished__','result-tap':'__IMG:result-suspended-sound__',
      'result-bent-up':'__IMG:result-bent-up__','result-bent-down':'__IMG:result-bent-down__',
      'result-flat-tip':'__IMG:result-flat-tip__','result-polish-pair':'__IMG:result-dull-to-bright__',
      'station-polish':'__IMG:station-polish__','station-tap':'__IMG:station-tap__',
      'station-bend':'__IMG:station-bend__','station-hammer':'__IMG:station-hammer__',
    },
  },
}));
