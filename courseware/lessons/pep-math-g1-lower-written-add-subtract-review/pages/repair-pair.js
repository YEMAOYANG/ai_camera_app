K.ready({title: '接住要核对的记录', sub: '看左边原竖式，让落牌贴着对应记录。'});

const originals = {
  'copy-plus': '__IMG:repair-copy-plus__', 'copy-minus': '__IMG:repair-copy-minus__',
  'carry-a': '__IMG:repair-carry-a__', 'carry-b': '__IMG:repair-carry-b__',
  'borrow-a': '__IMG:repair-borrow-a__', 'borrow-b': '__IMG:repair-borrow-b__'
};
const levels = [
  {bottom: [null, 'copy-plus-ok', null, 'copy-plus-swapped', 'copy-minus-ok', null],
   pieces: ['copy-plus', 'copy-minus'],
   pairs: [['copy-plus', 'copy-plus-ok'], ['copy-minus', 'copy-minus-ok']], interval: 1.48, symbol: 'badge',
   hints: ['按十位和个位依次核对原数。', '抄倒了两个数字，已经换成另一个数。']},
  {bottom: ['75', null, '65', null, '63', '53'], pieces: ['carry-a', 'carry-b'],
   pairs: [['carry-a', '75'], ['carry-b', '63']], interval: 1.03, symbol: 'badge',
   hints: ['个位满十了没有？', '换成一盒以后，算十位时要把它加上。']},
  {bottom: ['38', '28', null, '35', '25', null], pieces: ['borrow-a', 'borrow-b'],
   pairs: [['borrow-a', '28'], ['borrow-b', '25']], interval: .77, symbol: 'badge',
   hints: ['原来的十位已经少了一盒。', '先减个位，再用拆过以后的十位来减。']}
];
const repairGame = K.game(K.gameTemplates.fallingTiles({
  voiceLead: true,
  doneText: '核对过的记录都找到了对应卡。',
  art: {
    backdrop: '__IMG:repair-backdrop__',
    sticker: '__IMG:leaf-badge__',
    icons: {
      badge: '__IMG:record-badge__',
      'copy-plus': '__IMG:tile-copy-plus__', 'copy-minus': '__IMG:tile-copy-minus__',
      'carry-a': '__IMG:tile-carry-a__', 'carry-b': '__IMG:tile-carry-b__',
      'borrow-a': '__IMG:tile-borrow-a__', 'borrow-b': '__IMG:tile-borrow-b__',
      'copy-plus-ok': '__IMG:tile-copy-plus-correct__',
      'copy-plus-swapped': '__IMG:tile-copy-plus-swapped__',
      'copy-minus-ok': '__IMG:tile-copy-minus-correct__',
      '75': '__IMG:result-75__', '65': '__IMG:result-65__', '63': '__IMG:result-63__', '53': '__IMG:result-53__',
      '28': '__IMG:result-28__', '38': '__IMG:result-38__', '25': '__IMG:result-25__', '35': '__IMG:result-35__'
    }
  },
  cues: [
    {goal: 'repair-copy-goal', hint: 'repair-hint', hint2: 'repair-help', praise: 'repair-praise'},
    {goal: 'repair-carry-goal', hint: 'repair-hint', hint2: 'repair-help', praise: 'repair-praise'},
    {goal: 'repair-borrow-goal', hint: 'repair-hint', hint2: 'repair-help', praise: 'repair-praise'}
  ],
  levels
}));
const record = K.$('#current-record');
repairGame.follow(record, game => {
  const pieces = levels[game.level].pieces;
  const world = game.data.w;
  // The matched tile stays in view during its brief success flash and in the teacher demo.
  const showingMatch = world?.delay > 0 && world.flash - world.delay > .04 && world.i > 0;
  const index = (world?.i ?? 0) - Number(showingMatch);
  const image = originals[pieces[Math.min(index, pieces.length - 1)]];
  if (record.getAttribute('src') !== image) record.setAttribute('src', image);
  return {x: 30, y: 155, w: 290, h: 246};
});
repairGame.follow('#repair-columns', () => ({x: 121, y: 187, w: 145, h: 168}));
repairGame.follow('#first-repair-cell', game => game.level === 0 ? {x: 501, y: 526, w: 68, h: 70} : null);
