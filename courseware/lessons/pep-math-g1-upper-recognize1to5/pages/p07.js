(() => {
  const routes = [
    { direction: 'up', cards: [4, 2, 5, 1, 3], order: [1, 2, 3, 4, 5] },
    { direction: 'down', cards: [2, 5, 1, 3, 4], order: [5, 4, 3, 2, 1] },
  ];
  const badge = K.$('#route-badge');
  const slots = K.$('#route-slots');
  const tray = K.$('#route-tray');
  let level = 0;
  let task = routes[0];
  let placed = [];
  let teaching = false;
  let busy = false;
  let misses = 0;
  let timer;

  K.hud({ icon: '→', title: '两条送信路线', levels: routes.length });
  K.owl();
  K.ready({ emoji: '1→5', title: '两条送信路线', sub: '看阶梯方向，一张一张排数卡' });

  function card(parent, number, canChoose) {
    const item = K.el(canChoose ? 'button' : 'div', 'route-card' + (canChoose ? '' : ' placed'), '', parent);
    K.el('strong', '', String(number), item);
    const dots = K.el('span', 'route-dots', '', item);
    for (let i = 0; i < number; i++) K.el('i', '', '', dots);
    if (canChoose) {
      item.type = 'button';
      item.id = 'route-card-' + number;
      item.disabled = busy;
      item.setAttribute('aria-label', '数字' + number + '，' + number + '颗点');
      item.addEventListener('click', () => place(number));
    }
    return item;
  }

  function render() {
    badge.replaceChildren();
    slots.replaceChildren();
    tray.replaceChildren();
    const image = K.el('img', 'route-mark', '', badge);
    image.alt = '邮局的邮票';
    image.addEventListener('error', () => { image.remove(); }, { once: true });
    image.src = '__IMG:stamp__';
    const increasing = task.direction === 'up';
    K.el('span', '', increasing ? '从少到多' : '从多到少', badge);
    const stairs = K.el('span', 'route-stairs', '', badge);
    for (const height of (increasing ? [1, 2, 3, 4, 5] : [5, 4, 3, 2, 1])) {
      K.el('i', '', '', stairs).style.height = (height * 11) + 'px';
    }
    K.el('span', 'route-direction', '→', badge);
    for (let i = 0; i < 5; i++) {
      if (i < placed.length) card(slots, placed[i], false);
      else K.el('div', 'route-slot' + (i === placed.length ? ' next' : ''), '', slots);
    }
    for (const number of task.cards) {
      if (placed.includes(number)) K.el('div', 'route-slot vacant', '', tray);
      else card(tray, number, !teaching);
    }
    K.levels(routes.length, level);
  }

  function place(number) {
    if (busy || teaching) return;
    const expected = task.order[placed.length];
    if (number !== expected) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '看看这条路线是从少到多，还是从多到少。' : '和前一张比一比，下一步只多一颗或少一颗。', 'no');
      if (misses >= 3) K.highlight('#route-card-' + expected);
      return;
    }
    placed.push(number);
    misses = 0;
    busy = placed.length === task.order.length;
    render();
    K.sfx.tick(number);
    K.say(placed.length === 1 ? '第一张已经送到，再看下一张。' : '相邻两张的点，只差一颗。', 'ok');
    if (!busy) return;
    K.sfx.ok();
    K.star(1, slots);
    timer = setTimeout(() => {
      level++;
      if (level === routes.length) K.finish({ title: '两条路线都排好了', sub: '顺着方向，每一步多一颗或少一颗。', again: reset });
      else load();
    }, 850);
  }

  function load() {
    task = routes[level];
    placed = [];
    misses = 0;
    teaching = false;
    busy = false;
    render();
    K.say(task.direction === 'up' ? '看上坡，从少到多排。' : '看下坡，从多到少排。');
  }

  function reset() {
    clearTimeout(timer);
    level = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    load();
  }

  K.onStart = reset;
  K.onState = state => {
    if (state.play) { reset(); return; }
    if (!state.demo) return;
    clearTimeout(timer);
    teaching = true;
    task = state.demo === 'reverse' ? routes[1] : routes[0];
    placed = state.demo === 'forward' ? [2, 3] : state.demo === 'reverse' ? [5, 4] : [];
    render();
    K.say(state.demo === 'forward' ? '二多一颗就是三。' : state.demo === 'reverse' ? '五少一颗就是四。' : '先看阶梯方向，再选数卡。');
  };
  load();
})();
