(function () {
  const assets = {sun:'__IMG:sun__', leaf:'__IMG:leaf__'};
  const cues = {}; // Populated with checked teacher recordings at media binding.
  const rounds = [{top:4,start:4,match:'more'},{top:7,start:7,match:'less'},{top:6,start:5,match:'same'}];
  const board = K.$('#count-board');
  const plus = K.$('#count-plus');
  const minus = K.$('#count-minus');
  const check = K.$('#count-check');
  let level = 0, leaves = 0, attempts = 0, demo = false, locked = false, direction = 0, timer, clip;

  K.hud({icon:'◌', title:'对齐以后比一比', levels:rounds.length});
  K.owl();
  K.ready({emoji:'◌', title:'对齐以后比一比', sub:'上下一个对一个，再看哪边有剩'});

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
  function row(selector, kind, count, other) {
    const panel = K.$(selector);
    panel.replaceChildren();
    for (let i = 0; i < 10; i++) {
      if (i >= count) {
        K.el('span', 'count-empty', null, panel); continue;
      }
      const img = K.el('img', 'count-art ' + (i < other ? 'paired' : 'unpaired'), null, panel);
      img.alt = (kind === 'sun' ? '一枚太阳印' : '一枚叶印') + (i < other ? '，已配对' : '，未配对');
      img.onerror = () => { img.classList.add('count-missing'); K.say('印章图没加载，请点重载图片。', 'no'); };
      img.src = assets[kind];
    }
  }
  function render() {
    const top = demo ? 4 : rounds[level].top;
    const sameReady = !demo && rounds[level].match === 'same' && leaves === top;
    K.$('#count-round').textContent = demo ? '老师示范' : '第 ' + (level + 1) + ' 轮';
    row('#count-top', 'sun', top, leaves);
    row('#count-bottom', 'leaf', leaves, top);
    plus.disabled = demo || locked || sameReady || direction < 0 || leaves === 10;
    minus.disabled = demo || locked || sameReady || direction > 0 || leaves === 1;
    check.disabled = demo || locked;
    K.levels(rounds.length, level);
  }
  function reset() {
    clearTimeout(timer); stopAudio();
    level = 0; leaves = rounds[0].start; attempts = 0; demo = false; locked = false; direction = 0;
    K.stars = 0; K.$('#star-n').textContent = '0';
    board.classList.remove('wrong');
    render(); K.say('听题，再增减叶印。');
  }
  function edit(delta) {
    if (demo || locked || (delta > 0 ? plus.disabled : minus.disabled) || K.$('.count-missing')) return;
    const next = leaves + delta;
    if (next < 1 || next > 10) return;
    leaves = next; direction = delta; board.classList.remove('wrong'); render(); K.sfx.pick();
    K.say(rounds[level].match === 'same' && leaves === rounds[level].top
      ? '每枚都配上了，点核对看看。' : '从左往右比，看看哪排有没配对的。');
  }
  function hint() {
    if (demo || locked) return;
    attempts++;
    K.say(attempts === 1 ? '再听听要求，看看两排末尾。' : '上下逐个找朋友，剩下的那一排更多。', 'no');
    if (attempts > 1) K.highlight('#count-board');
  }
  function submit() {
    if (demo || locked || K.$('.count-missing')) return;
    const current = rounds[level];
    const result = leaves > current.top ? 'more' : leaves < current.top ? 'less' : 'same';
    if (result !== current.match) {
      // A submitted arrangement can be revised in the opposite direction.
      // If the child has not started moving objects, both choices stay open.
      if (direction) direction = current.match === 'more' || (current.match === 'same' && leaves < current.top) ? 1 : -1;
      render(); board.classList.add('wrong'); K.sfx.no(); hint(); return;
    }
    locked = true; stopAudio(); board.classList.remove('wrong', 'teach-hl');
    render(); K.star(1); K.sfx.ok();
    K.say(result === 'same' ? '都配上了，两边一样多。' : '你找到了没配上的一边，和要求一样。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === rounds.length) {
        K.finish({title:'两排都比清楚了', sub:'一个对一个，多少就看得见了。', again:reset});
        return;
      }
      leaves = rounds[level].start; attempts = 0; locked = false; direction = 0;
      render(); hear(); K.say('要求换了，先听新一轮。');
    }, 720);
  }

  plus.addEventListener('click', () => edit(1));
  minus.addEventListener('click', () => edit(-1));
  check.addEventListener('click', submit);
  K.$('#count-listen').addEventListener('click', hear);
  K.$('#count-help').addEventListener('click', hint);
  K.$('#count-reload').addEventListener('click', render);
  K.$('#start-btn').addEventListener('click', hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo || state.demoEqual) {
      clearTimeout(timer); stopAudio(); level = 0; demo = true; locked = true;
      leaves = state.demoEqual ? 4 : 3; render();
    }
    if (state.play) { reset(); hear(); }
  };
  reset();
})();
