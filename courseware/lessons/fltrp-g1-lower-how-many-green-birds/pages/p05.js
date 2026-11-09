(function () {
  const colours = ['blue', 'green', 'green', 'yellow', 'green', 'blue', 'green', 'green'];
  const targetTotal = colours.filter(colour => colour === 'green').length;

  function makeSelection() {
    const selected = new Set();
    return {
      select(index) {
        if (colours[index] !== 'green' || selected.has(index)) return 0;
        selected.add(index);
        return selected.size;
      },
      reset() { selected.clear(); },
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { makeSelection };
  if (typeof document === 'undefined') return;

  const model = makeSelection();
  const visual = { green: '__IMG:bird-green__', blue: '__IMG:bird-blue__', yellow: '__IMG:bird-yellow__' };
  const names = { green: '绿色', blue: '蓝色', yellow: '黄色' };
  const positions = K.$('#observe-slots');
  let wrongs = 0;
  let complete = false;
  let demo = false;
  let finishTimer;
  K.hud({ icon: '', title: '只数绿色的小鸟', levels: 1 });
  K.owl();

  function showFailure() { K.$('#sort-picture-failure').classList.remove('hide'); }

  const slots = Array.from({ length: targetTotal }, (_, index) => {
    const cell = K.el('div', 'observation-slot', null, positions);
    cell.id = 'observe-slot-' + (index + 1);
    const img = K.el('img', 'hide', null, cell);
    img.alt = '';
    img.addEventListener('error', showFailure);
    img.src = visual.green;
    return { img, number: K.el('span', '', null, cell) };
  });

  const birds = colours.map((colour, index) => {
    const button = K.el('button', 'sorting-bird', null, K.$('#sort-line'));
    button.id = 'sort-bird-' + (index + 1);
    button.type = 'button';
    button.setAttribute('aria-label', names[colour] + '小鸟，第' + (index + 1) + '只');
    const img = K.el('img', '', null, button);
    img.alt = '';
    img.addEventListener('error', showFailure);
    img.src = visual[colour];
    button.addEventListener('click', () => select(index));
    return button;
  });

  function setSlot(index, show) {
    slots[index].img.classList.toggle('hide', !show);
    slots[index].number.textContent = show ? String(index + 1) : '';
  }

  function select(index) {
    if (demo || complete) return;
    const count = model.select(index);
    if (!count) {
      wrongs += 1;
      K.shake(birds[index]);
      K.sfx.no();
      if (wrongs === 2) K.highlight('#sample-perch');
      K.say(wrongs === 1 ? '再比较这只鸟和颜色样本。' : '数过的已进格，别的颜色先留在原处。', 'no');
      return;
    }
    birds[index].classList.add('selected');
    birds[index].disabled = true;
    setSlot(count - 1, true);
    K.sfx.tick(count);
    if (count !== targetTotal) return;
    complete = true;
    K.star(1, birds[index]);
    K.levels(1, 1);
    K.say('观察格里的都是绿鸟。', 'ok');
    finishTimer = setTimeout(() => K.finish({ title: '找到全部绿鸟', sub: 'Five green birds.', again: reset }), 1100);
  }

  function reset() {
    clearTimeout(finishTimer);
    complete = demo = false;
    wrongs = 0;
    model.reset();
    birds.forEach(bird => { bird.classList.remove('selected'); bird.disabled = false; });
    slots.forEach((_, index) => setSlot(index, false));
    K.levels(1, 0);
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$('#tip').style.display = 'none';
    K.say('听清颜色，再点符合的小鸟。');
  }

  K.onState = state => {
    if (!Object.hasOwn(state, 'demoPick')) return;
    if (!state.demoPick) {
      reset();
      return;
    }
    demo = true;
    birds[1].classList.add('selected');
    setSlot(0, true);
  };

  K.$('#colour-example').addEventListener('error', showFailure);
  K.$('#reload-sorting').addEventListener('click', () => {
    K.$('#sort-picture-failure').classList.add('hide');
    K.$$('#sort-stage img').forEach(img => { img.src = img.src; });
  });
  reset();
  K.onStart = reset;
  K.ready({ title: '按颜色挑一挑', sub: '听完题，只挑一种颜色', emoji: '' });
})();
