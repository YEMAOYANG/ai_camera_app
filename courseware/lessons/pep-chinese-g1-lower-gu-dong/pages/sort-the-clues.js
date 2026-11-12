const config = {
  title: '推车给线索找位置',
  sub: '看画中怎么知道，再把画推到合适的托盘。',
  doneText: '从哪里知道的，几张线索都分清了。',
  voiceLead: true,
  art: {
    backdrop:'__IMG:clue-backdrop__',
    sticker:'__IMG:gudong-sticker__',
    frames:['__IMG:clue-cart__','__IMG:clue-cart-move__'],
    icons:{
      rabbit:'__IMG:clue-rabbit__', monkey:'__IMG:clue-monkey__',
      elephant:'__IMG:clue-elephant__', group:'__IMG:clue-group__',
      heard:'__IMG:dock-direct-hearing__', told:'__IMG:dock-told__', seen:'__IMG:dock-saw-source__'
    }
  },
  levels: [
    {
      map:['########','#......#','#.S....#','#......#','########'],
      items:[{x:3,y:2,token:'rabbit',group:'heard'},{x:3,y:3,token:'monkey',group:'told'}],
      docks:[{x:5,y:2,sample:'heard',group:'heard'},{x:5,y:3,sample:'told',group:'told'}],
      step:.31
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      items:[{x:4,y:2,token:'rabbit',group:'heard'},{x:3,y:3,token:'monkey',group:'told'},
        {x:4,y:4,token:'group',group:'seen'}],
      docks:[{x:6,y:2,sample:'heard',group:'heard'},{x:6,y:3,sample:'told',group:'told'},
        {x:7,y:4,sample:'seen',group:'seen'}],
      step:.26
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      items:[{x:4,y:3,token:'rabbit',group:'heard'},{x:5,y:2,token:'monkey',group:'told'},
        {x:7,y:4,token:'elephant',group:'told'},{x:4,y:5,token:'group',group:'seen'}],
      docks:[{x:8,y:2,sample:'heard',group:'heard'},{x:5,y:1,sample:'told',group:'told'},
        {x:8,y:4,sample:'told',group:'told'},{x:7,y:5,sample:'seen',group:'seen'}],
      step:.22
    }
  ].map(level=>({...level,hints:['想想画里的线索从哪里来。','先撤一步，再往发亮的托盘推。']})),
  cues:['clue-one','clue-two','clue-three'].map(goal=>({goal,hint:'clue-hint',hint2:'clue-help',praise:'clue-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#gudong-clue-card'),K.$('#gudong-clue-dock'));
const activity=K.gameTemplates.sortingDepot(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
