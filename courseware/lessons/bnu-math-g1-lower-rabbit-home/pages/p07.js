(function () {
  const tasks = [5, 2, 4];
  const left = K.$('#left-house');
  const right = K.$('#right-house');
  const total = K.$('#total-strip');
  const picture = K.$('#rabbit-model').getAttribute('src');
  let round = 0, demo = false, transferred = false, misses = 0, timer;
  const rabbits = Array.from({length: 12}, (_, index) => {
    const button = K.el('button', 'home-rabbit', '');
    button.type = 'button';
    button.dataset.rabbit = index + 1;
    const image = K.el('img', '', '', button);
    image.alt = '';
    image.onerror = () => {
      image.remove();
      K.el('span', 'rabbit-fallback', '', button).setAttribute('aria-hidden', 'true');
    };
    image.src = picture;
    button.onclick = () => move(button, left);
    K.drag(button, {enabled: () => !demo && !transferred, targets: () => [left, right], onDrop: (_, destination) => { if (destination) move(button, destination); }});
    return button;
  });

  K.hud({icon: '←', title: '只搬一只，总数还在', levels: tasks.length});
  K.owl();
  K.ready({emoji: '←', title: '只搬一只', sub: '把一只兔子从蓝屋搬到红屋'});

  function update() {
    const a = left.children.length, b = right.children.length;
    K.$('#left-number').textContent = a;
    K.$('#right-number').textContent = b;
    total.textContent = `${a} ＋ ${b} ＝ ${a + b}`;
    for (const button of rabbits) {
      button.setAttribute('aria-label', button.parentElement === left ? '红屋的一只兔子' : '蓝屋的一只兔子');
      button.disabled = transferred || demo;
    }
    K.levels(tasks.length, round);
  }

  function move(button, destination, forced = false) {
    if ((!forced && demo) || transferred) return;
    if (button.parentElement !== right || destination !== left) {
      misses++;
      K.sfx.no();
      K.highlight('#move-arrow');
      K.say(misses === 1 ? '看看箭头是往哪边的。' : '先在蓝屋里找一只，再把它送去红屋。', 'no');
      return;
    }
    transferred = true;
    K.$('#move-arrow').classList.remove('teach-hl');
    left.append(button);
    button.classList.add('moved');
    update();
    if (forced) return;
    K.sfx.ok();
    K.star(1, button);
    K.say('同一只换了屋，两边合起来还是十二只。', 'ok');
    timer = setTimeout(() => {
      if (++round < tasks.length) load(tasks[round]);
      else K.finish({title: '兔子都安好家啦', sub: '只换位置，不添也不丢。', again: reset});
    }, 1200);
  }

  function load(numberOnLeft) {
    transferred = false;
    misses = 0;
    for (const [index, button] of rabbits.entries()) {
      button.classList.remove('moved');
      (index < numberOnLeft ? left : right).append(button);
    }
    update();
    K.say('点一下蓝屋的一只兔子，或把它拖到红屋。');
  }

  function reset() {
    clearTimeout(timer);
    demo = false;
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    load(tasks[0]);
  }

  K.onStart = reset;
  K.onState = state => {
    if (state.demo) {
      clearTimeout(timer);
      K.$('#finish')?.classList.add('gone');
      demo = true;
      round = 0;
      load(3);
      K.say('先看老师把一只从蓝屋搬到红屋。');
    }
    if (demo && state.move) move(right.firstElementChild, left, true);
    if (state.play) reset();
  };
  load(tasks[0]);
})();
