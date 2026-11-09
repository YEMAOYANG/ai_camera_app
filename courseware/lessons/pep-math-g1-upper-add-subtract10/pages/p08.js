(function () {
  const targets = [7, 2, 0];
  let level = 0, target = 7, removed = 0, choices = [], solved = false, demo = false, misses = 0, timer;
  K.hud({icon:'◈', title:'留下指定的灯片', levels:targets.length});
  K.owl();
  K.ready({emoji:'◈', title:'留下指定的灯片', sub:'选要取走的数量，让剩下的图一样'});

  function render() {
    const board = K.$('#remain-board'), goal = K.$('#remain-target'), cards = K.$('#adjust-controls');
    board.replaceChildren(); goal.replaceChildren(); cards.replaceChildren();
    K.el('span', 'goal-number', String(target), goal);
    const dots = K.el('span', 'cluster', '', goal);
    for (let i = 0; i < target; i++) K.el('i', 'lamp green', '', dots);
    for (let i = 0; i < 10; i++) {
      const slot = K.el('span', 'slot', '', board);
      if (i < 10 - removed) K.el('i', 'lamp blue', '', slot);
    }
    for (const count of choices) {
      const card = K.el('button', 'card', '', cards);
      card.type = 'button'; card.disabled = demo || solved;
      card.setAttribute('aria-label', '拿走' + count + '片');
      if (removed === count) card.classList.add(solved ? 'selected' : 'previewed');
      const group = K.el('span', 'cluster', '', card);
      for (let i = 0; i < count; i++) K.el('i', 'lamp blue', '', group);
      card.onclick = () => choose(count);
    }
    K.$('#missing-equation').textContent = '10 − ' + (solved ? removed : '?') + ' = ' + target;
    K.levels(targets.length, level);
  }
  function choose(count) {
    if (demo || solved) return;
    removed = count;
    if (10 - removed !== target) {
      misses++; render(); K.sfx.no();
      K.say(misses === 1 ? '把板上的灯片和目标图一一比一比。' : '板上多了就换一组更多的，少了就换一组更少的。', 'no');
      return;
    }
    solved = true; render(); K.star(1, K.$('#remain-board')); K.sfx.ok();
    K.say('剩下的数量和目标一样，缺数找到了。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === targets.length) K.finish({title:'找到了该拿走的数量', sub:'十减掉拿走的，等于剩下的。', again:reset});
      else load();
    }, 1000);
  }
  function load() {
    target = targets[level]; removed = 0; solved = false; misses = 0;
    const correct = 10 - target;
    choices = K.shuffle(correct === 10 ? [8, 9, 10] : [correct - 1, correct, correct + 1]);
    render(); K.say('板上有十片，要留下' + target + '片。');
  }
  function reset() {
    clearTimeout(timer); level = 0; demo = false; K.stars = 0;
    K.$('#star-n').textContent = '0'; load();
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.play) { reset(); return; }
    if (!state.demo && !state.demoOne && !state.demoTwo && !state.demoAll) return;
    clearTimeout(timer); level = 0; demo = true; K.stars = 0; K.$('#star-n').textContent = '0';
    target = state.demoAll ? 0 : 8;
    removed = state.demoAll ? 10 : state.demoTwo ? 2 : state.demoOne ? 1 : 0;
    choices = state.demoAll ? [8, 9, 10] : [1, 2, 3];
    solved = removed === 10 - target; render();
    K.say('从十片里拿走' + removed + '片，留下' + (10 - removed) + '片。');
  };
  load();
})();
