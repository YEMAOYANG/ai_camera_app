const config = {
  title: '泡泡艇听词找图',
  sub: '听老师说的是哪件事，开小艇吹到那张图。',
  doneText: '每句声音都找到画面啦。',
  voiceLead: true,
  stepVoiceLead: true,
  labels: {count:'数灯笼', grow:'长出叶', ask:'问', answer:'答'},
  art: {
    sticker: '__IMG:drop-small__',
    frames: ['__IMG:rain-boat__', '__IMG:rain-boat-pop__'],
    icons: {
      count: '__IMG:count-lanterns__', grow: '__IMG:grow-leaf__',
      ask: '__IMG:ask-scene__', answer: '__IMG:answer-scene__'
    }
  },
  levels: [
    {
      rounds: [{target:'count', cards:['count','grow']},{target:'grow', cards:['count','grow']}],
      drift:16, pace:.64, tolerance:62,
      hints:['先重听一次，想想画面在做什么。','卡片慢下来了，试试发亮的那张。']
    },
    {
      rounds: [
        {target:'grow', cards:['ask','grow','count']},{target:'ask', cards:['grow','count','ask']},
        {target:'count', cards:['count','ask','grow']}
      ],
      drift:34, pace:1.06, tolerance:55,
      hints:['听清是数东西、长出叶子，还是问问题。','看发亮的图，等船头对过去。']
    },
    {
      rounds: [
        {target:'answer', cards:['grow','ask','answer']},{target:'ask', cards:['answer','ask','count']},
        {target:'grow', cards:['grow','answer','ask']},{target:'count', cards:['ask','count','answer']}
      ],
      drift:50, pace:1.45, tolerance:48,
      hints:['听出谁正在问，谁接着给出答话。','图漂慢了，照着亮图重新找。']
    }
  ],
  cues: [
    {goal:'listen-count', hint:'bubble-hint', hint2:'bubble-hint-again', praise:'bubble-praise',
      steps:['listen-count','listen-grow']},
    {goal:'listen-grow', hint:'bubble-hint', hint2:'bubble-hint-again', praise:'bubble-praise',
      steps:['listen-grow','listen-ask','listen-count']},
    {goal:'listen-answer', hint:'bubble-hint', hint2:'bubble-hint-again', praise:'bubble-praise',
      steps:['listen-answer','listen-ask','listen-grow','listen-count']}
  ]
};

K.ready({title:config.title, sub:config.sub});
K.stage().append(K.$('#rain-listen-symbol'), K.$('#rain-first-count'));
const activity = K.gameTemplates.wordBubbles(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
