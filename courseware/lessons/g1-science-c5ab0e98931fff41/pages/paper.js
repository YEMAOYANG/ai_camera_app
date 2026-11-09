(function () {
  const actions = ['fold', 'shaft', 'band', 'slow', 'fast'];
  const actionButtons = K.$$('.paper-controls button');
  const rotor = K.$('#paper-rotor');
  const labels = [
    '纸片折出了折痕。',
    '小杆穿过纸片中间。',
    '胶带固定好啦，可以试转。',
    '慢转时，纸片绕着中间转。',
    '快转时，纸片也绕着中间转。',
  ];
  let phase = 0;
  let misses = 0;
  let demo = false;
  let busy = false;
  let timer;

  K.hud({ icon: '◉', title: '做会转的小纸片', levels: actions.length });
  K.owl();

  function render() {
    K.$('#paper-flat').classList.toggle('hide', phase > 0);
    K.$('#paper-folded').classList.toggle('hide', phase < 1);
    K.$('#paper-shaft').classList.toggle('hide', phase < 2);
    K.$('#paper-band').classList.toggle('hide', phase < 3);
    K.$('#paper-build-controls').classList.toggle('hide', phase >= 3);
    K.$('#paper-spin-controls').classList.toggle('hide', phase < 3);
    actionButtons.forEach((button, index) => {
      button.classList.toggle('assembled', index < phase);
    });
    K.levels(actions.length, phase);
  }

  function turn(speed) {
    rotor.classList.remove('slow-turn', 'fast-turn');
    if (speed) {
      void rotor.getBoundingClientRect();
      rotor.classList.add(speed + '-turn');
    }
  }

  function reset() {
    clearTimeout(timer);
    phase = 0;
    misses = 0;
    demo = false;
    busy = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    turn(null);
    render();
    K.say('先折、再穿、最后用胶带固定。');
  }

  function choose(button) {
    if (!K.started || demo || busy || phase === actions.length) return;
    const action = button.dataset.action;
    if (action !== actions[phase]) {
      misses += 1;
      K.shake(button);
      K.sfx.no();
      if (misses === 1) {
        K.say('回想老师刚才的顺序，再试一下。', 'no');
      } else if (misses === 2) {
        K.say('看看现在的纸片，还能做什么？', 'no');
        K.highlight('#paper-diagram');
      } else {
        K.say('老师提示这个动作，再试一次。', 'no');
        const next = actionButtons.find(item => item.dataset.action === actions[phase]);
        K.highlight('#' + next.id);
        misses = 0;
      }
      return;
    }

    K.say(labels[phase], 'ok');
    phase += 1;
    misses = 0;
    K.sfx.ok();
    K.star(1, button);
    render();
    if (action === 'slow' || action === 'fast') {
      turn(action);
      busy = true;
      timer = setTimeout(() => {
        busy = false;
        if (phase === actions.length) {
          K.finish({
            title: '小纸片做完啦',
            sub: '试转时，看纸片绕着中间动。',
            again: reset,
          });
        }
      }, 1300);
    }
  }

  actionButtons.forEach(button => button.addEventListener('click', () => choose(button)));
  K.$('#paper-materials img').addEventListener('error', () => {
    K.say('材料图片没有加载好，请重新打开这一页。', 'no');
  });
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) {
      reset();
      return;
    }
    if (state.demo === true && Number.isInteger(state.phase)) {
      clearTimeout(timer);
      demo = true;
      phase = Math.max(0, Math.min(4, state.phase));
      render();
      turn(phase === 4 ? 'slow' : null);
    }
  };
  render();
  K.ready({ emoji: '', title: '做会转的小纸片', sub: '按顺序制作，完成后试转' });
})();
