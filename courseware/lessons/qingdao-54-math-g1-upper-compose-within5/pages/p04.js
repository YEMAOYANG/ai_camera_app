(() => {
  const bank = K.$$('.loose-disc');
  const trays = [K.$('#disc-left'), K.$('#disc-right')];
  const cards = K.$$('#disc-target span');
  const check = K.$('#disc-check');
  let locations = [];
  let round = 0;
  let selected = -1;
  let mistakes = 0;
  let demonstration = false;

  function fill(container, count) {
    container.replaceChildren(...Array.from({ length: count }, () => {
      const disc = document.createElement('i');
      disc.className = 'disc-unit';
      disc.setAttribute('aria-hidden', 'true');
      return disc;
    }));
  }

  function draw() {
    trays.forEach((tray, index) => fill(tray, locations.filter(place => place === index).length));
    fill(cards[0], round + 1);
    fill(cards[1], 3 - round);
    bank.forEach((button, index) => {
      button.classList.toggle('placed', locations[index] !== -1);
      button.classList.toggle('selected', selected === index);
      button.disabled = demonstration;
    });
    trays.forEach(tray => { tray.disabled = demonstration; });
    check.disabled = demonstration || locations.includes(-1);
  }

  function clear() {
    locations = [-1, -1, -1, -1];
    selected = -1;
    mistakes = 0;
    draw();
    K.say('照着两格里的圆贴图，把四枚都放进去。');
  }

  function reset() {
    demonstration = false;
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(3, 0);
    clear();
  }

  function choose(index) {
    if (demonstration || locations[index] !== -1) return;
    selected = index;
    draw();
    K.sfx.pick();
  }

  function place(index, tray) {
    if (demonstration || index < 0 || locations[index] !== -1 || tray < 0) return;
    const target = tray === 0 ? round + 1 : 3 - round;
    if (locations.filter(place => place === tray).length === target) {
      mistakes += 1;
      K.sfx.no();
      K.shake(trays[tray]);
      if (mistakes > 1) K.highlight('#disc-target');
      K.say(mistakes === 1 ? '先对一对，这一边跟图上一样多了吗？' : '已经对上的圆贴留在原处，再看看另一边。', 'no');
      return;
    }
    locations[index] = tray;
    selected = -1;
    draw();
    K.sfx.drop();
    K.say(locations.includes(-1) ? '这一枚对上了，再摆下一枚。' : '四枚都摆好了，按对一对。', 'ok');
  }

  bank.forEach((button, index) => {
    button.addEventListener('click', () => choose(index));
    K.drag(button, {
      enabled: () => !demonstration && locations[index] === -1,
      targets: () => trays,
      onTap: () => choose(index),
      onDrop: (_item, tray) => place(index, trays.indexOf(tray))
    });
  });
  trays.forEach((tray, index) => tray.addEventListener('click', () => place(selected, index)));
  K.$('#disc-reset').addEventListener('click', () => { if (!demonstration) clear(); });
  check.addEventListener('click', () => {
    if (demonstration || locations.includes(-1)) return;
    K.star(1);
    K.levels(3, round + 1);
    K.sfx.ok();
    if (round === 2) {
      K.finish({ title: '四的三种摆法找齐了', sub: '左右各两枚的摆法只记一次。', again: reset });
    } else {
      round += 1;
      clear();
      K.say('这一种对上了。再照下一张图摆一摆。', 'ok');
    }
  });

  K.hud({ icon: '◆', title: '四枚圆贴的三种分法', levels: 3 });
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) return reset();
    if (state.demo === true && Array.isArray(state.locations) && state.locations.length === 4 && [0, 1, 2].includes(state.round)) {
      demonstration = true;
      round = state.round;
      locations = state.locations.slice();
      draw();
      K.say('老师示范，照着两格图摆一摆。');
    }
  };
  reset();
  K.ready({ emoji: '◆', title: '四枚圆贴的三种分法', sub: '拖一拖，或先点圆贴再点托盘。' });
})();
