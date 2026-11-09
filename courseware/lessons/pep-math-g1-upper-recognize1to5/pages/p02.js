(() => {
  const assets = {
    letter: { name: '信封', url: '__IMG:letter__' },
    parcel: { name: '包裹', url: '__IMG:parcel__' },
    stamp: { name: '邮票', url: '__IMG:stamp__' },
    clip: { name: '夹子', url: '__IMG:clip__' },
  };
  const positions = [[62, 12], [273, 28], [493, 11], [714, 25], [938, 16], [165, 150], [383, 151], [607, 150], [824, 152]];
  const demo = { target: 'clip', items: ['clip', 'letter', 'clip', 'parcel', 'stamp', 'clip', 'letter', 'clip'] };
  const rounds = [
    { target: 'letter', items: ['letter', 'clip', 'parcel', 'letter', 'stamp', 'clip', 'letter', 'parcel'] },
    { target: 'stamp', items: ['stamp', 'parcel', 'stamp', 'stamp', 'clip', 'stamp', 'letter', 'stamp', 'letter'] },
    { target: 'parcel', items: ['clip', 'letter', 'parcel', 'stamp', 'stamp', 'clip', 'letter', 'parcel'] },
  ];
  const desk = K.$('#count-desk');
  const track = K.$('#count-track');
  const check = K.$('#count-check');
  let level = 0;
  let task = rounds[0];
  let counted = new Set();
  let teaching = false;
  let busy = false;
  let misses = 0;
  let timer;

  K.hud({ icon: '●', title: '点一件，记一次', levels: rounds.length });
  K.owl();
  K.ready({ emoji: '1–5', title: '点一件，记一次', sub: '认清图样，每件只点一次' });

  function image(key, parent) {
    const item = assets[key];
    const card = K.el('span', 'count-picture', '', parent);
    const img = K.el('img', '', '', card);
    img.alt = item.name;
    img.addEventListener('error', () => { card.textContent = item.name; }, { once: true });
    img.src = item.url;
  }

  function total() { return task.items.filter(key => key === task.target).length; }

  function render() {
    const sample = K.$('#count-sample');
    sample.replaceChildren();
    image(task.target, sample);
    desk.replaceChildren();
    task.items.forEach((key, index) => {
      const button = K.el('button', 'count-item', '', desk);
      button.type = 'button';
      button.id = 'count-item-' + index;
      button.style.left = positions[index][0] + 'px';
      button.style.top = positions[index][1] + 'px';
      button.dataset.counted = String(counted.has(index));
      button.disabled = teaching || busy || counted.has(index);
      button.setAttribute('aria-label', assets[key].name + (counted.has(index) ? '，已数过' : ''));
      image(key, button);
      button.addEventListener('click', () => choose(index));
    });
    track.replaceChildren();
    for (let i = 0; i < 5; i++) K.el('i', 'count-dot' + (i < counted.size ? ' filled' : ''), '', track);
    K.el('b', 'count-number', counted.size === total() ? String(total()) : '…', track);
    check.disabled = teaching || busy;
    K.levels(rounds.length, level);
  }

  function hint(first) {
    misses++;
    K.sfx.no();
    K.say(misses === 1 ? first : '对照上面的图样，找没亮过的同类物品。', 'no');
    if (misses >= 3) {
      const index = task.items.findIndex((key, i) => key === task.target && !counted.has(i));
      if (index >= 0) K.highlight('#count-item-' + index);
    }
  }

  function choose(index) {
    if (teaching || busy || counted.has(index)) return;
    if (task.items[index] !== task.target) {
      hint('把这件和上面的图样比一比。');
      return;
    }
    counted.add(index);
    render();
    K.sfx.tick(counted.size);
    K.say(counted.size === total() ? '同类物品都点过了，看看最后的数。' : '记好这一件，再找下一件。');
  }

  function load() {
    task = rounds[level];
    counted = new Set();
    teaching = false;
    busy = false;
    misses = 0;
    render();
    K.say('照着图样找，每件只点一次。');
  }

  function reset() {
    clearTimeout(timer);
    level = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    load();
  }

  check.addEventListener('click', () => {
    if (teaching || busy) return;
    if (counted.size !== total()) {
      hint('桌上还有同类物品没做记号吗？');
      return;
    }
    busy = true;
    render();
    K.sfx.ok();
    K.star(1, track);
    K.say('每件数一次，最后数到几就是几。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === rounds.length) K.finish({ title: '数清楚啦', sub: '一件配一颗点，最后的数是总个数。', again: reset });
      else load();
    }, 850);
  });

  K.onStart = reset;
  K.onState = state => {
    if (state.play) { reset(); return; }
    if (!state.demo) return;
    clearTimeout(timer);
    task = demo;
    teaching = true;
    counted = new Set(state.demo === 'all' ? [0, 2, 5, 7] : state.demo === 'first' ? [0] : []);
    render();
    K.say(state.demo === 'all' ? '点完四只夹子，最后的数是四。' : '示范先找夹子，每件点一次。');
  };
  load();
})();
