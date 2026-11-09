(function () {
  K.hud({ icon: '◉', title: '两种光下找影子', levels: 2 });
  K.owl();

  const scene = K.$('#shadow-view');
  const controls = K.$$('#shadow-controls button');
  const order = ['lamp', 'sun'];
  const images = {
    campus: { src: '__IMG:scene-campus__', alt: '等待切换光源的校园场景' },
    lamp: { src: '__IMG:lamp-shadow__', alt: '台灯照出绿色积木的影子' },
    sun: { src: '__IMG:sun-shadow__', alt: '日光照出木块的影子' },
  };
  let round = 0;
  let misses = 0;
  let demo = false;
  let busy = false;
  let timer;

  function showScene(key) {
    scene.src = images[key].src;
    scene.alt = images[key].alt;
  }

  function reset() {
    clearTimeout(timer);
    round = 0;
    misses = 0;
    demo = false;
    busy = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(2, 0);
    controls.forEach(button => button.classList.remove('observed'));
    showScene('campus');
    K.say('先找台灯，再找太阳。');
  }

  function choose(button) {
    if (!K.started || busy || demo || round === order.length) return;
    const key = button.dataset.light;
    if (key !== order[round]) {
      misses += 1;
      K.shake(button);
      K.sfx.no();
      if (misses === 1) {
        K.say('想想这一轮要找哪一种光。', 'no');
      } else if (misses === 2) {
        K.say('看看两幅图，光从哪里来？', 'no');
        K.highlight('#shadow-controls');
      } else {
        K.say('老师指给你看，再试一次。', 'no');
        K.highlight('#shadow-' + order[round]);
        misses = 0;
      }
      return;
    }

    showScene(key);
    button.classList.add('observed');
    K.star(1, button);
    K.sfx.ok();
    misses = 0;
    round += 1;
    K.levels(order.length, round);
    if (round < order.length) {
      K.say('看到台灯下的影子了，接下来找太阳。', 'ok');
      return;
    }
    K.say('日光下也能看到影子。', 'ok');
    busy = true;
    timer = setTimeout(() => K.finish({
      title: '两种光下都找到了影子',
      sub: '还可以和大人在身边找一找。',
      again: reset,
    }), 1050);
  }

  controls.forEach(button => button.addEventListener('click', () => choose(button)));
  scene.addEventListener('error', () => {
    if (scene.getAttribute('src') !== images.campus.src) showScene('campus');
  });
  controls.forEach(button => {
    const image = button.querySelector('img');
    image.addEventListener('error', () => {
      button.disabled = true;
      K.say('图片没有加载好，请重新打开这一页。', 'no');
    });
    image.addEventListener('load', () => { button.disabled = false; });
  });

  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) {
      reset();
      return;
    }
    if (state.demo === 'sun' || state.demo === 'lamp') {
      clearTimeout(timer);
      demo = true;
      showScene(state.demo);
    }
  };
  K.ready({ emoji: '', title: '两种光下找影子', sub: '切换光源，看看影子' });
})();
