const item = (x,y,kind,a,b) => ({x,y,token:'sort-'+kind+'-'+a+'-'+b,group:kind});
const dock = (x,y,kind) => ({x,y,sample:'dock-'+kind,group:kind});
const hints = ['先看问号在哪儿，问的是整组还是一部分？','先想好托盘，再绕到牌后面。'];
const levels = [
  {map:['########','#......#','#.S....#','#......#','########'],step:.30,
   items:[item(3,2,'add',5,3),item(3,3,'sub',8,3)],
   docks:[dock(5,2,'add'),dock(5,3,'sub')]},
  {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.23,
   items:[item(4,2,'add',7,2),item(4,4,'add',4,6),item(3,3,'sub',10,4)],
   docks:[dock(6,2,'add'),dock(7,4,'add'),dock(6,3,'sub')]},
  {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.19,
   items:[item(4,3,'sub',12,3),item(7,4,'add',8,3),item(4,2,'sub',11,5),item(4,5,'add',6,4)],
   docks:[dock(7,3,'sub'),dock(8,4,'add'),dock(8,2,'sub'),dock(7,5,'add')]},
];
const title='灯工坊分题牌';
K.ready({title,sub:'看问号在哪儿，把题牌推去相合的托盘。'});
K.game(K.gameTemplates.sortingDepot({
  title,voiceLead:true,doneText:'问整体的和问一部分的，都放对了。',
  art:{
    backdrop:'__IMG:sort-backdrop__',sticker:'__IMG:lantern-sticker__',
    frames:['__IMG:lantern-cart__','__IMG:lantern-cart-move__'],
    icons:{
      'sort-add-5-3':'__IMG:sort-add-5-3__','sort-sub-8-3':'__IMG:sort-sub-8-3__',
      'sort-add-7-2':'__IMG:sort-add-7-2__','sort-add-4-6':'__IMG:sort-add-4-6__','sort-sub-10-4':'__IMG:sort-sub-10-4__',
      'sort-sub-12-3':'__IMG:sort-sub-12-3__','sort-add-8-3':'__IMG:sort-add-8-3__',
      'sort-sub-11-5':'__IMG:sort-sub-11-5__','sort-add-6-4':'__IMG:sort-add-6-4__',
      'dock-add':'__IMG:dock-add__','dock-sub':'__IMG:dock-sub__',
    },
  },
  levels:levels.map(level=>({...level,hints})),
  cues:levels.map(()=>({goal:'lantern-sort-goal',hint:'lantern-sort-hint',hint2:'lantern-sort-help',praise:'lantern-sort-praise'})),
}));
