const config = {
  title: '把采访图送进合适的票箱',
  sub: '听问句找图；听完回答，再送到喜欢或不喜欢的票箱。',
  doneText: '你按采访里的回答送好了图。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:survey-backdrop__',
    sticker: '__IMG:project-sticker__',
    frames: ['__IMG:survey-cart__', '__IMG:survey-cart-load__'],
    icons: {
      swimming: '__IMG:survey-swimming__',
      kites: '__IMG:survey-kites__',
      tigers: '__IMG:survey-tigers__',
      green: '__IMG:survey-green__',
      yes: '__IMG:survey-box-yes__',
      no: '__IMG:survey-box-no__'
    }
  },
  levels: [
    {
      pickup: [['swimming', 2], ['kites', 4]],
      drop: [['yes', 3], ['no', 6]],
      orders: [['swimming', 'yes']],
      lanes: [{row: 2, speed: .83, spacing: 5.8, phase: .8}],
      step: .34
    },
    {
      pickup: [['kites', 2], ['tigers', 6], ['swimming', 8]],
      drop: [['no', 1], ['yes', 5]],
      orders: [['kites', 'no'], ['tigers', 'yes']],
      lanes: [{row: 1, speed: -.99, spacing: 5.2, phase: 1.2}, {row: 3, speed: 1.06, spacing: 5.6, phase: .6}],
      step: .30
    },
    {
      pickup: [['green', 1], ['tigers', 3], ['kites', 6], ['swimming', 8]],
      drop: [['yes', 2], ['no', 6]],
      orders: [['green', 'yes'], ['swimming', 'yes'], ['kites', 'no']],
      lanes: [
        {row: 1, speed: -1.12, spacing: 5.1, phase: .8},
        {row: 2, speed: .84, spacing: 5.6, phase: .8},
        {row: 3, speed: 1.13, spacing: 5.2, phase: 1.7}
      ],
      step: .27
    }
  ].map(level => ({...level, hints: ['重听这一步，想想是哪张图或哪个票箱。', '看看发亮的站点，路空一些再走。']}))
};
config.cues = config.levels.map(level => {
  const steps = level.orders.flatMap(([item, answer]) => ['survey-' + item, 'reply-' + answer]);
  return {steps, goal: steps[0], hint: 'survey-hint', hint2: 'survey-help', praise: 'survey-praise'};
});

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#first-survey-card'), K.$('#first-survey-box'));
const activity = K.gameTemplates.listenDelivery(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
