(function () {
  const tasks = [{boxes: [5, 7, 8], target: 15}, {boxes: [7, 8, 9], target: 17}];
  const demonstration = {boxes: [6, 8, 10], target: 16};
  const shelf = K.$('#tray-choices');
  const mat = K.$('#delivery-mat');
  const check = K.$('#check-pair');
  const targetPanel = K.$('#target-count');
  const surplus = K.$('#extra-biscuits');
  const total = K.$('#delivery-total');
  let round = 0, task = tasks[0], demo = false, accepted = false, misses = 0, timer;
  const placed = [];
  const cards = [];

  K.hud({icon: '＋', title: '挑两盒，刚刚好', levels: tasks.length});
  K.owl();
  K.ready({emoji: '＋', title: '挑两盒，刚刚好', sub: '把两盒移到餐垫，再点对勾'});

  function seeds(parent, amount) {
    for (let i = 0; i < amount; i++) K.el('i', 'seed', '', parent);
  }

  function isExact() {
    return placed.length === 2 && placed.reduce((sum, card) => sum + Number(card.dataset.count), 0) === task.target;
  }

  function render() {
    const counts = placed.map(card => Number(card.dataset.count));
    const sum = counts.reduce((a, b) => a + b, 0);
    K.$('#target-number').textContent = task.target;
    targetPanel.replaceChildren();
    seeds(targetPanel, task.target);
    [...targetPanel.children].slice(0, sum).forEach(seed => seed.classList.add('covered'));
    surplus.replaceChildren();
    seeds(surplus, Math.max(0, sum - task.target));
    total.textContent = counts.length === 2 ? `${counts[0]} ＋ ${counts[1]} ＝ ${sum}` : counts[0] || '＋';
    mat.querySelectorAll('.mat-slot').forEach(slot => slot.remove());
    for (let i = 0; i < 2 - placed.length; i++) K.el('span', 'mat-slot', '', mat);
    mat.dataset.full = placed.length === 2;
    check.disabled = demo || accepted || placed.length !== 2;
    check.classList.toggle('box-ready', !check.disabled && isExact());
    cards.forEach(card => {
      card.disabled = accepted || demo;
      const selected = placed.includes(card);
      card.classList.toggle('selected', selected);
      card.setAttribute('aria-pressed', String(selected));
    });
    K.levels(tasks.length, round);
  }

  function place(card, destination) {
    if (destination === mat && !placed.includes(card)) {
      if (placed.length === 2) shelf.append(placed.pop());
      placed.push(card);
      mat.append(card);
    }
    if (destination === shelf && placed.includes(card)) {
      placed.splice(placed.indexOf(card), 1);
      shelf.append(card);
    }
    render();
    if (!demo && isExact()) {
      targetPanel.classList.remove('teach-hl');
      K.say('一样多了。点对勾，把两盒送过去。', 'ok');
    }
  }

  function submit() {
    if (demo || accepted || placed.length !== 2) return;
    const sum = placed.reduce((value, card) => value + Number(card.dataset.count), 0);
    if (sum !== task.target) {
      misses++;
      K.sfx.no();
      K.highlight('#target-count');
      K.shake(total);
      K.say(misses === 1 ? '看看两盒的总数跟要的一样吗？' : sum < task.target ? '餐点还少一些，可以换一盒再试。' : '餐点多了一些，可以换一盒再试。', 'no');
      return;
    }
    accepted = true;
    render();
    K.sfx.ok();
    K.star(1, mat);
    K.say('两盒合起来刚刚好！', 'ok');
    timer = setTimeout(() => {
      if (++round < tasks.length) load(tasks[round]);
      else K.finish({title: '两盒送到啦', sub: '先看需要多少，再合一合。', again: reset});
    }, 1100);
  }

  function load(next) {
    task = next;
    accepted = false;
    misses = 0;
    placed.length = cards.length = 0;
    K.drags = [];
    shelf.replaceChildren();
    mat.replaceChildren();
    task.boxes.forEach((count, index) => {
      const card = K.el('button', 'box-card', '', shelf);
      card.type = 'button';
      card.id = `seed-box-${count}`;
      card.dataset.count = count;
      card.dataset.kind = index;
      card.setAttribute('aria-label', `有${count}块的饼盒`);
      seeds(K.el('span', 'biscuit-grid', '', card), count);
      card.onclick = () => { if (!demo && !accepted) place(card, card.parentElement === shelf ? mat : shelf); };
      K.drag(card, {enabled: () => !demo && !accepted && !isExact(), targets: () => [card.parentElement === shelf ? mat : shelf], onDrop: (_, target) => { if (target) place(card, target); }});
      cards.push(card);
    });
    render();
    K.say('看左边需要多少，再从架上挑两盒。');
  }

  function reset() {
    clearTimeout(timer);
    demo = false;
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    load(tasks[0]);
  }

  check.onclick = submit;
  K.onStart = reset;
  K.onState = state => {
    if (state.demo) {
      clearTimeout(timer);
      K.$('#finish')?.classList.add('gone');
      demo = true;
      round = 0;
      load(demonstration);
      K.say('先看老师选两盒。');
    }
    if (demo && state.short) {
      place(cards[2], shelf);
      place(cards[0], mat);
      place(cards[1], mat);
    }
    if (demo && state.match) {
      place(cards[1], shelf);
      place(cards[0], mat);
      place(cards[2], mat);
    }
    if (state.play) reset();
  };
  load(tasks[0]);
})();
