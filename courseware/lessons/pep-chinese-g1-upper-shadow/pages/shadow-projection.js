const config = {
  title: '把影子照进框',
  sub: '按左右箭头挪灯，影子进框后按圆钮。',
  doneText: '把不同位置的影子都留在幕上啦。',
  voiceLead: true,
  art: {sticker: '__IMG:lamp__', frames: ['__IMG:lamp__']},
  levels: [
    {
      tolerance: 32,
      shots: [{x: 766, d: 228, shape: 'circle'}],
      hints: ['先猜灯往哪边移，再看影子。', '对着亮框挪小灯，等轮廓重合。']
    },
    {
      tolerance: 24,
      shots: [{x: 484, d: 228, shape: 'triangle'}, {x: 796, d: 228, shape: 'triangle'}],
      hints: ['这次目标换边了，看看虚线。', '慢慢挪小灯，让影子轮廓和亮框对齐。']
    },
    {
      tolerance: 16,
      shots: [{x: 844, d: 228, shape: 'square'}, {x: 431, d: 228, shape: 'square'},
        {x: 736, d: 228, shape: 'square'}],
      hints: ['一点点移动，把两个轮廓对齐。', '慢慢挪小灯，让影子轮廓和亮框对齐。']
    }
  ],
  cues: Array.from({length: 3}, () => ({
    goal: 'shadow-goal', hint: 'shadow-hint', hint2: 'shadow-hint-again', praise: 'shadow-praise'
  }))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#shadow-paper'));
K.game(K.gameTemplates.shadowStage(config));
