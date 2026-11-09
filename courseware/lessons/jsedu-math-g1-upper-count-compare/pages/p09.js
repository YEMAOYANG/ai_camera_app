(function () {
  const assets = {badge:'__IMG:badge__', envelope:'__IMG:envelope__'};
  const cues = {}; // Populated with checked teacher recordings at media binding.
  const taskSizes = [2, 3, 5];
  const supply = K.$('#count-supply');
  const board = K.$('#count-board');
  const check = K.$('#count-check');
  let level = 0, fills = [], attempts = 0, demo = false, locked = false, timer, clip;

  K.hud({icon:'◌', title:'两枚纪念章进一封', levels:taskSizes.length});
  K.owl();
  K.ready({emoji:'◌', title:'两枚纪念章进一封', sub:'看每一封信，放进去两枚纪念章'});

  function art(parent, key, extra = '') {
    const img = K.el('img', 'count-art ' + extra, null, parent);
    img.alt = key === 'badge' ? '一枚纪念章' : '一个信封';
    img.onerror = () => { img.classList.add('count-missing'); K.say('图片没加载，请点重载图片。', 'no'); };
    img.src = assets[key];
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
    fills.forEach((quantity, i) => {
      const envelope = K.el('button', 'count-action count-envelope' + (quantity === 2 ? ' paired' : ''), null, board);
      envelope.dataset.envelope = String(i);
      envelope.setAttribute('aria-label', '第 ' + (i + 1) + ' 封，已有 ' + quantity + ' 枚');
      envelope.disabled = demo || locked;
      art(envelope, 'envelope', 'count-paper');
      const pockets = K.el('span', 'count-pockets', null, envelope);
      for (let slot = 0; slot < 2; slot++) {
        if (slot < quantity) art(pockets, 'badge', 'count-token-art');
        else K.el('i', 'count-empty', null, pockets);
      }
      envelope.addEventListener('click', () => place(i, envelope));
    });
    check.disabled = demo || locked;
    K.levels(taskSizes.length, level);
  }
  function reset() {
    clearTimeout(timer); stopAudio();
    level = 0; fills = Array(taskSizes[0]).fill(0); attempts = 0; demo = false; locked = false;
    K.stars = 0; K.$('#star-n').textContent = '0';
    board.classList.remove('wrong');
    render(); K.say('点信封或把纪念章拖进去。');
  }
  function place(i, envelope) {
    if (demo || locked || K.$('.count-missing') || !Number.isInteger(i) || i < 0 || i >= fills.length) return;
    if (fills[i] >= 2) {
      envelope.classList.add('wrong'); K.shake(envelope); K.sfx.no();
      K.say('这封已经放好了，看看还有哪一封没配好。', 'no');
      return;
    }
    fills[i]++; board.classList.remove('wrong'); render(); K.sfx.tick(fills[i]);
    K.say(fills[i] === 2 ? '这封有两枚了，接着看下一封。' : '这一封先放了一枚。');
  }
  function hint() {
    if (demo || locked) return;
    attempts++;
    K.say(attempts === 1 ? '一个信封一个信封地看。' : '有空位的信封还可以放一枚。', 'no');
    if (attempts > 1) K.highlight('#count-board');
  }
  function submit() {
    if (demo || locked || K.$('.count-missing')) return;
    if (fills.some(n => n !== 2)) {
      board.classList.add('wrong'); K.sfx.no(); hint(); return;
    }
    locked = true; stopAudio(); board.classList.remove('wrong', 'teach-hl');
    render(); K.star(1); K.sfx.ok();
    K.say('每封都配好两枚，寄信啦。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === taskSizes.length) {
        K.finish({title:'纪念章配好啦', sub:'你一封一封检查了纪念章。', again:reset});
        return;
      }
      fills = Array(taskSizes[level]).fill(0); attempts = 0; locked = false;
      render(); hear(); K.say('换几封信，仍然要一封一封配。');
    }, 720);
  }

  const token = K.el('button', 'count-action', null, supply);
  token.setAttribute('aria-label', '一枚可拖放的纪念章');
  art(token, 'badge');
  K.drag(token, {
    enabled:() => !demo && !locked,
    targets:() => K.$$('[data-envelope]'),
    onDrop:(_token, envelope) => { if (envelope) place(Number(envelope.dataset.envelope), envelope); },
    onTap:() => K.say('选一封信，点一下就能放进去。')
  });
  token.addEventListener('click', event => { if (event.detail === 0 && !demo) K.say('选一封信，点一下就能放进去。'); });
  check.addEventListener('click', submit);
  K.$('#count-listen').addEventListener('click', hear);
  K.$('#count-help').addEventListener('click', hint);
  K.$('#count-reload').addEventListener('click', () => { token.replaceChildren(); art(token, 'badge'); render(); });
  K.$('#start-btn').addEventListener('click', hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo || state.demoFilled) {
      clearTimeout(timer); stopAudio(); level = 0; demo = true; locked = true;
      fills = state.demoFilled ? [2,0] : [0,0];
      render();
    }
    if (state.play) { reset(); hear(); }
  };
  reset();
})();
