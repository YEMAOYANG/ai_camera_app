const config = {
  title: '泡泡艇听词找画',
  sub: '听老师说，开到相应图的下方吹泡泡。',
  doneText: '听到的词和动作配上图了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:word-backdrop__',
    sticker: '__IMG:minute-sticker__',
    frames: ['__IMG:word-boat__', '__IMG:word-boat-pop__'],
    icons: {
      alarm: '__IMG:alarm-word__', watch: '__IMG:watch-word__', sit: '__IMG:sit-word__', wait: '__IMG:wait-word__',
      carry: '__IMG:back-carry__', back: '__IMG:back-point__', front: '__IMG:front-carry__'
    }
  },
  levels: [
    {
      rounds: [{target: 'alarm', cards: ['alarm', 'watch']}, {target: 'watch', cards: ['alarm', 'watch']}],
      drift: 11, pace: .63, tolerance: 62,
      hints: ['听是用铃叫醒，还是戴在手腕。', '移到亮起来的图下面。']
    },
    {
      rounds: [
        {target: 'wait', cards: ['sit', 'wait', 'alarm']},
        {target: 'sit', cards: ['sit', 'watch', 'wait']},
        {target: 'watch', cards: ['wait', 'alarm', 'watch']}
      ],
      drift: 28, pace: .97, tolerance: 55,
      hints: ['看清谁坐下、谁在站台等。', '看亮图，等小艇移到下面。']
    },
    {
      rounds: [
        {target: 'carry', cards: ['back', 'front', 'carry']},
        {target: 'back', cards: ['back', 'carry', 'front']},
        {target: 'front', cards: ['carry', 'front', 'back']},
        {target: 'carry', cards: ['front', 'carry', 'back']}
      ],
      drift: 44, pace: 1.18, tolerance: 51,
      hints: ['仔细听，是背篮子还是用手指背。', '对准发亮的图，再吹泡泡。']
    }
  ],
  cues: [
    ['word-alarm', 'word-watch'],
    ['word-wait', 'word-sit', 'word-watch'],
    ['word-carry-back', 'word-point-back', 'word-carry-front', 'word-carry-back']
  ].map(steps => ({steps, goal: steps[0], hint: 'word-hint', hint2: 'word-help', praise: 'word-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#minute-word-listen'), K.$('#minute-first-clock'));
const activity = K.gameTemplates.wordBubbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
