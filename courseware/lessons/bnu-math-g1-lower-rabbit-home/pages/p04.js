(function () {
  const tasks = [[6, 8], [8, 7]];
  const board = K.$('#ten-board');
  const tray = K.$('#remainder-tray');
  const bank = K.$('#unit-bank');
  const equation = K.$('#lamp-equation');
  const slots = Array.from({length: 10}, () => K.el('span', 'lamp-slot', '', board));
  let round = 0, a = 6, b = 8, phase = 0, demo = false, misses = 0, timer;

  K.hud({icon: '＋', title: '给十格灯架补灯', levels: tasks.length});
  K.owl();
  K.ready({emoji: '＋', title: '给十格灯架补灯', sub: '看空格，选一组刚好放满'});

  function beads(parent, count, added) {
    for (let i = 0; i < count; i++) K.el('i', 'lamp-bead' + (added ? ' new' : ''), '', parent);
  }

  function render() {
    const need = 10 - a;
    equation.textContent = phase === 2 ? `10 ＋ ${b - need} ＝ ${a + b}` : `${a} ＋ ${b}`;
    K.$('.lamp-strip', board)?.remove();
    for (let index = 0; index < slots.length; index++) {
      const slot = slots[index];
      const lit = phase === 1 || (phase === 0 && index < a);
      slot.className = 'lamp-slot' + (lit ? ' lit' : '');
      slot.style.display = phase === 2 ? 'none' : '';
      slot.replaceChildren();
      if (lit) beads(slot, 1, index >= a);
    }
    if (phase === 2) {
      const strip = K.el('span', 'lamp-strip', '', board);
      for (let i = 0; i < 10; i++) K.el('i', '', '', strip);
      strip.style.gridArea = '1 / 1 / 3 / 6';
      strip.style.alignSelf = 'center';
    }
    tray.replaceChildren();
    beads(tray, phase ? b - need : b, true);
    K.levels(tasks.length, round);
  }

  function choose(count) {
    if (demo || phase) return;
    if (count !== 10 - a) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '先看看哪些格子还空着。' : '数一数空格，再数一数这组灯珠。', 'no');
      for (const slot of slots.slice(a)) slot.classList.add('hint');
      return;
    }
    phase = 1;
    render();
    K.sfx.ok();
    K.say('正好填满了！看看外面还留着几颗。', 'ok');
    bank.querySelectorAll('button').forEach(button => { button.disabled = true; });
    timer = setTimeout(() => {
      phase = 2;
      render();
      K.star(1, tray);
      timer = setTimeout(() => {
        if (++round < tasks.length) load(tasks[round]);
        else K.finish({title: '小灯都安好啦', sub: '先凑十，再加剩下的。', again: reset});
      }, 1000);
    }, 750);
  }

  function load(task) {
    [a, b] = task;
    phase = misses = 0;
    K.drags = [];
    bank.replaceChildren();
    const need = 10 - a;
    const alternatives = need === 1 ? [1, 2, 3] : [need - 1, need, need + 1];
    for (const count of K.shuffle(alternatives)) {
      const button = K.el('button', 'lamp-choice', '', bank);
      button.type = 'button';
      button.dataset.count = count;
      button.setAttribute('aria-label', `${count}颗灯珠`);
      beads(button, count, true);
      button.onclick = () => choose(count);
      K.drag(button, {enabled: () => !demo && !phase, targets: () => [board], onDrop: (_, target) => { if (target) choose(count); }});
    }
    render();
    K.say('数数十格灯架的空位，选一组正好补满。');
  }

  function reset() {
    clearTimeout(timer);
    demo = false;
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    load(tasks[0]);
  }

  K.onStart = reset;
  K.onState = state => {
    if (state.demo) {
      clearTimeout(timer);
      K.$('#finish')?.classList.add('gone');
      demo = true;
      round = 0;
      load([9, 7]);
      K.say('先看老师示范。');
    }
    if (demo && state.fill && phase < 1) { phase = 1; render(); }
    if (demo && state.exchange && phase < 2) { phase = 2; render(); }
    if (state.play) reset();
  };
  load(tasks[0]);
})();
