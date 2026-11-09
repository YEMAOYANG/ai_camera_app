(() => {
  const frame = K.$('#ten-frame');
  const loose = K.$('#loose-pieces');
  const equation = K.$('#count-equation');
  const choices = K.$('#count-choices');
  let addend, moved, demo, misses, done, finishTimer;
  K.hud({ title: '先把十格放满', icon: '9', levels: 2 });
  K.owl();

  function render() {
    frame.replaceChildren();
    for (let i = 0; i < 10; i++) {
      const full = i < 9 || moved;
      K.el('div', full ? 'slot full' : 'slot',
        full ? '<span class="disc' + (i === 9 ? ' added' : '') + '"></span>' : '', frame);
    }
    loose.replaceChildren();
    for (let i = 0; i < addend - Number(moved); i++) {
      const button = K.el('button', 'piece', '<span class="disc"></span>', loose);
      button.type = 'button';
      button.setAttribute('aria-label', '移这一枚纸片到十格盘');
      button.disabled = demo || moved;
      button.onclick = () => {
        moved = true;
        K.levels(2, 1);
        K.sfx.drop();
        render();
        K.say('十格满了。把整盘和盘外的纸片一起算。', 'ok');
      };
    }
    equation.textContent = moved ? '10 ＋ ' + (addend - 1) + ' ＝ ' + (demo ? 9 + addend : '？') : '9 ＋ ' + addend;
    choices.hidden = !moved || demo;
  }

  [15, 16, 17].forEach(value => {
    const option = K.el('button', 'btn ghost', String(value), choices);
    option.type = 'button';
    option.onclick = () => {
      if (done) return;
      if (value !== 9 + addend) {
        misses++;
        K.shake(option);
        K.sfx.no();
        K.say(misses === 1 ? '盘里已经是十。只数盘外还剩几枚。' : '从十往后数，盘外每一枚数一次。', 'no');
        if (misses > 1) K.highlight('#loose-pieces');
        return;
      }
      done = true;
      equation.textContent = '10 ＋ ' + (addend - 1) + ' ＝ ' + value;
      K.$$('button', choices).forEach(button => { button.disabled = true; });
      K.levels(2, 2);
      K.star(1, option);
      K.sfx.ok();
      K.say('凑成十，再加盘外剩下的。', 'ok');
      finishTimer = setTimeout(() => K.finish({ title: '纸片配齐了', sub: '先凑十，再加剩下的', again: reset }), 1000);
    };
  });

  function reset() {
    clearTimeout(finishTimer);
    addend = 7;
    moved = demo = done = false;
    misses = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$$('button', choices).forEach(button => { button.disabled = false; });
    K.levels(2, 0);
    render();
    K.say('点盘外一枚纸片，把十格放满。');
  }

  K.onStart = reset;
  K.onState = state => {
    if (state.resetTask) reset();
    if (state.demoMoved === true || state.demoMoved === false) {
      demo = true;
      addend = 6;
      moved = state.demoMoved;
      render();
    }
  };
  reset();
  K.ready({ title: '先把十格放满', sub: '纸片怎样摆更好数', emoji: '10' });
})();
