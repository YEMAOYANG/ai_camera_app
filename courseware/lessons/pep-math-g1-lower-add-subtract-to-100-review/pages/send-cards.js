K.ready({title: '给口算卡找托盘', sub: '听本关规则，用方向键推卡。'});

const rules = ['__IMG:sort-rule-ops__', '__IMG:sort-rule-carry__', '__IMG:sort-rule-borrow__'];
const rulePicture = K.$('#sort-rule-picture');
const depot = K.game(K.gameTemplates.sortingDepot({
  voiceLead: true,
  doneText: '每张口算卡都进了合适的托盘。',
  art: {
    backdrop: '__IMG:sort-backdrop__',
    frames: ['__IMG:trolley__'],
    sticker: '__IMG:microphone__',
    icons: {
      plus: '__IMG:dock-plus__', minus: '__IMG:dock-minus__',
      carry: '__IMG:dock-carry__', 'keep-add': '__IMG:dock-keep-add__',
      borrow: '__IMG:dock-borrow__', 'keep-sub': '__IMG:dock-keep-sub__',
      'add-26-3': '__IMG:add-26-3__', 'sub-57-3': '__IMG:sub-57-3__',
      'add-29-6': '__IMG:add-29-6__', 'add-43-4': '__IMG:add-43-4__', 'add-56-7': '__IMG:add-56-7__',
      'sub-42-5': '__IMG:sub-42-5__', 'sub-65-4': '__IMG:sub-65-4__',
      'sub-71-6': '__IMG:sub-71-6__', 'sub-49-8': '__IMG:sub-49-8__'
    }
  },
  cues: [
    {goal: 'sort-operation', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'},
    {goal: 'sort-carry', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'},
    {goal: 'sort-borrow', hint: 'sort-hint', hint2: 'sort-help', praise: 'sort-praise'}
  ],
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      step: .31,
      items: [
        {x: 3, y: 2, token: 'add-26-3', group: 'plus'},
        {x: 3, y: 3, token: 'sub-57-3', group: 'minus'}
      ],
      docks: [
        {x: 5, y: 2, sample: 'plus', group: 'plus'},
        {x: 5, y: 3, sample: 'minus', group: 'minus'}
      ],
      hints: ['找一找卡片中间的符号。', '有加号和减号两个托盘，先看这张卡。']
    },
    {
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      step: .26,
      items: [
        {x: 4, y: 2, token: 'add-43-4', group: 'keep-add'},
        {x: 4, y: 4, token: 'add-29-6', group: 'carry'},
        {x: 3, y: 3, token: 'add-56-7', group: 'carry'}
      ],
      docks: [
        {x: 6, y: 2, sample: 'keep-add', group: 'keep-add'},
        {x: 7, y: 4, sample: 'carry', group: 'carry'},
        {x: 6, y: 3, sample: 'carry', group: 'carry'}
      ],
      hints: ['把个位的两个数相加。', '凑成十个一时，就要换成一个十。']
    },
    {
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      step: .22,
      items: [
        {x: 4, y: 3, token: 'sub-42-5', group: 'borrow'},
        {x: 7, y: 4, token: 'sub-71-6', group: 'borrow'},
        {x: 4, y: 2, token: 'sub-65-4', group: 'keep-sub'},
        {x: 4, y: 5, token: 'sub-49-8', group: 'keep-sub'}
      ],
      docks: [
        {x: 7, y: 3, sample: 'borrow', group: 'borrow'},
        {x: 8, y: 4, sample: 'borrow', group: 'borrow'},
        {x: 8, y: 2, sample: 'keep-sub', group: 'keep-sub'},
        {x: 7, y: 5, sample: 'keep-sub', group: 'keep-sub'}
      ],
      hints: ['个位上的小方块够拿吗？', '不够拿时，从十位拆开一个十。']
    }
  ]
}));
depot.follow(rulePicture, game => {
  const picture = rules[game.level];
  if (rulePicture.getAttribute('src') !== picture) rulePicture.setAttribute('src', picture);
  return {x: 12, y: 157, w: 207, h: 102};
});
depot.follow('#first-operation-dock', game => game.level === 0 ? {x: 736, y: 297, w: 90, h: 90} : null);
