(() => {
  const cases = [
    { total: 2, visible: 1, options: [2, 1, 3] },
    { total: 3, visible: 1, options: [2, 3, 1] },
    { total: 4, visible: 3, options: [2, 3, 1] },
    { total: 5, visible: 2, options: [1, 3, 2] }
  ];
  const totalPanel = K.$('#cover-total');
  const openPanel = K.$('#cover-open');
  const lidPanel = K.$('#cover-lid');
  const closedArt = K.$('#cover-closed-art');
  const openArt = K.$('#cover-open-art');
  const next = K.$('#cover-next');
  const choices = K.$$('#cover-choices button');
  let round = 0;
  let revealed = false;
  let demonstration = false;
  let mistakes = 0;

  function dot(alternate = false) {
    const item = document.createElement('i');
    item.className = alternate ? 'cover-dot alternate' : 'cover-dot';
    item.setAttribute('aria-hidden', 'true');
    return item;
  }

  function countDots(count, alternate = false) {
    return Array.from({ length: count }, () => dot(alternate));
  }

  function draw() {
    const { total, visible, options } = cases[round];
    totalPanel.replaceChildren(...Array.from({ length: total }, (_, index) => {
      const slot = document.createElement('span');
      slot.className = 'cover-slot';
      if (index < visible || revealed) slot.append(dot(round === 2 && index >= visible));
      return slot;
    }));
    totalPanel.setAttribute('aria-label', `总数有${total}格，和可见的${visible}个一一对应`);
    openPanel.replaceChildren(...countDots(visible));
    closedArt.hidden = revealed;
    openArt.hidden = !revealed;
    lidPanel.classList.toggle('revealed', revealed);
    lidPanel.replaceChildren(...countDots(revealed ? total - visible : 0, round === 2));
    lidPanel.setAttribute('aria-label', revealed ? `打开后看到${total - visible}个圆片` : '盖住的一组');
    choices.forEach((button, index) => {
      button.replaceChildren(...countDots(options[index], round === 2));
      button.setAttribute('aria-label', `${options[index]}个圆片`);
      button.disabled = revealed || demonstration;
    });
    next.hidden = !revealed || demonstration;
  }

  function reset() {
    round = 0;
    revealed = false;
    demonstration = false;
    mistakes = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(4, 0);
    draw();
    K.say('先看总共有几格，再选出盖住的那一组。');
  }

  choices.forEach((button, index) => button.addEventListener('click', () => {
    if (revealed || demonstration) return;
    const { total, visible, options } = cases[round];
    if (options[index] !== total - visible) {
      mistakes += 1;
      K.sfx.no();
      K.shake(button);
      if (mistakes > 1) K.highlight('#cover-total');
      K.say(mistakes === 1 ? '先看看有几个位置已经对上了。' : '再数没有配上圆片的空格。', 'no');
      return;
    }
    revealed = true;
    draw();
    K.star(1);
    K.levels(4, round + 1);
    K.sfx.ok();
    K.say('打开看看，两边合起来正好填满参照格。', 'ok');
  }));
  next.addEventListener('click', () => {
    if (!revealed || demonstration) return;
    if (round === cases.length - 1) {
      K.finish({ title: '盖住的部分都找到了', sub: '先看总数，再把两边合起来检查。', again: reset });
      return;
    }
    round += 1;
    revealed = false;
    mistakes = 0;
    draw();
    K.say('这一组先看清总数和露出来的那一边。');
  });

  K.hud({ icon: '◆', title: '找出盖住的一组', levels: 4 });
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) return reset();
    if (state.demo === true && cases[state.round]) {
      demonstration = true;
      round = state.round;
      revealed = state.reveal === true;
      draw();
      K.say('老师示范，先配对，再看还空几格。');
    }
  };
  reset();
  K.ready({ emoji: '◆', title: '找出盖住的一组', sub: '找出另一边，打开看看。' });
})();
