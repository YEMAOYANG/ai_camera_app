(function () {
  const stamp = '__IMG:stamp__';
  const cues = {}; // Populated with checked teacher recordings at media binding.
  const targets = [3, 6, 9];
  const board = K.$('#count-board');
  const take = K.$('#count-take');
  const giveBack = K.$('#count-return');
  const check = K.$('#count-check');
  let level = 0, quantity = 0, attempts = 0, demo = false, locked = false, returning = false, timer, clip;

  K.hud({icon:'◌', title:'听数装邮票', levels:targets.length});
  K.owl();
  K.ready({emoji:'◌', title:'听数装邮票', sub:'听清要几枚，把邮票放进托盘'});

  function picture(parent) {
    const img = K.el('img', 'count-art', null, parent);
    img.alt = '一枚风筝邮票';
    img.onerror = () => { img.classList.add('count-missing'); K.say('邮票图没加载，请点重载图片。', 'no'); };
    img.src = stamp;
  }
  function stopAudio() { if (clip) { clip.pause(); clip = null; } }
  function hear() {
    stopAudio();
    if (demo || locked || !cues[level]) return;
    clip = new Audio(cues[level]);
    const current = clip;
    current.play().catch(error => {
      if (clip === current && error.name !== 'AbortError') K.say('声音没播出，再点听题。');
    });
  }
  function render() {
    K.$('#count-round').textContent = demo ? '老师示范' : '第 ' + (level + 1) + ' 轮';
    board.replaceChildren();
    for (let i = 0; i < 10; i++) {
      if (i < quantity) picture(board);
      else K.el('span', 'count-empty', null, board);
    }
    take.disabled = demo || locked || returning || quantity === 10;
    giveBack.disabled = demo || locked || !returning || quantity === 0;
    check.disabled = demo || locked;
    K.levels(targets.length, level);
  }
  function reset() {
    clearTimeout(timer); stopAudio();
    level = 0; quantity = 0; attempts = 0; demo = false; locked = false; returning = false;
    K.stars = 0; K.$('#star-n').textContent = '0';
    board.classList.remove('wrong', 'teach-hl');
    render(); K.say('听题，再一次拿一枚邮票。');
  }
  function edit(delta) {
    if (demo || locked || K.$('.count-missing')) return;
    if ((delta > 0 && returning) || (delta < 0 && !returning)) return;
    const next = quantity + delta;
    if (next < 0 || next > 10) return;
    quantity = next;
    board.classList.remove('wrong');
    render(); K.sfx.tick(quantity);
    K.say(delta > 0 ? '这枚已经进托盘了，数的时候别重复。' : '退回了一枚，再看看托盘里有几枚。');
  }
  function hint() {
    if (demo || locked) return;
    attempts++;
    K.say(attempts === 1 ? '先听清要求，再从托盘第一枚开始数。' : '一枚只数一次，数到的最后一个数是总数。', 'no');
    if (attempts > 1) K.highlight('#count-board');
  }
  function submit() {
    if (demo || locked || K.$('.count-missing')) return;
    if (quantity !== targets[level]) {
      returning = quantity > targets[level];
      render(); board.classList.add('wrong'); K.shake(board); K.sfx.no();
      hint();
      if (returning) K.say('重新数数。取多的邮票可以退回托盘外。', 'no');
      return;
    }
    locked = true; stopAudio(); board.classList.remove('wrong', 'teach-hl');
    render(); K.star(1); K.sfx.ok();
    K.say('刚好一样多，邮票可以送出。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === targets.length) {
        K.finish({title:'邮票送出啦', sub:'你按不同的数量拿好了邮票。', again:reset});
        return;
      }
      quantity = 0; attempts = 0; locked = false; returning = false;
      render(); hear(); K.say('新一轮换了数量，请先听清。');
    }, 720);
  }

  picture(take);
  K.drag(take, {enabled:() => !take.disabled, targets:() => [board],
    onTap:() => edit(1), onDrop:(_source, target) => { if (target) edit(1); }});
  take.addEventListener('click', event => { if (event.detail === 0) edit(1); });
  giveBack.addEventListener('click', () => edit(-1));
  check.addEventListener('click', submit);
  K.$('#count-listen').addEventListener('click', hear);
  K.$('#count-help').addEventListener('click', hint);
  K.$('#count-reload').addEventListener('click', () => {
    take.replaceChildren(); picture(take); render();
  });
  K.$('#start-btn').addEventListener('click', hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo || state.showFour) {
      clearTimeout(timer); stopAudio(); level = 0; demo = true; locked = true;
      quantity = state.showFour ? 4 : 0; render();
    }
    if (state.play) { reset(); hear(); }
  };
  render();
})();
