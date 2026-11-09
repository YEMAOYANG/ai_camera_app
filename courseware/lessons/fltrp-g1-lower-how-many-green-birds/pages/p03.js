(function () {
  const flockSize = 12;

  function makeCount() {
    const counted = new Set();
    return {
      mark(index) {
        if (!Number.isInteger(index) || index < 0 || index >= flockSize || counted.has(index)) return 0;
        counted.add(index);
        return counted.size;
      },
      reset() { counted.clear(); },
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { makeCount };
  if (typeof document === 'undefined') return;

  const model = makeCount();
  const perches = K.$('#perches');
  let demo = false;
  let complete = false;
  let finishTimer;
  let repeatAttempts = 0;
  K.hud({ icon: '', title: '给小鸟盖计数戳', levels: 1 });
  K.owl();

  function showFailure() { K.$('#picture-failure').classList.remove('hide'); }

  const birds = Array.from({ length: flockSize }, (_, index) => {
    const button = K.el('button', 'perched-bird', null, perches);
    button.type = 'button';
    button.id = 'perched-bird-' + (index + 1);
    button.setAttribute('aria-label', '第' + (index + 1) + '只蓝鸟');
    const picture = K.el('img', '', null, button);
    picture.alt = '';
    picture.addEventListener('error', showFailure);
    picture.src = '__IMG:bird-blue__';
    const stamp = K.el('span', 'bird-stamp', null, button);
    stamp.setAttribute('aria-hidden', 'true');
    button.addEventListener('click', () => mark(index));
    return { button, stamp };
  });

  function countFace(count) {
    K.$('#bird-count').textContent = String(count);
    K.$('#count-word').textContent = count === 11 ? 'eleven' : count === 12 ? 'twelve' : '';
  }

  function stampBird(index, order) {
    const bird = birds[index];
    bird.button.classList.toggle('counted', order > 0);
    bird.button.setAttribute('aria-pressed', String(order > 0));
    bird.stamp.textContent = order ? String(order) : '';
  }

  function mark(index) {
    if (demo || complete) return;
    const count = model.mark(index);
    if (!count) {
      repeatAttempts += 1;
      K.shake(birds[index].button);
      K.sfx.no();
      if (repeatAttempts === 2) K.highlight('#perches');
      K.say(repeatAttempts === 1 ? '有小印章的鸟已经数过。' : '看一看，接着点还没有印章的鸟。', 'no');
      return;
    }
    stampBird(index, count);
    countFace(count);
    K.sfx.tick(count);
    if (count !== flockSize) return;
    complete = true;
    K.levels(1, 1);
    K.star(1, birds[index].button);
    K.say('全都只数了一次。', 'ok');
    finishTimer = setTimeout(() => K.finish({ title: '十二只都数到了', sub: 'Twelve birds.', again: reset }), 1100);
  }

  function reset() {
    clearTimeout(finishTimer);
    complete = demo = false;
    repeatAttempts = 0;
    model.reset();
    birds.forEach((_, index) => stampBird(index, 0));
    countFace(0);
    K.levels(1, 0);
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$('#tip').style.display = 'none';
    K.say('每只小鸟只盖一次章。');
  }

  K.onState = state => {
    if (!Object.hasOwn(state, 'demoCount')) return;
    if (!state.demoCount) {
      reset();
      return;
    }
    demo = true;
    birds.forEach((_, index) => stampBird(index, index < state.demoCount ? index + 1 : 0));
    countFace(state.demoCount);
  };

  K.$('#reload-birds').addEventListener('click', () => {
    K.$('#picture-failure').classList.add('hide');
    K.$$('#count-board img').forEach(img => { img.src = img.src; });
  });
  reset();
  K.onStart = reset;
  K.ready({ title: '给小鸟盖计数戳', sub: '点一只，数一次', emoji: '' });
})();
