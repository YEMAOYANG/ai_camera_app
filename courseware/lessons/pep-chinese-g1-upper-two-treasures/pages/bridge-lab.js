K.ready({
  title: '给小兔搭好小桥',
  sub: '先看空位，再转动和放下木块。'
});

K.game(K.gameTemplates.shapeBridge({
  voiceLead: true,
  doneText: '木块都合上了，小兔过桥啦！',
  art: {
    backdrop: '__IMG:bridge-backdrop__',
    frames: ['__IMG:rabbit-ready__', '__IMG:rabbit-hop__'],
    sticker: '__IMG:reward-sticker__'
  },
  cues: [
    {goal: 'bridge-first', hint: 'bridge-hint', hint2: 'bridge-help', praise: 'bridge-praise'},
    {goal: 'bridge-turn', hint: 'bridge-hint', hint2: 'bridge-help', praise: 'bridge-praise'},
    {goal: 'bridge-check', hint: 'bridge-hint', hint2: 'bridge-help', praise: 'bridge-praise'}
  ],
  levels: [
    {
      seconds: 7.1,
      slots: [
        {col: 1, cells: [[0, 0], [1, 0]]},
        {col: 6, cells: [[0, 0], [1, 0], [0, 1], [1, 1]]}
      ],
      hints: ['看看木块和空位盖住哪几格。', '落慢了，找一找亮起来的空位。']
    },
    {
      seconds: 5.8,
      slots: [
        {col: 0, cells: [[0, 0], [0, 1], [1, 1]], turns: 1},
        {col: 4, cells: [[0, 0], [0, 1], [0, 2]], turns: 1},
        {col: 6, cells: [[0, 0], [1, 0]]}
      ],
      hints: ['找一找拐角，想想它朝哪边。', '转过来，再看看能不能盖住亮处。']
    },
    {
      seconds: 4.3,
      slots: [
        {col: 0, cells: [[0, 0], [0, 1], [1, 1]], turns: 3},
        {col: 2, cells: [[0, 0], [1, 0], [1, 1], [2, 1]], turns: 1},
        {col: 5, cells: [[0, 0], [1, 0], [2, 0], [1, 1]], turns: 2},
        {col: 8, cells: [[0, 0], [0, 1], [0, 2]], turns: 1}
      ],
      hints: ['先看哪一边凸出来，再动手转。', '木块慢下来了，对齐空位再放。']
    }
  ]
}));
