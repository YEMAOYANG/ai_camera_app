const config = {
  title: '把通知推到合适的托盘',
  sub: '看空了哪一格，从卡片后面把它推过去。',
  doneText: '每张通知都放到合适的托盘了。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:sort-backdrop__',
    sticker: '__IMG:meeting-sticker__',
    frames: ['__IMG:notice-cart__','__IMG:notice-cart-up__'],
    icons: {
      'missing-day':'__IMG:missing-day-card__','missing-time':'__IMG:missing-time-card__',
      'missing-place':'__IMG:missing-place-card__','complete':'__IMG:complete-card__',
      day:'__IMG:dock-date__',time:'__IMG:dock-time__',place:'__IMG:dock-place__',full:'__IMG:dock-full__'
    }
  },
  levels: [
    {
      map: ['########','#......#','#.S....#','#......#','########'],
      items: [{x:3,y:2,token:'missing-day',group:'day'},{x:3,y:3,token:'missing-time',group:'time'}],
      docks: [{x:5,y:2,sample:'day',group:'day'},{x:5,y:3,sample:'time',group:'time'}],
      step: .30, hints: ['日历和钟表，哪一格空着？','去发亮的托盘再试。']
    },
    {
      map: ['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      items: [{x:4,y:2,token:'missing-day',group:'day'},{x:4,y:4,token:'missing-place',group:'place'},
        {x:3,y:3,token:'complete',group:'full'}],
      docks: [{x:6,y:2,sample:'day',group:'day'},{x:6,y:3,sample:'full',group:'full'},{x:7,y:4,sample:'place',group:'place'}],
      step: .25, hints: ['日期、地点，还是三格都齐？','看发亮的托盘，绕到卡后面再推。']
    },
    {
      map: ['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      items: [{x:4,y:3,token:'missing-day',group:'day'},{x:7,y:4,token:'missing-place',group:'place'},
        {x:5,y:2,token:'missing-time',group:'time'},{x:4,y:5,token:'complete',group:'full'}],
      docks: [{x:8,y:4,sample:'place',group:'place'},{x:5,y:1,sample:'time',group:'time'},
        {x:8,y:2,sample:'day',group:'day'},{x:7,y:5,sample:'full',group:'full'}],
      step: .21, hints: ['看清空格，再选方向。','可以撤一步，再把卡推去亮着的位置。']
    }
  ],
  cues: ['sort-goal-one','sort-goal-two','sort-goal-three']
    .map(goal => ({goal,hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'}))
};

K.ready({title:config.title,sub:config.sub});
K.stage().append(K.$('#meeting-first-card'),K.$('#meeting-first-dock'));
const activity=K.gameTemplates.sortingDepot(config);
activity.onState=(_,state)=>{
  if(state.demo===false) K.$$('.teach-hl',K.stage()).forEach(anchor=>anchor.classList.remove('teach-hl'));
};
K.game(activity);
