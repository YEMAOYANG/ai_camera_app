K.ready({
  title: '钓出一图的算式',
  sub: '在水里滑一滑，移动船。对准鱼，再点船放钩。',
  img: '__IMG:studio__'
});

function round(picture, [orange, blue], options, matches, success) {
  return {
    goal: {image: picture, fallback: {groups: [
      {count: orange, color: '#e57b37'}, {count: blue, color: '#228caa'}
    ]}},
    options, matches, success,
    hint: '先数两组各有几枚，再看鱼背上的算式。',
    hint2: '加法要用两个部分，减法要从总数开始。'
  };
}

K.game(K.gameTemplates.fishing({
  goalHeight: 114,
  doneText: '认出了两部分和总数，捞齐同一张图的不同算式！',
  levels: [
    {
      name: '两边一样多',
      demoRounds: [
        round('__IMG:fish-equal__', [3, 3], ['3 + 3 = 6', '6 − 2 = 4', '6 − 3 = 3'], [0, 2], '两组一样多，只钓两道不同算式。')
      ],
      rounds: [
        round('__IMG:fish-equal__', [3, 3], ['6 − 4 = 2', '6 − 3 = 3', '3 + 3 = 6'], [1, 2], '换哪一组都是三，两个式子都找到了。')
      ]
    },
    {
      name: '两边不一样多',
      rounds: [
        round('__IMG:fish-seven__', [3, 4], ['7 − 3 = 4', '4 + 3 = 7', '6 − 3 = 3', '7 − 4 = 3', '3 + 4 = 7'], [0, 1, 3, 4], '三和四合成七，一共四道不同算式。'),
        round('__IMG:fish-six__', [2, 4], ['4 + 2 = 6', '6 − 2 = 4', '6 − 4 = 2', '2 + 4 = 6', '7 − 4 = 3'], [0, 1, 2, 3], '二和四合成六，两加两减都齐了。')
      ]
    }
  ]
}));
