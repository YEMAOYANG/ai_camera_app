(function () {
  const stamp = '__IMG:stamp__';
  const cues = {}; // Populated with checked teacher recordings at media binding.
  const board = K.$('#count-board');
  const move = K.$('#count-shift');
  const check = K.$('#count-check');
  const layouts = [
    Array.from({length:10}, (_, i) => [33 + i * 101, 117]),
    [[61,43],[191,184],[298,68],[429,193],[491,35],[585,113],[697,180],[762,39],[876,133],[950,53]],
    Array.from({length:10}, (_, i) => [210 + (i % 5) * 142, 47 + Math.floor(i / 5) * 142])
  ];
  const tokens = [];
  const counted = new Set();
  let level = 0, layout = 0, moved = false, demo = false, locked = false, attempts = 0, timer, clip;

  K.hud({icon:'◌', title:'十枚换个队形', levels:2});
  K.owl();
  K.ready({emoji:'◌', title:'十枚换个队形', sub:'只挪位置，再从头点数同一批邮票'});

  function addPicture(button) {
    const img = K.el('img', 'count-art', null, button);
    img.alt = '一枚风筝邮票';
    img.onerror = () => { img.classList.add('count-missing'); K.say('邮票图没加载，请点重载图片。', 'no'); };
    img.src = stamp;
  }
  function stopAudio() { if (clip) { clip.pause(); clip = null; } }
  function hear() {
    stopAudio();
    if (demo || locked || !cues[0]) return;
    clip = new Audio(cues[0]);
    const current = clip;
    current.play().catch(error => {
      if (clip === current && error.name !== 'AbortError') K.say('声音没播出，再点听题。');
    });
  }
  function render() {
    K.$('#count-round').textContent = demo ? '老师示范' : '第 ' + (level + 1) + ' 轮';
    board.classList.toggle('count-demo', demo);
    tokens.forEach((token, i) => {
      const [left, top] = layouts[layout][i];
      token.style.left = left + 'px';
      token.style.top = top + 'px';
      token.classList.toggle('counted', counted.has(i));
      token.disabled = demo || locked || counted.has(i);
      token.setAttribute('aria-pressed', String(counted.has(i)));
    });
    move.disabled = demo || locked || moved;
    check.disabled = demo || locked;
    K.levels(2, level);
  }
  function reset() {
    clearTimeout(timer); stopAudio();
    level = 0; layout = 0; moved = false; demo = false; locked = false; attempts = 0;
    counted.clear(); board.classList.remove('wrong');
    K.stars = 0; K.$('#star-n').textContent = '0';
    render(); K.say('同一批邮票，先换摆法，再点数。');
  }
  function count(i) {
    if (demo || locked || counted.has(i) || K.$('.count-missing')) return;
    counted.add(i); board.classList.remove('wrong'); render();
    K.sfx.tick(counted.size);
    K.say('亮起来的已经数过了，接着找还没亮的。');
  }
  function hint() {
    if (demo || locked) return;
    attempts++;
    K.say(!moved ? '请先换一个摆法。' : attempts === 1 ? '按一个方向点数，亮了就别再点。' : '看看还有哪枚没有亮起来。', 'no');
    if (moved && attempts > 1) K.highlight('#count-board');
  }
  function submit() {
    if (demo || locked || K.$('.count-missing')) return;
    if (!moved || counted.size !== tokens.length) {
      board.classList.add('wrong'); K.sfx.no(); hint(); return;
    }
    locked = true; stopAudio(); board.classList.remove('wrong', 'teach-hl');
    render(); K.star(1); K.sfx.ok();
    K.say('没添也没拿走，还是刚才的十枚。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === 2) {
        K.finish({title:'队形换好了', sub:'邮票搬了家，数量没有变。', again:reset});
        return;
      }
      counted.clear(); moved = false; attempts = 0; locked = false;
      render(); hear(); K.say('再换一种摆法，看看邮票少了没有。');
    }, 720);
  }

  for (let i = 0; i < 10; i++) {
    const button = K.el('button', 'count-action count-token', null, board);
    button.dataset.token = String(i);
    button.setAttribute('aria-label', '点数这枚邮票');
    addPicture(button);
    button.addEventListener('click', () => count(i));
    tokens.push(button);
  }
  move.addEventListener('click', () => {
    if (demo || locked || moved) return;
    moved = true; layout = level + 1; counted.clear(); board.classList.remove('wrong');
    render(); K.sfx.pick(); K.say('邮票只挪了位置，现在重新数。');
  });
  check.addEventListener('click', submit);
  K.$('#count-listen').addEventListener('click', hear);
  K.$('#count-help').addEventListener('click', hint);
  K.$('#count-reload').addEventListener('click', () => {
    tokens.forEach(button => { button.replaceChildren(); addPicture(button); });
  });
  K.$('#start-btn').addEventListener('click', hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo || state.demoSpread || state.demoRows) {
      clearTimeout(timer); stopAudio(); level = 0; demo = true; locked = true;
      layout = state.demoRows ? 2 : state.demoSpread ? 1 : 0;
      counted.clear();
      if (state.demo) tokens.forEach((_token, i) => counted.add(i));
      render();
    }
    if (state.play) { reset(); hear(); }
  };
  render();
})();
