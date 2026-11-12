const groups={'glory-side':'trumpet','pink-trumpet':'trumpet','cress-top':'cross','yellow-cross':'cross',
  'golden-bell':'bell','pea-flower':'butterfly'};
const item=(x,y,token)=>({x,y,token,group:groups[token]});
const dock=(x,y,group)=>({x,y,group,sample:'shape-'+group});
const hints=['先停一下。看花的外边，和托盘里的轮廓比一比。','绕到卡片后面用车推，按回转键可以撤回。'];
const levels=[
  {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.3,
   items:[item(3,2,'glory-side'),item(2,3,'yellow-cross')],
   docks:[dock(5,1,'trumpet'),dock(5,2,'cross')]},
  {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.24,
   items:[item(4,2,'pink-trumpet'),item(4,4,'golden-bell'),item(3,3,'cress-top')],
   docks:[dock(6,2,'trumpet'),dock(7,4,'bell'),dock(6,3,'cross')]},
  {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.2,
   items:[item(4,3,'pea-flower'),item(7,4,'yellow-cross'),item(4,2,'golden-bell'),item(4,5,'glory-side')],
   docks:[dock(7,3,'butterfly'),dock(8,4,'cross'),dock(8,2,'bell'),dock(7,5,'trumpet')]},
];
const title='花形样本分类站';
K.ready({title,sub:'把花卡推到外形相像的托盘。'});
K.game(K.gameTemplates.sortingDepot({
  title,doneText:'每朵花都按外形找到了自己的托盘。',
  voiceLead:true,
  levels:levels.map(l=>({...l,hints})),
  cues:['flower-sort-a','flower-sort-b','flower-sort-c'].map(goal=>({
    goal,hint:'flower-sort-hint',hint2:'flower-sort-help',praise:'flower-sort-praise',
  })),
  art:{
    backdrop:'__IMG:sort-background__',sticker:'__IMG:peach-top__',
    frames:['__IMG:flower-cart-idle__','__IMG:flower-cart-move__'],
    icons:{
      'glory-side':'__IMG:glory-side__','pink-trumpet':'__IMG:pink-trumpet__','cress-top':'__IMG:cress-top__',
      'yellow-cross':'__IMG:yellow-cross__','golden-bell':'__IMG:golden-bell__','pea-flower':'__IMG:pea-flower__',
      'shape-trumpet':'__IMG:shape-trumpet__','shape-cross':'__IMG:shape-cross__',
      'shape-bell':'__IMG:shape-bell__','shape-butterfly':'__IMG:shape-butterfly__',
    },
  },
}));
