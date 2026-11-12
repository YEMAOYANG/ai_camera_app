const title = '点亮相差的灯靶';
const orderBoard = K.$('#lamp-order');
const orderPicture = K.$('#lamp-order-picture');
const orderCards = {
  'order-9-5': {rows: [9, 5], image: '__IMG:order-9-5__'},
  'order-8-6': {rows: [8, 6], image: '__IMG:order-8-6__'},
  'order-14-8': {rows: [8, 14], image: '__IMG:order-14-8__'},
  'order-13-8': {rows: [13, 8], image: '__IMG:order-13-8__'},
  'order-31-23': {rows: [31, 23, 27], image: '__IMG:order-31-23__'},
  'order-34-25': {rows: [34, 25, 29], image: '__IMG:order-34-25__'},
  'order-27-20': {rows: [27, 20, 22], image: '__IMG:order-27-20__'}
};
const matches = (id, count) => {
  const order = orderCards[id];
  return Boolean(order) && Math.abs(order.rows[0] - order.rows[1]) === count;
};
const target = (x, value) => ({x, value});
const config = {
  title,
  sub: '数出两排相差的灯，用左右箭头瞄准，再发射。',
  doneText: '每颗弹珠都点亮了与相差数一样多的灯。',
  voiceLead: true,
  art: {
    backdrop: '__IMG:lantern-grove__',
    sticker: '__IMG:camp-reward__',
    frames: ['__IMG:amber-marble__'],
    icons: {
      ...Object.fromEntries(Object.entries(orderCards).map(([id, order]) => [id, order.image])),
      'lamp-symbol': '__IMG:camp-lantern__',
      2: '__IMG:lamp-target-2__',
      4: '__IMG:lamp-target-4__',
      5: '__IMG:lamp-target-5__',
      6: '__IMG:lamp-target-6__',
      7: '__IMG:lamp-target-7__',
      8: '__IMG:lamp-target-8__',
      9: '__IMG:lamp-target-9__'
    }
  },
  levels: [
    {
      queue: ['order-9-5', 'order-8-6'],
      targets: [target(410, 2), target(640, 4), target(870, 5)],
      speed: 480, drift: 3
    },
    {
      queue: ['order-14-8', 'order-13-8'],
      targets: [target(404, 6), target(641, 4), target(876, 5)],
      speed: 520, drift: 10
    },
    {
      queue: ['order-31-23', 'order-34-25', 'order-27-20'],
      targets: [target(354, 7), target(543, 8), target(730, 6), target(918, 9)],
      speed: 555, drift: 15
    }
  ].map(level => ({
    ...level, matches, targetWidth: 152, targetHeight: 112, symbol: 'lamp-symbol',
    hints: ['从较短一排的尽头开始看。', '先数露出的几格，再瞄准亮一点的靶。']
  })),
  cues: Array.from({length: 3}, () => ({
    goal: 'lamp-goal', hint: 'lamp-hint', hint2: 'lamp-help', praise: 'lamp-praise'
  }))
};

K.ready({title, sub: config.sub});
K.stage().append(orderBoard, K.$('#center-lamp-dock'));
const game = K.gameTemplates.magnetMarbles(config);
const draw = game.draw;
game.draw = (g, context) => {
  draw(g, context);
  const world = g.data.w;
  orderBoard.hidden = !world || g.state === 'ready' || g.state === 'done';
  if (orderBoard.hidden || world.delay > 0 || g.state === 'between') return;
  const id = config.levels[g.level].queue[world.i];
  if (id && orderPicture.dataset.order !== id) {
    orderPicture.src = orderCards[id].image;
    orderPicture.dataset.order = id;
  }
};
game.onState = (_, state) => {
  if (state.pause === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(game);
