K.ready({
  title: '把工具送到修补台',
  sub: '听清困难，挑合适的工具，再开小车送过去。'
});

K.game(K.gameTemplates.listenDelivery({
  voiceLead: true,
  stepVoiceLead: true,
  doneText: '工具送齐了，修补台可以开工啦！',
  art: {
    backdrop: '__IMG:tool-backdrop__',
    frames: ['__IMG:tool-cart__', '__IMG:tool-cart-lift__', '__IMG:lane-cart__'],
    sticker: '__IMG:reward-sticker__',
    icons: {
      brace: '__IMG:prop-brace__',
      clip: '__IMG:prop-clip__',
      marker: '__IMG:prop-marker__',
      frame: '__IMG:station-frame__',
      papers: '__IMG:station-papers__',
      sign: '__IMG:station-sign__'
    }
  },
  cues: [
    {goal: 'frame-pick', hint: 'tool-hint', hint2: 'tool-help', praise: 'tool-praise',
      steps: ['frame-pick', 'frame-drop']},
    {goal: 'sign-pick', hint: 'tool-hint', hint2: 'tool-help', praise: 'tool-praise',
      steps: ['sign-pick', 'sign-drop', 'papers-pick', 'papers-drop']},
    {goal: 'papers-pick', hint: 'tool-hint', hint2: 'tool-help', praise: 'tool-praise',
      steps: ['papers-pick', 'papers-drop', 'frame-pick', 'frame-drop', 'sign-pick', 'sign-drop']}
  ],
  levels: [
    {
      pickup: [['brace', 3], ['clip', 7]],
      drop: [['frame', 6], ['papers', 1]],
      orders: [['brace', 'frame']],
      lanes: [{row: 2, speed: 0.84, spacing: 5.7, phase: 0}],
      step: 0.32,
      hints: ['再听一次困难，想工具能做什么。', '慢一点，看看亮起来的地方。']
    },
    {
      pickup: [['clip', 2], ['marker', 6], ['brace', 8]],
      drop: [['papers', 4], ['sign', 7], ['frame', 1]],
      orders: [['marker', 'sign'], ['clip', 'papers']],
      lanes: [
        {row: 1, speed: -1.22, spacing: 4.8, phase: 1.6},
        {row: 3, speed: 1.30, spacing: 4.9, phase: 0.9}
      ],
      step: 0.26,
      hints: ['停在草地上，想好下一步。', '小车慢了些，可以再听一次。']
    },
    {
      pickup: [['marker', 1], ['brace', 4], ['clip', 7]],
      drop: [['sign', 6], ['frame', 2], ['papers', 8]],
      orders: [['clip', 'papers'], ['brace', 'frame'], ['marker', 'sign']],
      lanes: [
        {row: 1, speed: -1.62, spacing: 4.4, phase: 0.7},
        {row: 2, speed: 1.46, spacing: 4.5, phase: 2.0},
        {row: 3, speed: -1.52, spacing: 4.3, phase: 1.4}
      ],
      step: 0.21,
      hints: ['等车道空出来，再向前走。', '看亮起来的位置，重新想想路线。']
    }
  ]
}));
