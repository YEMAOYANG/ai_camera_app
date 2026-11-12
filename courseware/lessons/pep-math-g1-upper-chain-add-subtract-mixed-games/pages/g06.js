(function () {
  function step(before, change, choices, beginning) {
    const after = before + change;
    return {before, change, beginning, goal: {groups: [
      {count: before}, change > 0 ? '+' : '−',
      {count: Math.abs(change), color: change > 0 ? '#328A65' : '#9E5544'}
    ]}, player: {count: before}, options: choices.map(count => ({count})), answer: choices.indexOf(after),
    hint: '先看架上的书，再看借还是还。',
    hint2: change > 0 ? '还书要合起来。' : '借书要拿走这一批。',
    success: '架上的数变了，接着算。'};
  }
  function story(start, first, second, firstChoices, secondChoices) {
    return [step(start, first, firstChoices, true),
      step(start + first, second, secondChoices, false)];
  }
  K.ready({title: '借还碰碰车', sub: '开车去碰这一步算完应有的数量。书架变化以后，再接下一步。'});
  const options = K.gameTemplates.bumper({
    levels: [
      {name: '先还书，再借书', demoRounds: story(4, -1, 2, [2, 3, 5], [4, 6, 5]),
        rounds: story(3, 2, -1, [3, 5, 6], [4, 5, 6])},
      {name: '先借书，再还书', rounds: story(8, -3, 2, [4, 6, 5, 8], [8, 7, 5, 6])},
      {name: '比较不同先后', rounds: [
        ...story(6, 2, -4, [9, 8, 7, 6], [2, 5, 4, 6]),
        ...story(6, -4, 2, [2, 4, 6, 8], [6, 3, 5, 4])
      ]}
    ],
    doneText: '最后一样多，中间不一定一样。先后要和事情对得上。'
  });
  const T = K.gameTemplates.tools;
  const book = {image: '__IMG:single-book__', fallback: {count: 1}};
  T.validateVisual(book);
  const setup = options.setup;
  const reset = options.reset;
  const update = options.update;
  const draw = options.draw;
  function current(data) {
    return data.plan.rounds[data.round];
  }
  options.setup = function (g) {
    setup(g);
    g.follow('#game-stock', () => T.area(894, 184, 611, 70));
  };
  options.reset = function (g, level) {
    reset(g, level);
    g.data.stock = current(g.data).before;
    g.pointer.active = false;
  };
  options.update = function (g, dt) {
    const state = g.data;
    const round = state.round;
    const resolved = state.next > 0;
    update(g, dt);
    if (g.data !== state) return;
    if (!resolved && state.next > 0) {
      state.stock += current(state).change;
    }
    if (state.round !== round) {
      const next = current(state);
      if (next.beginning) state.stock = next.before;
      else T.assert(state.stock === next.before, 'the next step must carry the shelf count');
      g.pointer.active = false;
    }
  };
  options.draw = function (g, c) {
    draw(g, c);
    const stock = g.data.stock;
    if (stock == null) return;
    T.box(c, 588, 149, 611, 70, '#F1DDC0', 22, '#A6835B');
    T.line(c, {x: 611, y: 205}, {x: 1175, y: 205}, '#956C44', 6);
    for (let i = 0; i < stock; i++) {
      T.visual(c, book, 632 + 48 * i, 178, 43, 48);
    }
    T.text(c, stock, 1157, 179, 34, 45);
  };
  options.bubbleAt = () => ({x: 264, y: 175});
  K.game(options);
})();
