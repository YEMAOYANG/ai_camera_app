const config = {
  title: '徽章小车分仓',
  sub: '两行散枚能装满一条吗？推到相应的托盘。',
  doneText: '散枚卡都送到对应的仓位。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:workshop-floor__',
    frames: ['__IMG:pushcart-rest__', '__IMG:pushcart-roll__'],
    sticker: '__IMG:badge-sticker__',
    icons: {
      'sort-3-4': '__IMG:sort-3-4__', 'sort-6-4': '__IMG:sort-6-4__',
      'sort-8-5': '__IMG:sort-8-5__', 'sort-4-5': '__IMG:sort-4-5__',
      'sort-7-2': '__IMG:sort-7-2__', 'sort-8-6': '__IMG:sort-8-6__',
      'sort-6-2': '__IMG:sort-6-2__',
      'dock-under': '__IMG:dock-under__', 'dock-full': '__IMG:dock-full__'
    }
  },
  levels: [
    {
      map: ['#######', '#S....#', '#.....#', '#.....#', '#######'], step: .39,
      items: [
        {x:3,y:2,token:'sort-3-4',group:'under'},
        {x:4,y:3,token:'sort-6-4',group:'full'}
      ],
      docks: [
        {x:4,y:2,sample:'dock-under',group:'under'},
        {x:3,y:3,sample:'dock-full',group:'full'}
      ],
      hints: ['先把两行的散枚合起来数。', '再看十格，够不够填满。']
    },
    {
      map: ['#######', '#....S#', '#.....#', '#.....#', '#######'], step: .33,
      items: [
        {x:3,y:2,token:'sort-8-5',group:'full'},
        {x:4,y:3,token:'sort-4-5',group:'under'}
      ],
      docks: [
        {x:2,y:2,sample:'dock-full',group:'full'},
        {x:2,y:3,sample:'dock-under',group:'under'}
      ],
      hints: ['多出来的散枚也一起数。', '够装一条时，剩下的仍是散枚。']
    },
    {
      map: ['#######', '#.....#', '#.....#', '#.S...#', '#######'], step: .27,
      items: [
        {x:3,y:1,token:'sort-7-2',group:'under'},
        {x:3,y:2,token:'sort-8-6',group:'full'},
        {x:4,y:3,token:'sort-6-2',group:'under'}
      ],
      docks: [
        {x:1,y:1,sample:'dock-under',group:'under'},
        {x:5,y:2,sample:'dock-full',group:'full'},
        {x:5,y:3,sample:'dock-under',group:'under'}
      ],
      hints: ['先找这一张卡上的两组。', '别记仓位，按这一张的数量重新选。']
    }
  ],
  cues: [
    {goal:'sort-goal',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'},
    {goal:'sort-goal-two',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'},
    {goal:'sort-goal-three',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'}
  ]
};

K.ready({title:config.title,sub:config.sub,img:'__IMG:workshop-cover__'});
K.stage().append(K.$('#sort-first-dock'));
const activity = K.gameTemplates.sortingDepot(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
