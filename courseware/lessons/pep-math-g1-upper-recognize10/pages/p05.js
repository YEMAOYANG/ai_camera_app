(() => {
  const row = K.$('#p05-pots');
  const pots = [];
  let fromLeft = false;
  let misses = 0;
  let demo = false;
  let done = false;
  let timer;
  let counting;
  K.hud({title:'哪盆排在第十',icon:'10',levels:1});
  K.owl();

  function render(selected = -1) {
    K.$('#p05-left').hidden = !fromLeft;
    K.$('#p05-right').hidden = fromLeft;
    pots.forEach((pot, i) => {
      pot.disabled = demo || done;
      pot.classList.toggle('chosen', i === selected);
    });
  }

  function choose(index, pot) {
    if (done || demo) return;
    if (index !== (fromLeft ? pots.length - 1 : 0)) {
      misses++;
      K.sfx.no();
      K.shake(pot);
      K.say(misses === 1 ? '先找箭头的尾巴，从那边第一盆开始数。' : '先数紧靠箭头尾巴的那盆，再顺着箭头逐盆数。', 'no');
      if (misses > 1) K.highlight(fromLeft ? '#p05-left' : '#p05-right');
      return;
    }
    done = true;
    render(index);
    K.star(1, pot);
    K.levels(1, 1);
    K.sfx.ok();
    K.say('圈出的是第十盆，整行还是十盆。', 'ok');
    timer = setTimeout(() => K.finish({title:'第十盆找到了',sub:'总数没变，位置跟着起点变',again:reset}), 1000);
  }
  for (let i = 0; i < 10; i++) {
    const pot = K.el('button', 'p05-pot', '<img src="__IMG:seedling__" alt=""><i data-semantic-diagram="一盆对应一个点"></i>', row);
    pot.id = 'p05-pot-' + i;
    pot.setAttribute('aria-label', '从左边看的第' + (i + 1) + '盆');
    K.$('img', pot).addEventListener('error', () => pot.classList.add('failed'));
    pot.onclick = () => choose(i, pot);
    pots.push(pot);
  }

  function reset() {
    clearTimeout(timer);
    clearInterval(counting);
    misses = 0;
    fromLeft = false;
    demo = false;
    done = false;
    render();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(1, 0);
    K.say('从右边第一盆开始数，点第十盆。');
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.resetTask) reset();
    if (state.demoSide) {
      demo = true;
      fromLeft = state.demoSide === 'left';
      render();
      K.say(fromLeft ? '老师从左边第一盆开始数。' : '老师从右边第一盆开始数。');
      clearInterval(counting);
      let index = fromLeft ? 0 : pots.length - 1;
      counting = setInterval(() => {
        render(index);
        index += fromLeft ? 1 : -1;
        if (index < 0 || index >= pots.length) clearInterval(counting);
      }, 430);
    }
    if (state.demoOrdinal) {
      clearInterval(counting);
      render(fromLeft ? pots.length - 1 : 0);
      K.say('这一盆排在第十，整行有十盆。');
    }
  };
  reset();
  K.ready({title:'哪盆排在第十',sub:'沿箭头数，选一盆',emoji:'10'});
})();
