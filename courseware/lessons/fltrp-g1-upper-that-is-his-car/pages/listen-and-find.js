K.ready({
  title: '听近远，接住那一幅图',
  sub: '听完整句，看物品离说话人近还是远。'
});

K.game(K.gameTemplates.wordBubbles({
  voiceLead: true,
  stepVoiceLead: true,
  doneText: '你听清了物品，也听清了远近！',
  art: {
    backdrop: '__IMG:bubble-backdrop__',
    frames: ['__IMG:bubble-boat__', '__IMG:bubble-boat-pop__'],
    sticker: '__IMG:home-sticker__',
    icons: {
      'near-book': '__IMG:near-book__',
      'far-book': '__IMG:far-book__',
      'near-car': '__IMG:near-car__',
      'far-car': '__IMG:far-car__',
      'near-ball': '__IMG:near-ball__',
      'far-ball': '__IMG:far-ball__',
      'near-desk': '__IMG:near-desk__',
      'far-desk': '__IMG:far-desk__',
      'near-pen': '__IMG:near-pen__',
      'far-pen': '__IMG:far-pen__'
    }
  },
  cues: [
    {goal:'near-book', hint:'distance-hint', hint2:'distance-help', praise:'distance-praise',
      steps:['near-book','far-book']},
    {goal:'far-car', hint:'distance-hint', hint2:'distance-help', praise:'distance-praise',
      steps:['far-car','near-ball','far-ball']},
    {goal:'far-desk', hint:'distance-hint', hint2:'distance-help', praise:'distance-praise',
      steps:['far-desk','near-pen','near-desk','far-pen']}
  ],
  levels: [
    {
      rounds: [
        {target:'near-book', cards:['near-book','far-book']},
        {target:'far-book', cards:['near-book','far-book']}
      ],
      drift: 8, pace: 0.53, tolerance: 61,
      hints: ['再听一遍。东西离说话人近，还是远？', '瞄准亮起来的图，再吹泡泡。']
    },
    {
      rounds: [
        {target:'far-car', cards:['near-car','near-ball','far-car']},
        {target:'near-ball', cards:['near-ball','far-ball','far-car']},
        {target:'far-ball', cards:['near-ball','far-ball','far-car']}
      ],
      drift: 20, pace: 0.70, tolerance: 57,
      hints: ['先听清说的是哪件东西。', '图慢下来了。听清远近，再对准亮处。']
    },
    {
      rounds: [
        {target:'far-desk', cards:['near-desk','far-desk','near-pen']},
        {target:'near-pen', cards:['far-pen','far-desk','near-pen']},
        {target:'near-desk', cards:['near-desk','far-pen','near-pen']},
        {target:'far-pen', cards:['near-desk','far-ball','far-pen']}
      ],
      drift: 28, pace: 0.93, tolerance: 52,
      hints: ['听物品，也听清楚开头。', '先找画里的说话人，再看东西放在哪儿。']
    }
  ]
}));
