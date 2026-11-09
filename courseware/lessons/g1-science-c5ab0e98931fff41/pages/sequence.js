(function () {
  K.hud({ icon: '◉', title: '按步骤做实验', levels: 3 });
  K.owl();

  const order = ['spoon', 'chopsticks', 'tongs'];
  const view = K.$('#seq-cup-image');
  const moving = K.$('#seq-moving-tool');
  const sources = {
    sink: '__IMG:egg-sink__', cup: '__IMG:cup__', float: '__IMG:egg-float__',
    salt: '__IMG:salt__', chopsticks: '__IMG:chopsticks__', tongs: '__IMG:tongs__',
  };
  let phase = 0;
  let misses = 0;
  let demo = false;
  let busy = false;
  let timer;

  function draw() {
    if (phase === 0) {
      view.src = sources.sink;
      view.alt = '这次鸡蛋停在杯底';
    } else if (phase === 3) {
      view.src = sources.float;
      view.alt = '这次鸡蛋浮在水面';
    } else {
      view.src = sources.cup;
      view.alt = '准备加入食盐和搅拌的水杯';
    }
    K.$$('.seq-step').forEach((step, index) => {
      step.classList.toggle('done', index < phase);
      step.classList.toggle('active', index === phase);
    });
    K.levels(order.length, phase);
  }

  function showTool(key, animate) {
    moving.src = sources[key];
    moving.dataset.tool = key;
    moving.classList.remove('hide');
    moving.classList.toggle('moving', animate);
  }

  function hideTool() {
    moving.classList.add('hide');
    moving.classList.remove('moving');
  }

  function reset() {
    clearTimeout(timer);
    phase = 0;
    misses = 0;
    demo = false;
    busy = false;
    hideTool();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    draw();
    K.say('先看鸡蛋的位置，再按顺序选工具。');
  }

  function act(button) {
    if (!K.started || demo || busy || phase >= order.length || button.querySelector('[data-failed]')) return;
    const tool = button.dataset.tool;
    if (order[phase] !== tool) {
      misses += 1;
      K.shake(button);
      K.sfx.no();
      if (misses === 1) {
        K.say('先回想实验顺序，再选工具。', 'no');
      } else if (misses === 2) {
        K.say('看看左边的实验步骤，再想下一步。', 'no');
        K.highlight('#seq-history');
      } else {
        K.say('老师示范下一步工具，跟着再试。', 'no');
        K.highlight('#seq-' + order[phase]);
        misses = 0;
      }
      return;
    }

    busy = true;
    showTool(phase === 0 ? 'salt' : tool, true);
    K.sfx.drop();
    timer = setTimeout(() => {
      hideTool();
      phase += 1;
      draw();
      K.star(1, button);
      K.sfx.ok();
      K.say([
        '盐已加入，接着让它和水混合。',
        '已经搅拌，接着放入鸡蛋再观察。',
        '画面里浮起来了，把这一次现象记下来。',
      ][phase - 1], 'ok');
      misses = 0;
      busy = phase === order.length;
      if (busy) {
        timer = setTimeout(() => K.finish({
          title: '实验顺序完成了',
          sub: '先操作，再观察，真实实验请大人协助。',
          again: reset,
        }), 1000);
      }
    }, 550);
  }

  K.$$('#seq-tools button').forEach(button => button.addEventListener('click', () => act(button)));
  K.$$('#play img').forEach(image => image.addEventListener('error', () => {
    image.dataset.failed = '1';
    K.say('图片没有加载好，请重新打开这一页。', 'no');
  }));
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) {
      reset();
      return;
    }
    if (state.demo === true && Number.isInteger(state.phase)) {
      clearTimeout(timer);
      demo = true;
      phase = Math.max(0, Math.min(order.length, state.phase));
      draw();
      hideTool();
      if (phase === 1) showTool('salt', false);
      if (phase === 2) showTool('chopsticks', true);
    }
  };
  draw();
  K.ready({ emoji: '', title: '按步骤做实验', sub: '听老师示范，再按顺序操作' });
})();
