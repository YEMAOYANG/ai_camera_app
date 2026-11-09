(() => {
  const leftPots = K.$('#p06-left-pots');
  const rightPots = K.$('#p06-right-pots');
  const leftCount = K.$('#p06-left-count');
  const rightCount = K.$('#p06-right-count');
  const move = K.$('#p06-move');
  const choices = K.$('#p06-choices');
  const leftUnits = [];
  const rightUnits = [];
  let left = 9;
  let right = 1;
  let phase = 'move';
  let misses = 0;
  let timer;
  K.hud({title:'十盆分两盘',icon:'10',levels:5});
  K.owl();

  function unit(parent) {
    const pot = K.el('span', 'p06-pot', '<img src="__IMG:seedling__" alt=""><i data-semantic-diagram="一盆对应一个点"></i>', parent);
    K.$('img', pot).addEventListener('error', () => pot.classList.add('failed'));
    return pot;
  }
  for (let i = 0; i < 9; i++) {
    leftUnits.push(unit(leftPots));
    rightUnits.push(unit(rightPots));
  }
  function render() {
    leftUnits.forEach((pot, i) => { pot.hidden = i >= left; });
    rightUnits.forEach((pot, i) => { pot.hidden = i >= right; });
    leftCount.textContent = String(left);
    rightCount.textContent = phase === 'match' ? '?' : String(right);
    move.hidden = phase !== 'move';
    move.disabled = phase !== 'move';
    choices.hidden = phase !== 'match' && phase !== 'done';
    Array.from(choices.children).forEach(button => { button.disabled = phase === 'done'; });
  }
  function reset() {
    clearTimeout(timer);
    left = 9;
    right = 1;
    phase = 'move';
    misses = 0;
    Array.from(choices.children).forEach(button => button.classList.remove('chosen'));
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(5, 0);
    render();
    K.say('点箭头，每次从左盘移一盆。');
  }

  move.onclick = () => {
    if (phase !== 'move') return;
    left--;
    right++;
    K.levels(5, right - 1);
    K.sfx.tick(right);
    render();
    K.pop(rightUnits[right - 1]);
    K.say(left === right ? '两盘都是五盆，一样多。' : '左边少一盆，右边多一盆，总数还是十。', 'ok');
    if (left === right) {
      move.disabled = true;
      timer = setTimeout(() => {
        phase = 'match';
        left = 7;
        right = 0;
        render();
        K.say('换一组。左盘七盆，选右盘的花盆。');
      }, 1700);
    }
  };

  [4, 2, 3].forEach(number => {
    const button = K.el('button', 'p06-choice', null, choices);
    button.id = 'p06-choice-' + number;
    button.setAttribute('aria-label', number + '盆幼苗');
    for (let i = 0; i < number; i++) unit(button);
    button.onclick = () => {
      if (phase !== 'match') return;
      if (left + number !== 10) {
        misses++;
        K.sfx.no();
        K.shake(button);
        K.say(misses === 1 ? '把两盘放在一起数，想想够不够十盆。' : '从七往后接着数，每多一盆就数下一个数。', 'no');
        if (misses > 1) K.highlight('#p06-left-pots');
        return;
      }
      phase = 'done';
      right = number;
      button.classList.add('chosen');
      render();
      K.star(1, button);
      K.levels(5, 5);
      K.sfx.ok();
      K.say('七盆和三盆合起来，正好十盆。', 'ok');
      timer = setTimeout(() => K.finish({title:'十盆配好了',sub:'两部分合起来是十',again:reset}), 1050);
    };
  });

  K.onStart = reset;
  K.onState = state => {
    if (state.resetTask) reset();
    if (Number.isInteger(state.demoSplit)) {
      phase = 'demo';
      left = state.demoSplit;
      right = 10 - left;
      render();
      K.say('看两盘中的盆数，合起来是十。');
    }
  };
  reset();
  K.ready({title:'十盆分两盘',sub:'挪一盆，看两盘一起变',emoji:'10'});
})();
