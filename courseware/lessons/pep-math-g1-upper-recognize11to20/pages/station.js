(() => {
  const modes = {
    '十根一捆，接着数': 'pack',
    '十九添一，换一捆': 'twenty',
    '把数摆进两根杆': 'beads',
    '给数牌找位置': 'route',
    '哪边的小格更少': 'near',
  };
  const mode = modes[document.title];
  if (!mode) throw new Error('Unknown number station scene');
  K.$('#' + mode + '-view').hidden = false;
  const packTasks = [
    { trays: [9, 11, 10], answer: 10 },
    { loose: 4, choices: [13, 14, 15], answer: 14 },
    { loose: 8, choices: [16, 19, 18], answer: 18 },
  ];
  const beadTasks = [
    { target: 15, side: 'tens', choices: [2, 1, 0], answer: 1 },
    { target: 15, side: 'ones', choices: [8, 3, 5], answer: 5 },
    { target: 18, side: 'tens', choices: [0, 2, 1], answer: 1 },
    { target: 18, side: 'ones', choices: [5, 8, 3], answer: 8 },
  ];
  const routeTasks = [
    { target: 16, options: [18, 16, 14] }, { target: 19, options: [19, 18, 17] },
    { target: 11, options: [10, 12, 11] },
  ];
  const nearTasks = [12, 18, 17];
  const levels = { pack: 3, twenty: 2, beads: 4, route: 3, near: 3 }[mode];
  const readyText = {
    pack: '找正好十根的一盘，再看捆和散棒。',
    twenty: '先添一根，再把满十的散棒扎起来。',
    beads: '看数字和亮起的杆，把合适的珠子摆上去。',
    route: '先看两边，再把数牌放到空位。',
    near: '从红点向两边数，找小格少的那边。',
  };
  let level = 0;
  let demo = false;
  let demoMode = '';
  let busy = false;
  let misses = 0;
  let timer;
  let selected = null;
  let beads = { tens: 0, ones: 0 };

  K.hud({ icon: '◇', title: document.title, levels });
  K.owl();
  K.ready({ emoji: '▥', title: document.title, sub: readyText[mode] });

  function sticks(container, count) {
    container.replaceChildren();
    for (let i = 0; i < count; i += 1) K.el('i', 'stick-diagram', '', container);
  }

  function button(parent, kind, label, click, symbol = label) {
    const item = K.el('button', 'station-button ' + kind, null, parent);
    item.type = 'button';
    item.setAttribute('aria-label', String(label));
    item.textContent = symbol;
    item.disabled = demo || busy;
    item.onclick = () => { if (!demo && !busy) click(item); };
    return item;
  }

  function wrong(item, first, later) {
    misses += 1;
    K.sfx.no();
    K.shake(item);
    K.say(misses === 1 ? first : later, 'no');
  }

  function correct(item, caption) {
    busy = true;
    item.classList.add('success');
    K.sfx.ok();
    K.star(1, item);
    K.say(caption, 'ok');
    timer = setTimeout(() => {
      item.classList.remove('success');
      level += 1;
      selected = null;
      busy = false;
      misses = 0;
      if (level >= levels) {
        K.levels(levels, levels);
        K.finish({ title: '补给整理好了', sub: readyText[mode], again: reset });
        return;
      }
      if (mode === 'beads' && level === 2) beads = { tens: 0, ones: 0 };
      render();
      K.say(readyText[mode]);
    }, 860);
  }

  function renderPack() {
    const task = packTasks[level];
    const trays = K.$('#pack-trays');
    const result = K.$('#pack-count');
    const options = K.$('#pack-options');
    trays.hidden = !task.trays || demoMode === 'bundle';
    result.hidden = task.trays && demoMode !== 'bundle';
    trays.replaceChildren();
    options.replaceChildren();
    sticks(K.$('#pack-loose'), task.loose || 0);
    if (demoMode === 'counted') {
      [...K.$('#pack-loose').children].forEach((stick, index) => {
        stick.classList.add('counted-stick');
        stick.dataset.count = index + 1;
        stick.style.animationDelay = index * 520 + 'ms';
      });
    }
    if (task.trays && demoMode !== 'bundle') {
      for (const count of task.trays) {
        const item = button(trays, 'pack-tray', count + '根的一盘', control => {
          if (count !== task.answer) {
            wrong(control, '一根一根数，点过的别重复。', '每满一排看一次，还差几根才满十？');
            return;
          }
          correct(control, '正好十根，扎起来是一捆。');
          trays.hidden = true;
          result.hidden = false;
        }, '');
        sticks(item, count);
      }
    } else if (task.choices) {
      for (const value of task.choices) button(options, 'digit-option', value, control => {
        if (value !== task.answer) {
          wrong(control, '先看一捆，再数旁边的散棒。', '一捆表示十，散棒每根是一个一。');
          return;
        }
        correct(control, '读数时先说十，再说几个一。');
      });
    }
  }

  function renderExchange() {
    const add = K.$('#exchange-add');
    const tie = K.$('#exchange-tie');
    let count = demoMode === 'traded' ? 0 : demoMode === 'full' || level === 1 ? 10 : 9;
    if (selected === 'added') count = 10;
    if (selected === 'tied') count = 0;
    sticks(K.$('#exchange-ones'), count);
    K.$('#exchange-new-bundle').hidden = !(demoMode === 'traded' || selected === 'tied');
    [add, tie].forEach(item => { item.disabled = demo || busy; });
    add.onclick = () => {
      if (demo || busy) return;
      if (level !== 0) { wrong(add, '看看散棒已经有多少。', '满十时可以换成一捆。'); return; }
      selected = 'added';
      correct(add, '九根再添一根，散棒正好十根。');
      renderExchange();
    };
    tie.onclick = () => {
      if (demo || busy) return;
      if (level !== 1) { wrong(tie, '先数一数散棒，看看够不够。', '整整十根，才能扎成一捆。'); return; }
      selected = 'tied';
      correct(tie, '散棒扎成第二捆，总数还是二十。');
      renderExchange();
    };
  }

  function renderBeads() {
    const task = beadTasks[level];
    const demoTargets = { left: '11', both: '11', sixteen: '16' };
    K.$('#bead-target').textContent = demoTargets[demoMode] || task.target;
    for (const side of ['tens', 'ones']) {
      const column = K.$('#bead-' + side);
      const stack = column.querySelector('.bead-stack');
      stack.replaceChildren();
      column.classList.toggle('active', !demo && side === task.side);
      for (let i = 0; i < beads[side]; i += 1) K.el('i', '', '', stack);
    }
    const controls = K.$('#bead-choices');
    controls.replaceChildren();
    for (const n of task.choices) {
      const item = button(controls, 'bead-option', n + '颗珠子', control => {
        if (n !== task.answer) {
          wrong(control, '先看亮起来的这根杆。', '看数字牌上同一位置，再挑对应颗数。');
          return;
        }
        beads[task.side] = n;
        correct(control, '珠子放到了对应的数位。');
        renderBeads();
      }, '');
      if (n === 0) K.el('i', 'empty-counter', '', item);
      else for (let i = 0; i < n; i += 1) K.el('i', '', '', item);
    }
  }

  function renderRoute() {
    const task = demo ? { target: 12, options: [11, 12, 13] } : routeTasks[level];
    K.$('#route-left').textContent = task.target - 1;
    K.$('#route-right').textContent = task.target + 1;
    const hole = K.$('#route-hole');
    const filled = demoMode === 'filled' || selected === task.target;
    hole.textContent = filled ? task.target : '';
    hole.classList.toggle('completed', filled);
    const controls = K.$('#route-choices');
    controls.replaceChildren();
    for (const n of task.options) button(controls, 'digit-option', n, control => {
      if (n !== task.target) {
        wrong(control, '从左边这个数往后数一格。', '再从右边往前数一格，两边要对上。');
        return;
      }
      selected = n;
      correct(control, '读一下左边、中间和右边，顺序对了。');
      renderRoute();
    });
  }

  function renderNear() {
    const target = demo ? (demoMode === 'far' ? 18 : 12) : nearTasks[level];
    const line = K.$('#near-line');
    line.replaceChildren();
    const showLeft = selected === 'left' || busy || demoMode === 'paths';
    const showRight = selected === 'right' || busy || demoMode === 'paths';
    for (let n = 10; n <= 20; n += 1) {
      const tick = K.el('div', 'near-tick', null, line);
      if (n === target) {
        tick.classList.add('target');
        K.el('b', '', '', tick);
      }
      if ((showLeft && n < target) || (showRight && n >= target && n < 20)) tick.classList.add('walk');
      if ([10, target, 20].includes(n)) K.el('span', '', String(n), tick);
    }
    if (showLeft) K.el('span', 'near-count left', String(target - 10), line);
    if (showRight) K.el('span', 'near-count right', String(20 - target), line);
    for (const side of ['left', 'right']) {
      const item = K.$('#near-' + side);
      item.disabled = demo || busy;
      item.onclick = () => {
        if (demo || busy) return;
        selected = side;
        const answer = target < 15 ? 'left' : 'right';
        if (side !== answer) {
          wrong(item, '数数这一边的小格，再想想另一边。', '每小格是一步，别把端点当作一步。');
          renderNear();
          return;
        }
        correct(item, '两边都数小格，步数少的那边更近。');
        renderNear();
      };
    }
  }

  const renderer = { pack: renderPack, twenty: renderExchange, beads: renderBeads, route: renderRoute, near: renderNear }[mode];
  function render() {
    renderer();
    K.levels(levels, level);
  }

  function reset() {
    clearTimeout(timer);
    level = misses = 0;
    demo = busy = false;
    demoMode = '';
    selected = null;
    beads = { tens: 0, ones: 0 };
    K.$$('.station-button.success').forEach(item => item.classList.remove('success'));
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    render();
    K.say(readyText[mode]);
  }

  K.onStart = reset;
  K.onState = ({ mode: state }) => {
    reset();
    if (state === 'play') return;
    demo = true;
    demoMode = state;
    if (mode === 'pack' && (state === 'read' || state === 'counted')) level = 1;
    if (mode === 'pack' && state === 'read-eight') level = 2;
    if (mode === 'beads' && state === 'left') beads.tens = 1;
    if (mode === 'beads' && state === 'both') beads = { tens: 1, ones: 1 };
    if (mode === 'beads' && state === 'sixteen') beads = { tens: 1, ones: 6 };
    render();
  };

  K.$$('img').forEach(image => {
    image.addEventListener('error', () => {
      const parent = image.parentElement;
      const bundle = image.classList.contains('bundle-illustration') || parent.id === 'exchange-tie';
      image.classList.add('failed-image');
      const fallback = K.el('span', 'diagram-fallback', '', null);
      image.after(fallback);
      fallback.setAttribute('data-semantic-diagram', '小棒的数量后备图');
      sticks(fallback, bundle ? 10 : 1);
    }, { once: true });
  });
  render();
})();
