const config = {
  title: '夏日词语泡泡艇',
  sub: '听老师念一个词，开到那张图的下面吹泡泡。',
  doneText: '游园的画卡配好啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:summer-backdrop__',
    sticker: '__IMG:firefly-sticker__',
    frames: ['__IMG:summer-boat__', '__IMG:summer-boat-pop__'],
    icons: {
      ice: '__IMG:ice-pop__', melon: '__IMG:watermelon__', soup: '__IMG:mung-soup__',
      mat: '__IMG:bamboo-mat__', coil: '__IMG:mosquito-coil__', lotion: '__IMG:floral-water__',
      fan: '__IMG:palm-fan__', chair: '__IMG:bamboo-chair__', firefly: '__IMG:firefly__'
    }
  },
  levels: [
    {
      rounds: [
        {target: 'ice', cards: ['ice', 'melon']},
        {target: 'melon', cards: ['soup', 'melon']},
        {target: 'soup', cards: ['soup', 'ice']}
      ],
      drift: 10, pace: .62, tolerance: 62,
      hints: ['先听一遍，再看形状。', '对着发亮的图再吹。']
    },
    {
      rounds: [
        {target: 'mat', cards: ['coil', 'mat', 'lotion']},
        {target: 'coil', cards: ['coil', 'lotion', 'mat']},
        {target: 'lotion', cards: ['mat', 'coil', 'lotion']}
      ],
      drift: 27, pace: .96, tolerance: 56,
      hints: ['看看是席子、盘香还是小瓶。', '卡片慢了，试试发亮的图。']
    },
    {
      rounds: [
        {target: 'fan', cards: ['chair', 'firefly', 'fan']},
        {target: 'chair', cards: ['chair', 'fan', 'coil']},
        {target: 'firefly', cards: ['coil', 'firefly', 'chair']},
        {target: 'coil', cards: ['fan', 'firefly', 'coil']}
      ],
      drift: 41, pace: 1.2, tolerance: 51,
      hints: ['重听词，再看看哪件东西配得上。', '船头对准亮图再吹。']
    }
  ],
  cues: [
    ['summer-ice', 'summer-melon', 'summer-soup'],
    ['summer-mat', 'summer-coil', 'summer-lotion'],
    ['summer-fan', 'summer-chair', 'summer-firefly', 'summer-coil']
  ].map(steps => ({steps, goal: steps[0], hint: 'summer-hint', hint2: 'summer-help', praise: 'summer-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#summer-listen-mark'), K.$('#summer-first-ice'));
const activity = K.gameTemplates.wordBubbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
