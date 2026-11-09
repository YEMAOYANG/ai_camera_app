(function () {
  'use strict';

  const order = ['come', 'touch', 'return'];
  const initial = () => ({ step: 0, misses: 0, finished: false });

  function next(state, choice) {
    if (choice === 'reset') return initial();
    if (state.finished || !order.includes(choice)) return state;
    if (choice !== order[state.step]) return { ...state, misses: state.misses + 1 };
    const step = state.step + 1;
    return { ...state, step, finished: step === order.length };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { initial, next };
  if (typeof document === 'undefined') return;

  const shore = K.$('#shore-view');
  const controls = Object.fromEntries(order.map(choice => [choice, K.$('#' + choice + '-choice')]));
  let state = initial();
  let demoTimer;
  let finishTimer;
  K.hud({ icon: '', title: '浪花来回', levels: 3 });
  K.owl();
  K.ready({ img: '__IMG:waves-cover__', title: '浪花来回', sub: '听老师，再点画面' });

  function render() {
    shore.dataset.step = state.step;
    for (const [index, name] of order.entries()) {
      controls[name].disabled = index < state.step;
      controls[name].classList.toggle('done', index < state.step);
    }
    K.levels(3, state.step);
  }

  function reset() {
    clearTimeout(demoTimer);
    clearTimeout(finishTimer);
    state = initial();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.say('看浪花的位置，选接下来发生的画面。');
    render();
  }

  const feedback = ['白泡沫向岸边靠近。', '浪花轻轻碰到脚边。', '水退回海里了。'];
  function choose(choice) {
    clearTimeout(demoTimer);
    const before = state;
    state = next(state, choice);
    render();
    if (state.misses > before.misses) {
      K.sfx.no();
      K.shake(shore);
      K.say(state.misses === 1 ? '看看白泡沫现在在哪里。' : '再留意浪花离脚边有多远。', 'no');
      return;
    }
    if (state.step === before.step) return;
    K.star(1, controls[choice]);
    K.say(feedback[state.step - 1], 'ok');
    if (state.finished) finishTimer = setTimeout(() => {
      K.finish({ title: '看见浪花来回', sub: '把三幅画的先后说给家人听。', again: reset });
    }, 560);
  }

  for (const [choice, button] of Object.entries(controls)) button.addEventListener('click', () => choose(choice));
  K.onStart = reset;
  K.onState = value => {
    const stage = order.indexOf(value.demo);
    if (stage < 0) return;
    clearTimeout(demoTimer);
    shore.dataset.step = stage + 1;
    K.say('老师示范：' + feedback[stage]);
    demoTimer = setTimeout(render, 2200);
  };
  K.$$('.shore-view img').forEach(image => image.addEventListener('error', () => {
    K.$('#shore-picture-error').classList.remove('hide');
  }));
})();
