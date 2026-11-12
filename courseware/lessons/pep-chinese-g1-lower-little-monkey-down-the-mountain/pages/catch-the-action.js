const config = {
  title: '泡泡艇接动作',
  sub: '听词，看手和肩，开到图下面吹泡泡。',
  doneText: '听到的动作都接住啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:action-backdrop__',
    sticker: '__IMG:monkey-sticker__',
    frames: ['__IMG:action-boat__', '__IMG:action-boat-pop__'],
    icons: {
      split: '__IMG:act-break-icon__', pluck: '__IMG:act-pick-icon__',
      shoulder: '__IMG:act-shoulder-icon__', cup: '__IMG:act-cup-icon__', hug: '__IMG:act-hug-icon__',
      ballHug: '__IMG:act-ball-hug-icon__', ballCup: '__IMG:act-ball-cup-icon__', ballToss: '__IMG:act-ball-toss-icon__'
    }
  },
  levels: [
    {
      rounds: [{target: 'split', cards: ['split', 'pluck']}, {target: 'pluck', cards: ['split', 'pluck']}],
      drift: 9, pace: .61, tolerance: 62
    },
    {
      rounds: [
        {target: 'shoulder', cards: ['cup', 'shoulder', 'hug']},
        {target: 'cup', cards: ['hug', 'shoulder', 'cup']},
        {target: 'hug', cards: ['hug', 'cup', 'shoulder']}
      ],
      drift: 24, pace: .87, tolerance: 57
    },
    {
      rounds: [
        {target: 'ballToss', cards: ['ballHug', 'ballCup', 'ballToss']},
        {target: 'ballCup', cards: ['ballToss', 'ballCup', 'ballHug']},
        {target: 'ballHug', cards: ['ballHug', 'ballToss', 'ballCup']},
        {target: 'pluck', cards: ['split', 'shoulder', 'pluck']},
        {target: 'shoulder', cards: ['cup', 'shoulder', 'ballHug']}
      ],
      drift: 38, pace: 1.09, tolerance: 51
    }
  ].map(level => ({...level, hints: ['再听一听，看手在哪里。', '卡片慢了，看看发亮的动作。']})),
  cues: [
    ['act-break', 'act-pick'],
    ['act-shoulder', 'act-cup', 'act-hug'],
    ['act-ball-toss', 'act-ball-cup', 'act-ball-hug', 'act-pick', 'act-shoulder']
  ].map(steps => ({goal: steps[0], steps, hint: 'act-hint', hint2: 'act-hint2', praise: 'act-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#monkey-action-listen'), K.$('#monkey-action-first'));
const activity = K.gameTemplates.wordBubbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
