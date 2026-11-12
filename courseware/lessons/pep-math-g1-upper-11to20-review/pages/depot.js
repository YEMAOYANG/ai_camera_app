const card = (value) => 'cards-' + value;
const beads = (value) => 'beads-' + value;
const number = (value) => 'number-' + value;
const item = (x, y, value, picture) => ({x, y, token: picture(value), group: 'count-' + value});
const tray = (x, y, value, picture) => ({x, y, sample: picture(value), group: 'count-' + value});

const levels = [
  {
    map: ['########', '#......#', '#.S....#', '#......#', '########'],
    step: 0.30,
    items: [item(3, 2, 11, card), item(3, 3, 14, card)],
    docks: [tray(5, 2, 11, beads), tray(5, 3, 14, number)],
    hints: ['先找一组十，再数散开的。', '左边的珠记十，右边的珠记一个。'],
  },
  {
    map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
    step: 0.23,
    items: [item(4, 2, 12, card), item(4, 4, 19, beads), item(3, 3, 15, card)],
    docks: [tray(6, 2, 12, beads), tray(7, 4, 19, card), tray(6, 3, 15, number)],
    hints: ['看清两边各有几个十、几个一。', '车只能推，绕到卡片背后再走。'],
  },
  {
    map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
    step: 0.19,
    items: [item(4, 3, 13, card), item(7, 4, 10, card), item(4, 2, 20, beads), item(4, 5, 15, beads)],
    docks: [tray(7, 3, 13, beads), tray(8, 4, 10, beads), tray(8, 2, 20, card), tray(7, 5, 15, number)],
    hints: ['零散的都没有，看看有几组十。', '先给其他卡留条路，回转键可以撤回。'],
  },
];

const cues = ['depot-goal', 'depot-goal-b', 'depot-goal-c'].map(goal => ({
  goal, hint: 'depot-hint', hint2: 'depot-help', praise: 'depot-praise',
}));

const config = {
  title: '展品收货站',
  sub: '数目一样的卡片和托盘配成对。',
  doneText: '每张卡都送到了数量相同的托盘。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:depot-room__',
    sticker: '__IMG:exhibit-flag__',
    frames: ['__IMG:rover-idle__', '__IMG:rover-moving__'],
    icons: {
      'cards-10': '__IMG:depot-cards-10__', 'cards-11': '__IMG:depot-cards-11__',
      'cards-12': '__IMG:depot-cards-12__', 'cards-13': '__IMG:depot-cards-13__',
      'cards-14': '__IMG:depot-cards-14__', 'cards-15': '__IMG:depot-cards-15__',
      'cards-19': '__IMG:depot-cards-19__', 'cards-20': '__IMG:depot-cards-20__',
      'beads-10': '__IMG:depot-beads-10__', 'beads-11': '__IMG:depot-beads-11__',
      'beads-12': '__IMG:depot-beads-12__', 'beads-13': '__IMG:depot-beads-13__',
      'beads-15': '__IMG:depot-beads-15__', 'beads-19': '__IMG:depot-beads-19__',
      'beads-20': '__IMG:depot-beads-20__',
      'number-14': '__IMG:depot-number-14__', 'number-15': '__IMG:depot-number-15__',
    },
  },
  levels,
  cues,
};

K.ready({title: config.title, sub: config.sub});
K.game(K.gameTemplates.sortingDepot(config));
