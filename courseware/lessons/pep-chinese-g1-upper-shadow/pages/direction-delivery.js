const config = {
  title: '听方位送道具',
  sub: '先听要拿什么，再送给纸偶指定方位的小伙伴。',
  doneText: '道具都送到影子剧场啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    sticker: '__IMG:rover__',
    frames: ['__IMG:rover__', '__IMG:rover-carry__', '__IMG:patrol__'],
    icons: {
      leaf: '__IMG:leaf__',
      bell: '__IMG:bell__',
      bookmark: '__IMG:bookmark__',
      front: '__IMG:station-front__',
      back: '__IMG:station-back__',
      left: '__IMG:station-left__',
      right: '__IMG:station-right__'
    }
  },
  levels: [
    {
      pickup: [['leaf', 3], ['bell', 6]],
      drop: [['front', 5], ['back', 2]],
      orders: [['leaf', 'front']],
      lanes: [{row: 2, speed: 0.9, spacing: 5.7, phase: 0}],
      step: 0.32,
      hints: ['重听一下，老师说了什么？', '看亮起来的位置，再过去试试。']
    },
    {
      pickup: [['leaf', 2], ['bell', 6], ['bookmark', 8]],
      drop: [['left', 5], ['right', 7], ['front', 1]],
      orders: [['bell', 'left'], ['bookmark', 'right']],
      lanes: [{row: 1, speed: -1.25, spacing: 4.6, phase: 2}, {row: 3, speed: 1.36, spacing: 4.6, phase: 1}],
      step: 0.26,
      hints: ['停在草地上，听清要送到哪边。', '看亮起来的位置，等巡车过去。']
    },
    {
      pickup: [['leaf', 1], ['bell', 4], ['bookmark', 7]],
      drop: [['front', 4], ['back', 6], ['left', 2], ['right', 8]],
      orders: [['bookmark', 'back'], ['leaf', 'right'], ['bell', 'left']],
      lanes: [
        {row: 1, speed: -1.8, spacing: 3.9, phase: 0.7},
        {row: 2, speed: 1.65, spacing: 4, phase: 2.2},
        {row: 3, speed: -1.6, spacing: 3.9, phase: 1.4}
      ],
      step: 0.21,
      hints: ['再听一遍，先确定自己正在取还是送。', '找亮起来的地方，再看看巡车。']
    }
  ],
  cues: [
    {goal: 'pick-leaf', hint: 'delivery-hint', hint2: 'delivery-hint-again', praise: 'delivery-praise',
      steps: ['pick-leaf', 'send-front']},
    {goal: 'pick-bell', hint: 'delivery-hint', hint2: 'delivery-hint-again', praise: 'delivery-praise',
      steps: ['pick-bell', 'send-left', 'pick-bookmark', 'send-right']},
    {goal: 'pick-bookmark', hint: 'delivery-hint', hint2: 'delivery-hint-again', praise: 'delivery-praise',
      steps: ['pick-bookmark', 'send-back', 'pick-leaf', 'send-right', 'pick-bell', 'send-left']}
  ]
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#shadow-delivery-demo-drop'));
K.game(K.gameTemplates.listenDelivery(config));
