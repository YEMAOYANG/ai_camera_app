const orderPictures = {
  'delivery-5-plus-4': '__IMG:delivery-5-plus-4__',
  'delivery-10-minus-3': '__IMG:delivery-10-minus-3__',
  'delivery-18-minus-8': '__IMG:delivery-18-minus-8__',
  'delivery-23-plus-9': '__IMG:delivery-23-plus-9__',
  'delivery-27-minus-11': '__IMG:delivery-27-minus-11__',
};
const windowPictures = {round: '__IMG:window-round__', triangle: '__IMG:window-triangle__'};
const config = {
  title: '把刚好的票签送过去',
  sub: '听数量，到袋子前拿取。再听窗口，避开来车，到了按方钮。',
  doneText: '你把每袋票签送到了听到的窗口。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:theater-path__',
    frames: ['__IMG:wood-cart__', '__IMG:wood-cart-moving__', '__IMG:wood-van__'],
    icons: {
      ...windowPictures,
      7: '__IMG:delivery-total-7__', 9: '__IMG:delivery-total-9__', 10: '__IMG:delivery-total-10__',
      13: '__IMG:delivery-total-13__', 16: '__IMG:delivery-total-16__',
      23: '__IMG:delivery-total-23__', 32: '__IMG:delivery-total-32__',
    },
  },
  levels: [
    {
      pickup: [[7, 2], [9, 4], [13, 7]], drop: [['round', 3], ['triangle', 6]],
      orders: [[9, 'round']], comparisons: ['delivery-5-plus-4'],
      lanes: [{row: 2, speed: .83, spacing: 5.8, phase: .8}], step: .34,
    },
    {
      pickup: [[10, 2], [13, 5], [7, 7]], drop: [['triangle', 2], ['round', 6]],
      orders: [[7, 'triangle'], [10, 'round']], comparisons: ['delivery-10-minus-3', 'delivery-18-minus-8'],
      lanes: [{row: 1, speed: -.99, spacing: 5.2, phase: 1.2}, {row: 3, speed: 1.06, spacing: 5.6, phase: .6}],
      step: .30,
    },
    {
      pickup: [[23, 1], [32, 3], [16, 6]], drop: [['round', 7], ['triangle', 2]],
      orders: [[32, 'round'], [16, 'triangle']], comparisons: ['delivery-23-plus-9', 'delivery-27-minus-11'],
      lanes: [
        {row: 1, speed: -1.12, spacing: 5.1, phase: .8},
        {row: 2, speed: .84, spacing: 5.6, phase: .8},
        {row: 3, speed: 1.13, spacing: 5.2, phase: 1.7},
      ], step: .27,
    },
  ].map(level => ({
    ...level,
    hints: ['重听这一步。拿袋子先算数量，送票签先找窗口标记。', '亮起的是该去的位置，等路空一些再走。'],
  })),
};
config.cues = config.levels.map(level => {
  const steps = level.orders.flatMap(([, window], index) => [level.comparisons[index], 'take-to-' + window]);
  return {goal: steps[0], steps, hint: 'delivery-hint', hint2: 'delivery-help', praise: 'delivery-praise'};
});

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#first-ticket-conditions'), K.$('#first-ticket-window'));
const activity = K.gameTemplates.listenDelivery(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};

const draw = activity.draw;
const orderCard = K.el('img', 'ticket-order-card', null, K.stage());
orderCard.setAttribute('data-semantic-diagram', '');
orderCard.style.cssText = 'position:absolute;left:18px;top:229px;width:205px;height:91px;object-fit:contain;pointer-events:none';
activity.draw = (game, context) => {
  draw(game, context);
  const {level, progress = 0} = game.data;
  const index = Math.floor(progress / 2);
  const order = level?.orders[index];
  const carrying = progress % 2 === 1;
  const picture = order && (carrying ? windowPictures[order[1]] : orderPictures[level.comparisons[index]]);
  orderCard.hidden = game.state !== 'play' || !picture;
  orderCard.alt = carrying ? '这一步要送到的窗口标记' : '这一步取货的已知组和相差段';
  if (picture && orderCard.getAttribute('src') !== picture) orderCard.src = picture;
};
K.game(activity);
