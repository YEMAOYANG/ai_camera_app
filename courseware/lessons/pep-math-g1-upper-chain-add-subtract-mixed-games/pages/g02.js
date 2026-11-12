(function () {
  const groupColors = ['#388B87', '#9A663A', '#67518D'];
  function route(collect, groups, airborne, distractors) {
    const goal = {groups: groups.map((count, index) => ({count, color: groupColors[index]}))};
    const track = groups.map((value, index) => ({value, airborne: airborne[index],
      visual: {count: value, color: groupColors[index]}}));
    for (const [index, value, high] of distractors) {
      track.splice(index, 0, {value, airborne: high,
        visual: {count: value, color: groupColors[index % groupColors.length]}});
    }
    return {goal, collect, track, hint: '再看看目标里的三批和篮里已有的数量。',
      hint2: '一批一批收。遇到多余的书包，可以躲开。',
      success: '三批书合在一起，数量正好！'};
  }
  K.ready({title: '运书跑酷', sub: '接住三批指定数量的书。点一下跳起来，绕开多余的书包。'});
  const options = K.gameTemplates.runner({
    levels: [
      {name: '三批合起来', demoRounds: [route(5, [2, 2, 1], [false, true, false], [[1, 7, false]])],
        rounds: [route(7, [2, 1, 4], [false, true, false], [[2, 8, false]])]},
      {name: '空中和地面都要看',
        rounds: [route(9, [3, 2, 4], [true, false, true], [[1, 8, true]])]},
      {name: '从更多书包里挑出三批',
        rounds: [route(10, [3, 2, 5], [true, false, true], [[1, 6, false], [4, 9, true]])]}
    ],
    doneText: '每接一批，篮里的数就增加一次。把刚才得到的数带到下一步。'
  });
  const update = options.update;
  options.update = function (g, dt) {
    const data = g.data;
    const before = data.world.count;
    update(g, dt);
    if (g.data === data && data.world.count > 10) {
      data.world.count = before;
      data.world.retry = 1.3;
      K.gameTemplates.tools.hint(g);
    }
  };
  K.game(options);
})();
