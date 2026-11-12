const config = {
  title: '把尾巴纸偶推去合适的布景',
  sub: '看尾巴的动作，从纸偶后面把它推过去。',
  doneText: '尾巴纸偶都到了合适的布景。',
  voiceLead: true,
  art: {
    backdrop:'__IMG:tail-sort-backdrop__',
    sticker:'__IMG:gecko-sticker__',
    frames:['__IMG:tail-cart__','__IMG:tail-cart-move__'],
    icons:{
      fish:'__IMG:tail-fish__',cow:'__IMG:tail-cow__',swallow:'__IMG:tail-swallow__',gecko:'__IMG:tail-gecko__',
      water:'__IMG:dock-water__',flies:'__IMG:dock-flies__',turn:'__IMG:dock-turn__',home:'__IMG:dock-home__'
    }
  },
  levels: [
    {
      map:['########','#......#','#.S....#','#......#','########'],
      items:[{x:3,y:2,token:'fish',group:'water'},{x:3,y:3,token:'cow',group:'flies'}],
      docks:[{x:5,y:2,sample:'water',group:'water'},{x:5,y:3,sample:'flies',group:'flies'}],
      step:.31
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      items:[{x:4,y:2,token:'fish',group:'water'},{x:3,y:3,token:'cow',group:'flies'},
        {x:4,y:4,token:'swallow',group:'turn'}],
      docks:[{x:6,y:2,sample:'water',group:'water'},{x:6,y:3,sample:'flies',group:'flies'},
        {x:7,y:4,sample:'turn',group:'turn'}],
      step:.26
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      items:[{x:4,y:3,token:'fish',group:'water'},{x:5,y:2,token:'cow',group:'flies'},
        {x:7,y:4,token:'swallow',group:'turn'},{x:4,y:5,token:'gecko',group:'home'}],
      docks:[{x:8,y:2,sample:'water',group:'water'},{x:5,y:1,sample:'flies',group:'flies'},
        {x:8,y:4,sample:'turn',group:'turn'},{x:7,y:5,sample:'home',group:'home'}],
      step:.22
    }
  ].map(level=>({...level,hints:['先想尾巴正在做什么。','退一步，再往亮起来的布景推。']})),
  cues:['tail-first','tail-next','tail-last'].map(goal=>({goal,hint:'tail-hint',hint2:'tail-help',praise:'tail-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#gecko-first-card'),K.$('#gecko-first-dock'));
const activity=K.gameTemplates.sortingDepot(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
