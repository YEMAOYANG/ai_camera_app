K.ready({title: '把竖式送到合适的托盘', sub: '先看加减符号，再看个位是否要换十。'});

const rules = ['__IMG:sort-add__', '__IMG:sort-sub__', '__IMG:sort-mix__'];
const ruleCard = K.$('#written-rule-card');
const sortGame = K.game(K.gameTemplates.sortingDepot({
  voiceLead: true,
  doneText: '四类笔算记录都送到了对应的托盘。',
  art: {
    backdrop: '__IMG:sort-backdrop__',
    frames: ['__IMG:trolley__'],
    sticker: '__IMG:leaf-badge__',
    icons: {
      'add-keep': '__IMG:dock-add-keep__', 'add-carry': '__IMG:dock-add-carry__',
      'sub-keep': '__IMG:dock-sub-keep__', 'sub-borrow': '__IMG:dock-sub-borrow__',
      's-36-22': '__IMG:s-36-22__', 's-39-24': '__IMG:s-39-24__',
      's-68-35': '__IMG:s-68-35__', 's-61-23': '__IMG:s-61-23__', 's-85-44': '__IMG:s-85-44__',
      's-52-31': '__IMG:s-52-31__', 's-48-27': '__IMG:s-48-27__',
      's-77-42': '__IMG:s-77-42__', 's-63-29': '__IMG:s-63-29__'
    }
  },
  cues: [
    {goal: 'sort-add-goal', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'},
    {goal: 'sort-sub-goal', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'},
    {goal: 'sort-mixed-goal', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'}
  ],
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      step: .31,
      items: [{x: 3, y: 2, token: 's-36-22', group: 'add-keep'},
              {x: 3, y: 3, token: 's-39-24', group: 'add-carry'}],
      docks: [{x: 5, y: 2, sample: 'add-keep', group: 'add-keep'},
              {x: 5, y: 3, sample: 'add-carry', group: 'add-carry'}],
      hints: ['先看看右边两个数字。', '个位满十才把散棒合成一盒。']
    },
    {
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      step: .26,
      items: [{x: 4, y: 2, token: 's-68-35', group: 'sub-keep'},
              {x: 3, y: 3, token: 's-61-23', group: 'sub-borrow'},
              {x: 4, y: 4, token: 's-85-44', group: 'sub-keep'}],
      docks: [{x: 6, y: 2, sample: 'sub-keep', group: 'sub-keep'},
              {x: 6, y: 3, sample: 'sub-borrow', group: 'sub-borrow'},
              {x: 7, y: 4, sample: 'sub-keep', group: 'sub-keep'}],
      hints: ['比较个位两个数。', '个位不够拿时，先拆一盒。']
    },
    {
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      step: .22,
      items: [{x: 4, y: 3, token: 's-52-31', group: 'add-keep'},
              {x: 7, y: 4, token: 's-48-27', group: 'add-carry'},
              {x: 4, y: 2, token: 's-77-42', group: 'sub-keep'},
              {x: 4, y: 5, token: 's-63-29', group: 'sub-borrow'}],
      docks: [{x: 7, y: 3, sample: 'add-keep', group: 'add-keep'},
              {x: 8, y: 4, sample: 'add-carry', group: 'add-carry'},
              {x: 8, y: 2, sample: 'sub-keep', group: 'sub-keep'},
              {x: 7, y: 5, sample: 'sub-borrow', group: 'sub-borrow'}],
      hints: ['先看符号，再看个位。', '没有换十的两类，还要看是加还是减。']
    }
  ]
}));
sortGame.follow(ruleCard, game => {
  const image = rules[game.level];
  if (ruleCard.getAttribute('src') !== image) ruleCard.setAttribute('src', image);
  return {x: 12, y: 146, w: 207, h: game.level === 2 ? 155 : 100};
});
sortGame.follow('#first-written-dock', game => game.level === 0 ? {x: 736, y: 297, w: 90, h: 90} : null);
