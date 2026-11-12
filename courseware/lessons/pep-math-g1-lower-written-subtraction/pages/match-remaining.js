K.ready({
  title: '竖式落块',
  sub: '算出余量，把竖式落到对应图卡旁边。',
});

K.game(K.gameTemplates.fallingTiles({
  art: {
    backdrop: '__IMG:supply-backdrop__',
    sticker: '__IMG:feather-sticker__',
    icons: {
      'ledger-54-23': '__IMG:tile-ledger-54-23__',
      'ledger-82-37': '__IMG:tile-ledger-82-37__',
      'ledger-70-6': '__IMG:tile-ledger-70-6__',
      'stock-31': '__IMG:tile-stock-31__',
      'stock-32': '__IMG:tile-stock-32__',
      'stock-23': '__IMG:tile-stock-23__',
      'stock-45': '__IMG:tile-stock-45__',
      'stock-55': '__IMG:tile-stock-55__',
      'stock-64': '__IMG:tile-stock-64__',
      'stock-74': '__IMG:tile-stock-74__',
      'stock-10': '__IMG:tile-stock-10__',
    },
  },
  voiceLead: true,
  doneText: '三张余量记录都对上啦！',
  cues: [
    {goal: 'ledger-first', hint: 'ledger-check', hint2: 'ledger-recheck', praise: 'ledger-praise'},
    {goal: 'ledger-borrow', hint: 'ledger-check', hint2: 'ledger-recheck', praise: 'ledger-praise'},
    {goal: 'ledger-zero', hint: 'ledger-check', hint2: 'ledger-recheck', praise: 'ledger-praise'},
  ],
  levels: [
    {
      interval: 2.25, symbol: 'ledger-54-23', pieces: ['ledger-54-23'],
      bottom: ['stock-31', null, null, 'stock-32', 'stock-23', null],
      pairs: [['ledger-54-23', 'stock-31']],
    },
    {
      interval: 2.25, symbol: 'ledger-82-37', pieces: ['ledger-82-37'],
      bottom: ['stock-55', null, null, 'stock-45', 'stock-32', null],
      pairs: [['ledger-82-37', 'stock-45']],
    },
    {
      interval: 2.25, symbol: 'ledger-70-6', pieces: ['ledger-70-6'],
      bottom: ['stock-74', null, null, 'stock-10', 'stock-64', null],
      pairs: [['ledger-70-6', 'stock-64']],
    },
  ],
}));
