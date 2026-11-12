const groups={
  'ginkgo-top':'fan','gold-ginkgo':'fan','maize-top':'long','straw-maize':'long',
  'lotus-blade':'round','pale-camphor':'broad',
};
const item=(x,y,token)=>({x,y,token,group:groups[token]});
const dock=(x,y,group)=>({x,y,group,sample:'dock-'+group});
const hints=['先停一下。看看叶子的外边跟托盘里的样子像不像。','车只能推，绕到叶卡背后，也可以撤回一步。'];
const levels=[
  {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.3,
   items:[item(3,2,'ginkgo-top'),item(2,3,'straw-maize')],
   docks:[dock(5,1,'fan'),dock(5,2,'long')]},
  {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.24,
   items:[item(4,2,'gold-ginkgo'),item(4,4,'lotus-blade'),item(3,3,'maize-top')],
   docks:[dock(6,2,'fan'),dock(7,4,'round'),dock(6,3,'long')]},
  {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.2,
   items:[item(4,3,'pale-camphor'),item(7,4,'straw-maize'),item(4,2,'lotus-blade'),item(4,5,'ginkgo-top')],
   docks:[dock(7,3,'broad'),dock(8,4,'long'),dock(8,2,'round'),dock(7,5,'fan')]},
];
const title='按叶的外形送进托盘';
K.ready({title,sub:'绕到卡片后面，把它推到轮廓相像的托盘。'});
K.game(K.gameTemplates.sortingDepot({
  title,doneText:'用外形比较，每片叶都回到相像的托盘。',
  voiceLead:true,
  levels:levels.map(l=>({...l,hints})),
  cues:['shape-goal','shape-goal-b','shape-goal-c'].map(goal=>({
    goal,hint:'shape-hint',hint2:'shape-help',praise:'shape-praise',
  })),
  art:{
    backdrop:'__IMG:sort-backdrop__',sticker:'__IMG:gold-ginkgo__',
    frames:['__IMG:caddy-still__','__IMG:caddy-moving__'],
    icons:{
      'ginkgo-top':'__IMG:ginkgo-top__','gold-ginkgo':'__IMG:gold-ginkgo__','maize-top':'__IMG:maize-top__',
      'straw-maize':'__IMG:straw-maize__','lotus-blade':'__IMG:lotus-blade__','pale-camphor':'__IMG:pale-camphor__',
      'dock-fan':'__IMG:dock-fan__','dock-long':'__IMG:dock-long__','dock-round':'__IMG:dock-round__','dock-broad':'__IMG:dock-broad__',
    },
  },
}));
