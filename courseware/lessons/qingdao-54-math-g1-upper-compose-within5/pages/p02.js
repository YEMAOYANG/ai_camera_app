(() => {
  const total = 5;
  const choices = [K.$('#seed-choice-a'), K.$('#seed-choice-b')];
  const leftPile = K.$('#seed-left');
  const rightPile = K.$('#seed-right');
  const history = K.$('#seed-history');
  let left = 1;
  let mistakes = 0;
  let demonstration = false;

  function tokens(element, count) {
    element.replaceChildren(...Array.from({ length: count }, () => {
      const token = document.createElement('i');
      token.className = 'seed-token';
      token.setAttribute('aria-hidden', 'true');
      return token;
    }));
  }

  function draw() {
    tokens(leftPile, left);
    tokens(rightPile, total - left);
    leftPile.setAttribute('aria-label', `左边${left}粒`);
    rightPile.setAttribute('aria-label', `右边${total - left}粒`);
    history.replaceChildren(...[1, 2, 3, 4].map(count => {
      const record = document.createElement('div');
      record.className = 'seed-record' + (count > left ? ' unseen' : '');
      const leftGroup = document.createElement('span');
      const rightGroup = document.createElement('span');
      tokens(leftGroup, count);
      tokens(rightGroup, total - count);
      record.append(leftGroup, rightGroup);
      return record;
    }));
    for (const [index, button] of choices.entries()) {
      const count = index === left % 2 ? 1 : 2;
      tokens(button, count);
      button.dataset.count = String(count);
      button.setAttribute('aria-label', `移${count}粒`);
      button.disabled = demonstration || left === 4;
    }
  }

  function reset() {
    demonstration = false;
    left = 1;
    mistakes = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(3, 0);
    draw();
    K.say('每次只从右边移一粒，看看两边怎样变。');
  }

  function move(button) {
    if (demonstration || left === 4) return;
    if (button.dataset.count !== '1') {
      mistakes += 1;
      K.shake(button);
      K.sfx.no();
      if (mistakes > 1) K.highlight('#seed-direction');
      K.say(mistakes === 1 ? '先数一数卡片上的种子，再想要移几粒。' : '一粒刚离开右边，就到左边。试着只移这一粒。', 'no');
      return;
    }
    left += 1;
    mistakes = 0;
    draw();
    K.star(1);
    K.levels(3, left - 1);
    K.sfx.ok();
    K.say('左边多一粒，右边少一粒，合起来还是五粒。', 'ok');
    if (left === 4) K.finish({ title: '找齐四种摆法', sub: '两边都有种子，总数一直是五。', again: reset });
  }

  choices.forEach(button => button.addEventListener('click', () => move(button)));
  K.hud({ icon: '◆', title: '每次移一粒', levels: 3 });
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) return reset();
    if (state.demo === true && [1, 2, 3, 4].includes(state.left)) {
      demonstration = true;
      left = state.left;
      draw();
      K.say('老师示范，沿着箭头把一粒种子向左移。');
    }
  };
  draw();
  K.ready({ emoji: '◆', title: '每次移一粒', sub: '看看两边怎样变。' });
})();
