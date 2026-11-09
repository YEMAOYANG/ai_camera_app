(() => {
  const assets = {
    letter: { name: '信封', url: '__IMG:letter__' },
    parcel: { name: '包裹', url: '__IMG:parcel__' },
    stamp: { name: '邮票', url: '__IMG:stamp__' },
  };
  const rounds = [
    { key: 'parcel', count: 1, options: [2, 1, 3] },
    { key: 'stamp', count: 4, options: [4, 5, 3] },
    { key: 'letter', count: 5, options: [3, 4, 5] },
  ];
  const items = K.$('#match-items');
  const bridge = K.$('#match-bridge');
  const choices = K.$('#match-choices');
  let task = rounds[0];
  let level = 0;
  let placed = false;
  let teaching = false;
  let misses = 0;
  let timer;

  K.hud({ icon: '●', title: '同样多，送到一起', levels: rounds.length });
  K.owl();
  K.ready({ emoji: '●●', title: '同样多，送到一起', sub: '选一张和实物同样多的卡片' });

  function render() {
    items.replaceChildren();
    bridge.replaceChildren();
    choices.replaceChildren();
    const asset = assets[task.key];
    for (let i = 0; i < task.count; i++) {
      const tile = K.el('div', 'match-unit', '', items);
      const img = K.el('img', '', '', tile);
      img.alt = asset.name;
      img.addEventListener('error', () => { tile.textContent = asset.name; }, { once: true });
      img.src = asset.url;
      const dotSlot = K.el('span', 'match-dot-slot', '', bridge);
      if (placed) K.el('i', 'match-dot', '', dotSlot);
    }
    bridge.setAttribute('aria-label', placed ? task.count + '颗已配对的点' : '配对后在这里显示点');
    for (const value of task.options) {
      const card = K.el('button', 'match-choice' + (placed && value === task.count ? ' chosen' : ''), '', choices);
      card.type = 'button';
      card.id = 'match-card-' + value;
      card.disabled = teaching || placed;
      card.setAttribute('aria-label', '数字' + value + '，' + value + '颗点');
      K.el('strong', '', String(value), card);
      const dotRow = K.el('span', 'dot-row', '', card);
      for (let i = 0; i < value; i++) K.el('i', 'match-dot', '', dotRow);
      card.addEventListener('click', () => choose(value));
    }
    K.levels(rounds.length, level);
  }

  function choose(value) {
    if (teaching || placed) return;
    if (value !== task.count) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '点着实物再数一遍，最后数到几？' : '让每件配一颗点，看看有没有剩下。', 'no');
      if (misses >= 3) K.highlight('#match-card-' + task.count);
      return;
    }
    placed = true;
    render();
    K.sfx.ok();
    K.star(1, bridge);
    K.say('每件都有一颗点相配，两个数量一样。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === rounds.length) K.finish({ title: '数量卡送到了', sub: '同样多的物品，用同一个数来记。', again: reset });
      else load();
    }, 950);
  }

  function load() {
    task = rounds[level];
    placed = false;
    teaching = false;
    misses = 0;
    render();
    K.say('数完左边，再找一张同样多的卡片。');
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
    task = { key: state.demo === 'transfer' ? 'parcel' : 'letter', count: 2, options: [3, 2, 1] };
    placed = state.demo !== 'objects';
    render();
    K.say(state.demo === 'transfer' ? '两个包裹也能配两颗点。' : '把两只信封和两颗点逐一对应。');
  };
  load();
})();
