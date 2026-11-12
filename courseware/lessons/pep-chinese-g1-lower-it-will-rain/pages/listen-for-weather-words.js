const config = {
  title: '泡泡艇听词找图',
  sub: '听词，看画面，开到图的下面吹泡泡。',
  doneText: '听到的词找到画面了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:weather-backdrop__',
    sticker: '__IMG:game-sticker__',
    frames: ['__IMG:weather-boat__', '__IMG:weather-boat-pop__'],
    icons: {
      dark: '__IMG:overcast__', bright: '__IMG:bright__',
      wet: '__IMG:wet-leaf__', dry: '__IMG:dry-leaf__',
      surface: '__IMG:water-surface__', stuffy: '__IMG:stuffy__', rush: '__IMG:rush__',
      bend: '__IMG:bend__', stand: '__IMG:stand__',
      news: '__IMG:news__', free: '__IMG:free-time__', busy: '__IMG:busy__'
    }
  },
  levels: [
    {
      rounds: [{target: 'dark', cards: ['dark', 'bright']}, {target: 'wet', cards: ['dry', 'wet']}],
      drift: 10, pace: .62, tolerance: 62,
      hints: ['先重听一句，再比两张图。', '卡片慢了，找亮起来的图。']
    },
    {
      rounds: [
        {target: 'surface', cards: ['rush', 'surface', 'stuffy']},
        {target: 'stuffy', cards: ['stuffy', 'rush', 'surface']},
        {target: 'rush', cards: ['surface', 'stuffy', 'rush']}
      ],
      drift: 29, pace: .95, tolerance: 56,
      hints: ['听完再看，人或小船在做什么？', '找发亮的画面，开到下面再吹。']
    },
    {
      rounds: [
        {target: 'bend', cards: ['stand', 'news', 'bend']},
        {target: 'news', cards: ['news', 'free', 'stand']},
        {target: 'free', cards: ['busy', 'free', 'news']},
        {target: 'wet', cards: ['dry', 'dark', 'wet']}
      ],
      drift: 44, pace: 1.18, tolerance: 51,
      hints: ['听清动作或样子，再想一想。', '这次看亮起来的图，慢一点吹。']
    }
  ],
  cues: [
    {goal: 'word-dark', steps: ['word-dark', 'word-wet']},
    {goal: 'word-surface', steps: ['word-surface', 'word-stuffy', 'word-rush']},
    {goal: 'word-bend', steps: ['word-bend', 'word-news', 'word-free', 'word-wet']}
  ].map(cue => ({...cue, hint: 'word-hint', hint2: 'word-hint-again', praise: 'word-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#weather-listen-mark'), K.$('#weather-first-cloud'));
const activity = K.gameTemplates.wordBubbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
