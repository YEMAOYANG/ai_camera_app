const config = {
  title: '听词开艇找画面',
  sub: '听老师念一个词，开到相应图的下面吹泡泡。',
  doneText: '听到的词都有合适的画。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:word-backdrop__',
    sticker: '__IMG:stationery-sticker__',
    frames: ['__IMG:word-boat__', '__IMG:word-boat-pop__'],
    icons: {
      book: '__IMG:fresh-book__', year: '__IMG:new-year__',
      safe: '__IMG:safe-home__', flat: '__IMG:flat-path__',
      partners: '__IMG:partners__', together: '__IMG:together__'
    }
  },
  levels: [
    {
      rounds: [{target: 'book', cards: ['book', 'year']}, {target: 'year', cards: ['book', 'year']}],
      drift: 11, pace: .62, tolerance: 62,
      hints: ['先听说的是书，还是过年。', '对着发亮的图再吹。']
    },
    {
      rounds: [
        {target: 'flat', cards: ['flat', 'safe', 'book']},
        {target: 'safe', cards: ['book', 'year', 'safe']},
        {target: 'year', cards: ['safe', 'year', 'flat']}
      ],
      drift: 27, pace: .98, tolerance: 56,
      hints: ['听清是路平平的，还是回到家。', '看亮起来的图，移到下面。']
    },
    {
      rounds: [
        {target: 'partners', cards: ['safe', 'book', 'partners']},
        {target: 'together', cards: ['together', 'year', 'flat']},
        {target: 'flat', cards: ['partners', 'flat', 'safe']},
        {target: 'book', cards: ['safe', 'together', 'book']}
      ],
      drift: 43, pace: 1.17, tolerance: 51,
      hints: ['先想听到谁在做哪件事。', '等船头对着亮起来的图，再吹。']
    }
  ],
  cues: [
    ['word-new-book', 'word-new-year'],
    ['word-flat', 'word-safe', 'word-new-year'],
    ['word-partners', 'word-together', 'word-flat', 'word-new-book']
  ].map(steps => ({steps, goal: steps[0], hint: 'word-hint', hint2: 'word-help', praise: 'word-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#word-listen-mark'), K.$('#word-first-book'));
const activity = K.gameTemplates.wordBubbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
