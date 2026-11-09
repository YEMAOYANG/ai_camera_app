(function () {
  const starts = [1, 4, 5];
  let level = 0, first = 1, joined = false, swapped = false, demo = false, misses = 0, timer;
  K.hud({icon:'◈', title:'两组合成十', levels:starts.length});
  K.owl();
  K.ready({emoji:'◈', title:'两组合成十', sub:'选一组灯片，把空格刚好装满'});

  function render() {
    const second = 10 - first;
    const board = K.$('#join-board');
    board.replaceChildren();
    for (let i = 0; i < 10; i++) {
      const slot = K.el('span', 'slot', '', board);
      const color = ((i < first) !== swapped) ? 'blue' : 'green';
      if (i < first || joined) K.el('i', 'lamp ' + color, '', slot);
    }
    K.$('#join-equation').textContent = first + ' + ' + (joined ? second : '?') + ' = 10';
    const cards = K.$('#join-cards');
    cards.replaceChildren();
    if (!joined) {
      const options = demo ? [second - 1, second, second + 1] : K.shuffle([second - 1, second, second + 1]);
      for (const count of options) {
        const card = K.el('button', 'card', '', cards);
        card.type = 'button'; card.disabled = demo; card.setAttribute('aria-label', count + '片灯片');
        const group = K.el('span', 'cluster', '', card);
        for (let i = 0; i < count; i++) K.el('i', 'lamp green', '', group);
        card.onclick = () => choose(count);
      }
    }
    K.levels(starts.length, level);
  }
  function choose(count) {
    if (demo || joined) return;
    if (first + count !== 10) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '先看哪些格还空着，再挑一组。' : '一个空格放一片，不能剩下，也不能挤出来。', 'no');
      return;
    }
    joined = true; render(); K.star(1, K.$('#join-board')); K.sfx.ok();
    K.say('两组灯片各放一次，正好装满十格。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === starts.length) K.finish({title:'正好合成十', sub:'两个部分一起数，得到整体。', again:reset});
      else load();
    }, 1000);
  }
  function load() {
    first = starts[level]; joined = false; swapped = false; misses = 0; render();
    K.say('展板上有' + first + '片，哪组刚好装满？');
  }
  function reset() {
    clearTimeout(timer); level = 0; demo = false; K.stars = 0;
    K.$('#star-n').textContent = '0'; load();
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.play) { reset(); return; }
    if (!state.demo && !state.demoJoined && !state.demoSwapped) return;
    clearTimeout(timer); demo = true; level = 0; K.stars = 0; K.$('#star-n').textContent = '0';
    swapped = !!state.demoSwapped; first = swapped ? 8 : 2; joined = !!(state.demoJoined || state.demoSwapped);
    render(); K.say(joined ? '两组都保留，一共十片。' : '先看两片蓝灯片和还空着的格子。');
  };
  load();
})();
