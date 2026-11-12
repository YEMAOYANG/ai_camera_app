const config = {
  title: '帮纸偶找到故事里的位置',
  sub: '听角色，找布景，从纸偶牌后面推过去。',
  doneText: '故事纸偶都到了合适的布景。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:sort-backdrop__',
    sticker: '__IMG:cotton-sticker__',
    frames: ['__IMG:cotton-cart__', '__IMG:cotton-cart-move__'],
    icons: {
      swallow: '__IMG:puppet-swallow__', woodpecker: '__IMG:puppet-woodpecker__',
      frog: '__IMG:puppet-frog__', ladybug: '__IMG:puppet-ladybug__',
      sky: '__IMG:dock-sky__', trunk: '__IMG:dock-trunk__',
      paddy: '__IMG:dock-paddy__', leaf: '__IMG:dock-leaf__'
    }
  },
  levels: [
    {
      map: ['########','#......#','#.S....#','#......#','########'],
      items: [{x:3,y:2,token:'swallow',group:'sky'},{x:3,y:3,token:'woodpecker',group:'trunk'}],
      docks: [{x:5,y:2,sample:'sky',group:'sky'},{x:5,y:3,sample:'trunk',group:'trunk'}],
      step: .30
    },
    {
      map: ['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      items: [{x:4,y:2,token:'swallow',group:'sky'},{x:4,y:4,token:'frog',group:'paddy'},
        {x:3,y:3,token:'woodpecker',group:'trunk'}],
      docks: [{x:6,y:2,sample:'sky',group:'sky'},{x:6,y:3,sample:'trunk',group:'trunk'},
        {x:7,y:4,sample:'paddy',group:'paddy'}],
      step: .25
    },
    {
      map: ['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      items: [{x:4,y:3,token:'swallow',group:'sky'},{x:7,y:4,token:'frog',group:'paddy'},
        {x:5,y:2,token:'woodpecker',group:'trunk'},{x:4,y:5,token:'ladybug',group:'leaf'}],
      docks: [{x:8,y:4,sample:'paddy',group:'paddy'},{x:5,y:1,sample:'trunk',group:'trunk'},
        {x:8,y:2,sample:'sky',group:'sky'},{x:7,y:5,sample:'leaf',group:'leaf'}],
      step: .21
    }
  ].map(level => ({
    ...level, hints: ['先想想它在故事里去哪里。', '绕到纸偶牌后面，再往亮起的位置推。']
  })),
  cues: ['stage-sort-first','stage-sort-next','stage-sort-last'].map(goal => ({
    goal, hint:'stage-sort-hint', hint2:'stage-sort-help', praise:'stage-sort-praise'
  }))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#cotton-first-card'),K.$('#cotton-first-dock'));
const activity=K.gameTemplates.sortingDepot(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
