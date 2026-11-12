const title = '把弹珠送到正确数量';
const board = K.$('#nursery-order');
const orderPicture = K.$('#nursery-order-picture');
const previousPicture = K.$('#nursery-previous-answer');
const orders = {
  'order-find-13': {image: '__IMG:order-find-13__', amount: 9, gap: 4, type: 'long'},
  'order-find-gap': {image: '__IMG:order-find-gap__', amount: 13, other: 9, type: 'difference'},
  'order-find-27': {image: '__IMG:order-find-27__', amount: 36, gap: 9, type: 'short'},
  'order-find-63': {image: '__IMG:order-find-63__', amount: 36, other: 27, type: 'total'},
  'order-west-27': {image: '__IMG:order-west-27__', amount: 33, gap: 6, type: 'short'},
  'order-south-35': {image: '__IMG:order-south-35__', gap: 8, usePrevious: 'order-west-27', type: 'long'}
};
function value(id) {
  const order = orders[id];
  if (!order) return null;
  const amount = order.usePrevious ? value(order.usePrevious) : order.amount;
  if (order.type === 'long') return amount + order.gap;
  if (order.type === 'short') return amount - order.gap;
  if (order.type === 'difference') return Math.abs(amount - order.other);
  return amount + order.other;
}
const matches = (id, count) => value(id) === count;
const target = (x, value) => ({x, value});
const config = {
  title,
  sub: '听口令看数量图，用左右键瞄准，再发射。',
  doneText: '你找到了每问需要的数量，还会把它带到下一问。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:seedling-shed__',
    sticker: '__IMG:garden-reward__',
    frames: ['__IMG:garden-marble__'],
    icons: {
      ...Object.fromEntries(Object.entries(orders).map(([id, order]) => [id, order.image])),
      'sprout-symbol': '__IMG:garden-sprout__',
      4: '__IMG:target-4__',
      9: '__IMG:target-9__',
      13: '__IMG:target-13__',
      27: '__IMG:target-27__',
      35: '__IMG:target-35__',
      39: '__IMG:target-39__',
      41: '__IMG:target-41__',
      45: '__IMG:target-45__',
      63: '__IMG:target-63__'
    }
  },
  levels: [
    {queue: ['order-find-13', 'order-find-gap'],
      targets: [target(405, 4), target(640, 13), target(875, 9)], speed: 476, drift: 3},
    {queue: ['order-find-27', 'order-find-63'],
      targets: [target(365, 27), target(550, 45), target(735, 63), target(920, 9)], speed: 515, drift: 9},
    {queue: ['order-west-27', 'order-south-35'],
      targets: [target(365, 39), target(548, 27), target(733, 41), target(919, 35)], speed: 550, drift: 15}
  ].map(level => ({
    ...level, matches, targetWidth: 152, targetHeight: 112, symbol: 'sprout-symbol',
    hints: ['先指一指问号在哪里。', '再看两段怎样接起来。']
  })),
  cues: [
    {steps: ['marble-find-longer', 'marble-find-gap']},
    {steps: ['marble-find-shorter', 'marble-find-total']},
    {steps: ['marble-find-shorter', 'marble-use-previous']}
  ].map(cues => ({...cues, goal: cues.steps[0], hint: 'marble-hint', hint2: 'marble-help', praise: 'marble-praise'}))
};

K.ready({title, sub: config.sub});
K.stage().append(board, K.$('#first-seed-target'));
const game = K.gameTemplates.magnetMarbles(config);
const draw = game.draw;
game.draw = (g, context) => {
  draw(g, context);
  const world = g.data.w;
  board.hidden = !world || g.state === 'ready' || g.state === 'done';
  if (board.hidden || g.state === 'between') return;
  const id = config.levels[g.level].queue[world.i];
  if (!id || orderPicture.dataset.order === id) return;
  orderPicture.src = orders[id].image;
  orderPicture.dataset.order = id;
  const carry = orders[id].usePrevious ? world.locked?.value : undefined;
  previousPicture.hidden = carry === undefined;
  if (carry !== undefined) previousPicture.src = config.art.icons[carry];
  else previousPicture.removeAttribute('src');
};
game.onState = (_, state) => {
  if (state.pause === false) K.$$('.teach-hl', K.stage()).forEach(el => el.classList.remove('teach-hl'));
};
K.game(game);
