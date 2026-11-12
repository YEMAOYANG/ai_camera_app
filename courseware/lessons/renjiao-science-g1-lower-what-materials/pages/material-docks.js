const groups = {
  'wood-tray':'wood','plastic-tray':'plastic','wood-box':'wood','wood-frame':'wood',
  'cloth-pouch':'cloth','paper-card':'paper','glass-dish':'glass','metal-bell':'metal','stone-tile':'stone',
};
const item = (x,y,token) => ({x,y,token,group:groups[token]});
const dock = (x,y,group) => ({x,y,group,sample:'swatch-'+group});
const levels = [
  {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.3,
    items:[item(3,2,'wood-tray'),item(2,3,'plastic-tray')],
    docks:[dock(5,1,'wood'),dock(5,2,'plastic')]},
  {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.24,
    items:[item(4,2,'wood-box'),item(4,4,'cloth-pouch'),item(3,3,'wood-frame')],
    docks:[dock(6,2,'wood'),dock(7,4,'cloth'),dock(6,3,'wood')]},
  {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.2,
    items:[item(4,3,'paper-card'),item(7,4,'glass-dish'),item(4,2,'metal-bell'),item(4,5,'stone-tile')],
    docks:[dock(7,3,'paper'),dock(8,4,'glass'),dock(8,2,'metal'),dock(7,5,'stone')]},
];
const hints = ['看物品边上，找和材料片相像的地方。','绕到物品后面推，按回转键可以撤回。'];
const title = '给材料找托盘';
const sub = '把展台物品推到相同材料的托盘。';
K.ready({title,sub});
K.game(K.gameTemplates.sortingDepot({
  title,sub,doneText:'展台物品已经按用到的材料摆好了。',voiceLead:true,
  levels:levels.map(level=>({...level,hints})),
  cues:['docks-start','docks-wood','docks-mix'].map(goal=>({
    goal,hint:'docks-hint',hint2:'docks-help',praise:'docks-praise',
  })),
  art:{
    backdrop:'__IMG:sorting-workbench__',sticker:'__IMG:materials-badge__',
    frames:['__IMG:material-cart-idle__','__IMG:material-cart-move__'],
    icons:{
      'wood-tray':'__IMG:wood-tray__','plastic-tray':'__IMG:plastic-tray__',
      'wood-box':'__IMG:wood-box__','wood-frame':'__IMG:wood-frame__','cloth-pouch':'__IMG:cloth-pouch__',
      'paper-card':'__IMG:paper-card__','glass-dish':'__IMG:glass-dish__',
      'metal-bell':'__IMG:metal-bell__','stone-tile':'__IMG:stone-tile__',
      'swatch-wood':'__IMG:swatch-wood__','swatch-plastic':'__IMG:swatch-plastic__',
      'swatch-cloth':'__IMG:swatch-cloth__','swatch-paper':'__IMG:swatch-paper__',
      'swatch-glass':'__IMG:swatch-glass__','swatch-metal':'__IMG:swatch-metal__',
      'swatch-stone':'__IMG:swatch-stone__',
    },
  },
}));
