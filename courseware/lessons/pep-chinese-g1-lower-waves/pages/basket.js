(function () {
  'use strict';

  const gifts = ['shell', 'shrimp'];
  const initial = () => ({ placed: [], misses: 0, finished: false });

  function next(state, choice) {
    if (choice === 'reset') return initial();
    if (state.finished) return state;
    if (choice === 'extra') {
      if (state.placed.length === gifts.length) return { ...state, finished: true };
      return { ...state, misses: state.misses + 1 };
    }
    if (!gifts.includes(choice) || state.placed.includes(choice)) return state;
    return { ...state, placed: [...state.placed, choice] };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { initial, next };
  if (typeof document === 'undefined') return;

  const basket = K.$('#basket-view');
  const slots = [K.$('#basket-slot-one'), K.$('#basket-slot-two')];
  const controls = { shell: K.$('#choose-shell'), shrimp: K.$('#choose-shrimp'), extra: K.$('#check-extra') };
  const art = { shell: { src: '__IMG:story-shell__', alt: '白贝壳' }, shrimp: { src: '__IMG:story-shrimp__', alt: '青色小虾' } };
  let state = initial();
  let demoTimer;
  K.hud({ icon: '', title: '小篮装礼物', levels: 3 });
  K.owl();
  K.ready({ img: '__IMG:story-basket__', title: '小篮装礼物', sub: '看图放礼物，看看还剩多少地方' });

  function paintBasket(placed) {
    basket.classList.toggle('full', placed.length === slots.length);
    slots.forEach((slot, index) => {
      const item = art[placed[index]];
      const image = slot.querySelector('img');
      slot.classList.toggle('filled', Boolean(item));
      if (item) {
        image.src = item.src;
        image.alt = item.alt;
      } else {
        image.removeAttribute('src');
        image.alt = '';
      }
    });
  }

  function render() {
    paintBasket(state.placed);
    for (const gift of gifts) controls[gift].disabled = state.placed.includes(gift);
    K.levels(3, state.placed.length + Number(state.finished));
  }

  function reset() {
    clearTimeout(demoTimer);
    state = initial();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    render();
    K.say('先看空篮，再把故事里的礼物放进去。');
  }

  function choose(choice) {
    clearTimeout(demoTimer);
    const before = state;
    state = next(state, choice);
    render();
    if (state.misses > before.misses) {
      K.sfx.no();
      K.shake(basket);
      K.say(state.misses === 1 ? '再看篮子里，还有什么没放？' : '看看篮边的两样故事礼物。', 'no');
      return;
    }
    if (state.placed.length > before.placed.length) {
      K.star(1, slots[state.placed.length - 1]);
      K.say(state.placed.length === 1 ? '放进去一件，还剩一个空位。' : '两样礼物都放好了，再看看有没有空位。', 'ok');
    }
    if (state.finished && !before.finished) {
      K.star(1, controls.extra);
      K.say('这个篮子没有空位，新贝壳装不下。', 'ok');
      K.finish({ title: '看懂装不下', sub: '没有地方再放，贝壳留在篮外。', again: reset });
    }
  }

  for (const [choice, button] of Object.entries(controls)) button.addEventListener('click', () => choose(choice));
  K.onStart = reset;
  K.onState = value => {
    const examples = { empty: [], one: ['shrimp'], full: ['shrimp', 'shell'] };
    const placed = examples[value.demo];
    if (!Array.isArray(placed)) return;
    clearTimeout(demoTimer);
    paintBasket(placed);
    K.say(['老师示范：空篮能放礼物。', '老师示范：放入一件，空位变少。', '老师示范：篮里已经没有空位。'][placed.length]);
    demoTimer = setTimeout(render, 2200);
  };
  K.$$('.basket-activity img').forEach(image => image.addEventListener('error', () => {
    K.$('#basket-picture-error').classList.remove('hide');
  }));
})();
