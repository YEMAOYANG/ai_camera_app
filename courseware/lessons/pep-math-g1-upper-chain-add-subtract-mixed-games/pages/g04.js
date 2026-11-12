(function () {
  const book = {image: '__IMG:single-book__', fallback: {count: 1}, color: '#FFDD83'};
  function remove(start, amount, first) {
    return {goal: {groups: [{count: start}, '−', {count: amount, color: '#9E5544'}]},
      lamps: Array.from({length: start}, () => book), turnOff: amount,
      hint: '先看右边要拿走的点，再数已经熄灭的灯。',
      hint2: '如果打多了，再击中一盏暗灯就能重新点亮。',
      success: first ? '数数还亮着的灯，下一步接着这些数。' : '第二次只从仍亮的灯里熄灭。'};
  }
  function story(start, first, second) {
    return [remove(start, first, true), remove(start - first, second, false)];
  }
  K.ready({title: '瞄准熄书灯', sub: '每借走一本书，就瞄准打灭一盏灯。确认后，从仍亮的数继续。'});
  K.game(K.gameTemplates.slingshot({
    levels: [
      {name: '第一轮还剩多少', demoRounds: story(6, 2, 1), rounds: story(5, 1, 2)},
      {name: '两次都要拿走几本', rounds: story(9, 2, 3)},
      {name: '灯更多，接着余数减', rounds: story(10, 3, 2)}
    ],
    doneText: '只从还在架上的书里再拿。第一次剩下的数量是第二步的起点。'
  }));
})();
