const pieces = {
  'tile-6-plus-2': 8, 'tile-9-plus-3': 12,
  'tile-11-minus-2': 9, 'tile-15-minus-7': 8,
  'tile-24-plus-7': 31, 'tile-26-minus-8': 18,
};
const art = {
  'tile-6-plus-2': '__IMG:tile-6-plus-2__',
  'tile-9-plus-3': '__IMG:tile-9-plus-3__',
  'tile-11-minus-2': '__IMG:tile-11-minus-2__',
  'tile-15-minus-7': '__IMG:tile-15-minus-7__',
  'tile-24-plus-7': '__IMG:tile-24-plus-7__',
  'tile-26-minus-8': '__IMG:tile-26-minus-8__',
  8: '__IMG:tile-total-8__',
  12: '__IMG:tile-total-12__',
  9: '__IMG:tile-total-9__',
  31: '__IMG:tile-total-31__',
  18: '__IMG:tile-total-18__',
};
const config = {
  title: '把道具卡落到配对处',
  sub: '看两排，算出问号。移到正确数量旁边，再让卡落下。',
  doneText: '你把比较图和需要的数量配好了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {backdrop: '__IMG:theater-stage__', sticker: '__IMG:wood-cart__', icons: art},
  levels: [
    {bottom: [null, 12, null, null, 8, null], pieces: ['tile-6-plus-2', 'tile-9-plus-3'], interval: 1.25},
    {bottom: [9, null, null, 8, null, null], pieces: ['tile-11-minus-2', 'tile-15-minus-7'], interval: 1.12},
    {bottom: [null, 18, null, null, null, 31], pieces: ['tile-24-plus-7', 'tile-26-minus-8'], interval: .94},
  ].map(level => ({
    ...level,
    matches: (order, target) => typeof target === 'number' && pieces[order] === target,
    hints: ['先找方牌这一排，再看下排是接长了，还是留下空格。', '算好问号，再移到对应底牌紧挨的空格。'],
  })),
};
config.cues = config.levels.map(level => ({
  goal: level.pieces[0], steps: level.pieces, hint: 'tile-hint', hint2: 'tile-help', praise: 'tile-praise',
}));

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#first-prop-card'), K.$('#first-total-card'));
const activity = K.gameTemplates.fallingTiles(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};

// Show the currently falling order at a readable scale beside its small moving copy.
const draw = activity.draw;
const orderCard = K.el('img', 'prop-order-card', null, K.stage());
orderCard.alt = '本张落牌的已知组和相差段';
orderCard.setAttribute('data-semantic-diagram', '');
orderCard.style.cssText = 'position:absolute;left:108px;top:218px;width:300px;height:107px;object-fit:contain;pointer-events:none';
activity.draw = (game, context) => {
  draw(game, context);
  const order = game.data.level?.pieces[game.data.progress];
  orderCard.hidden = game.state !== 'play' || !order;
  if (order && orderCard.getAttribute('src') !== art[order]) orderCard.src = art[order];
};
K.game(activity);
