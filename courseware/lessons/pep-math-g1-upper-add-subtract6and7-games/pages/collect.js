K.ready({
  title: '跑着装满计数筐',
  sub: '地上的圆片跑着接，高处的圆片跳着接。两包合起来要刚刚好。',
  img: '__IMG:studio__'
});

function round(goal, track, success) {
  return {
    goal: {count: goal}, collect: goal, track, success,
    hint: '先看看筐里有多少，再想还差几枚。',
    hint2: '可以从已经装进去的数，接着数到目标。'
  };
}

K.game(K.gameTemplates.runner({
  doneText: '两包圆片合起来，换个先后一样多。',
  levels: [
    {
      name: '装到六',
      demoRounds: [
        round(6, [{value: 2}, {value: 3, airborne: true}, {value: 4, airborne: true}], '两枚和四枚，刚好六枚！')
      ],
      rounds: [
        round(6, [{value: 4}, {value: 3, airborne: true}, {value: 2, airborne: true}], '四枚和两枚，刚好六枚！')
      ]
    },
    {
      name: '装到七，再换个顺序',
      rounds: [
        round(7, [{value: 3, airborne: true}, {value: 1}, {value: 4}, {value: 1, airborne: true}], '三枚和四枚，刚好七枚！'),
        round(7, [{value: 4}, {value: 1, airborne: true}, {value: 1}, {value: 3, airborne: true}], '顺序换过来，还是七枚！')
      ]
    }
  ]
}));
