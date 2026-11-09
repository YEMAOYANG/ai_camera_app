(function () {
  const tasks = [[6, 9], [9, 8]];
  const choices = K.$('#path-choices');
  const ticks = K.$('#path-ticks');
  const arcs = K.$('#path-arcs');
  const equation = K.$('#path-equation');
  const rabbit = K.$('#path-rabbit');
  const rabbitImage = K.$('img', rabbit);
  rabbitImage.onerror = () => rabbitImage.remove();
  const start = K.$('#path-start');
  const middle = K.$('#path-ten');
  const end = K.$('#path-end');
  let round = 0, a = 6, b = 9, phase = 0, demo = false, misses = 0, timer;

  K.hud({icon: '→', title: '沿石径跳两段', levels: tasks.length});
  K.owl();
  K.ready({emoji: '→', title: '沿石径跳两段', sub: '先到十，再跳剩下的格子'});

  function x(number) { return 22 + (number - 5) * 80; }
  for (let value = 5; value <= 18; value++) {
    const tick = K.el('b', 'path-tick', String(value), ticks);
    tick.style.left = `${x(value) - 10}px`;
  }

  function arc(from, to, style) {
    const first = x(from), last = x(to), center = (first + last) / 2;
    return `<path class="${style}" d="M ${first} 145 Q ${center} 13 ${last} 145 M ${last - 13} 135 L ${last} 145 L ${last - 4} 126"/><text x="${center}" y="65" text-anchor="middle">＋${to - from}</text>`;
  }

  function render() {
    const destination = phase === 0 ? a : phase === 1 ? 10 : a + b;
    start.style.left = `${x(a)}px`;
    middle.style.left = `${x(10)}px`;
    end.style.left = `${x(a + b)}px`;
    end.classList.toggle('hide', phase < 2);
    rabbit.style.left = `${x(destination)}px`;
    arcs.innerHTML = phase === 0 ? '' : arc(a, 10, 'first') + (phase === 2 ? arc(10, a + b, 'second') : '');
    equation.textContent = phase < 2 ? `${a} ＋ ${b}` : `${a} ＋ ${b} ＝ ${a + b}`;
    choices.replaceChildren();
    if (phase < 2) {
      const need = phase === 0 ? 10 - a : b - (10 - a);
      const options = need === 1 ? [1, 2, 3] : [need - 1, need, need + 1];
      for (const steps of K.shuffle(options)) {
        const button = K.el('button', 'path-choice', '', choices);
        button.type = 'button';
        button.dataset.steps = steps;
        button.setAttribute('aria-label', `向右跳${steps}格`);
        for (let i = 0; i < steps; i++) K.el('i', '', '', button);
        button.onclick = () => choose(steps, need);
      }
    }
    K.levels(tasks.length, round);
  }

  function choose(steps, need) {
    if (demo || phase >= 2) return;
    if (steps !== need) {
      misses++;
      K.sfx.no();
      K.shake(choices);
      K.highlight(phase === 0 ? '#path-start' : '#path-arcs');
      K.say(misses === 1 ? '看看兔子现在站在哪一格。' : '数跨过的间隔，别把起点也数进去。', 'no');
      return;
    }
    phase++;
    misses = 0;
    start.classList.remove('teach-hl');
    arcs.classList.remove('teach-hl');
    render();
    K.sfx.ok();
    if (phase === 1) {
      K.say('第一跳到十！第二跳走完剩下的格子。', 'ok');
      return;
    }
    K.star(1, rabbit);
    K.say('两段走完，到了合起来的总数。', 'ok');
    timer = setTimeout(() => {
      if (++round < tasks.length) load(tasks[round]);
      else K.finish({title: '两次都跳好啦', sub: '先跳到十，再跳剩下的。', again: reset});
    }, 1000);
  }

  function load(task) {
    [a, b] = task;
    phase = misses = 0;
    render();
    K.say('数从起点到十有几格，选第一段的点。');
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
      load([8, 5]);
      K.say('先看老师示范。');
    }
    if (demo && state.first && phase < 1) { phase = 1; render(); }
    if (demo && state.second && phase < 2) { phase = 2; render(); }
    if (state.play) reset();
  };
  load(tasks[0]);
})();
