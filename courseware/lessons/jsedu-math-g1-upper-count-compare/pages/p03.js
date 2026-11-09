(function () {
  const stamps = {sun:'__IMG:sun__', leaf:'__IMG:leaf__'};
  const names = {sun:'太阳印', leaf:'叶印'};
  const cues = {}; // Populated with checked teacher recordings at media binding.
  const tasks = [{shape:'sun', count:3}, {shape:'leaf', count:5}, {shape:'sun', count:8}];
  const supply = K.$('#count-supply');
  const paper = K.$('#count-board');
  const erase = K.$('#count-return');
  const check = K.$('#count-check');
  const reload = K.$('#count-reload');
  let level = 0, marks = [], ink = '', attempts = 0, demo = false, locked = false, erasing = false, timer, clip;

  K.hud({icon:'◌', title:'听数盖图章', levels:tasks.length});
  K.owl();
  K.ready({emoji:'◌', title:'听数盖图章', sub:'选一个章，在纸上印出听到的数量'});

  function art(parent, kind) {
    const img = K.el('img', 'count-art', null, parent);
    img.alt = names[kind];
    img.onerror = () => {
      img.classList.add('count-missing'); reload.disabled = false;
      K.say('图章没加载，请点重载图片。', 'no');
    };
    img.src = stamps[kind];
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
    reload.disabled = true;
    supply.replaceChildren();
    for (const kind of Object.keys(stamps)) {
      const button = K.el('button', 'count-action' + (ink === kind ? ' chosen' : ''), null, supply);
      button.dataset.ink = kind;
      button.setAttribute('aria-label', '选择' + names[kind]);
      button.setAttribute('aria-pressed', String(ink === kind));
      button.disabled = demo || locked || erasing || marks.length > 0;
      art(button, kind);
      button.addEventListener('click', () => {
        if (kind !== tasks[level].shape) {
          K.shake(button); K.sfx.no(); K.say('先重听，分清要画的是哪一种。', 'no');
          return;
        }
        ink = kind; render(); K.say('再点空格，盖一个图章。');
      });
    }
    paper.replaceChildren();
    for (let i = 0; i < 10; i++) {
      const filled = marks.find(mark => mark.slot === i);
      const slot = K.el('button', 'count-action' + (filled ? ' placed' : ''), null, paper);
      slot.dataset.slot = String(i);
      slot.setAttribute('aria-label', filled ? '已有' + names[filled.kind] : '盖章空格');
      slot.disabled = demo || locked || erasing || !ink || Boolean(filled);
      if (filled) art(slot, filled.kind);
      slot.addEventListener('click', () => stamp(i, slot));
    }
    erase.disabled = demo || locked || !erasing || !marks.length;
    check.disabled = demo || locked;
    K.levels(tasks.length, level);
  }
  function reset() {
    clearTimeout(timer); stopAudio();
    level = 0; marks = []; ink = ''; attempts = 0; demo = false; locked = false; erasing = false;
    K.stars = 0; K.$('#star-n').textContent = '0';
    paper.classList.remove('wrong', 'teach-hl');
    render(); K.say('听题，先选图章，再盖到空格上。');
  }
  function stamp(slot, button) {
    if (demo || locked || erasing || K.$('.count-missing') || marks.some(mark => mark.slot === slot)) return;
    if (!ink || ink !== tasks[level].shape) {
      button.classList.add('wrong'); K.shake(button); K.sfx.no();
      K.say(!ink ? '先选一种图章。' : '先重听，分清要画的是哪一种。', 'no');
      return;
    }
    paper.classList.remove('wrong');
    marks.push({slot, kind:ink});
    render(); K.sfx.tick(marks.length);
    K.say('画过的留在纸上，每个图只数一次。');
  }
  function hint() {
    if (demo || locked) return;
    attempts++;
    K.say(attempts === 1 ? '先听清画什么，再数纸上的图。' : '数过的图别再数，可以从左往右数。', 'no');
    if (attempts > 1) K.highlight('#count-board');
  }
  function submit() {
    if (demo || locked || K.$('.count-missing')) return;
    if (marks.length !== tasks[level].count) {
      erasing = marks.length > tasks[level].count;
      render(); paper.classList.add('wrong'); K.shake(paper); K.sfx.no();
      hint();
      if (erasing) K.say('重新数数。印多了可以擦掉再核对。', 'no');
      return;
    }
    locked = true; stopAudio(); paper.classList.remove('wrong', 'teach-hl');
    render(); K.star(1); K.sfx.ok();
    K.say('图的种类和数量都合适。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === tasks.length) {
        K.finish({title:'印章画好啦', sub:'你按听到的数印出了图。', again:reset});
        return;
      }
      marks = []; ink = ''; attempts = 0; locked = false; erasing = false;
      render(); hear(); K.say('换一张新纸，听这次的要求。');
    }, 720);
  }

  erase.addEventListener('click', () => {
    if (!demo && !locked && erasing && marks.length) {
      marks.pop();
      paper.classList.remove('wrong');
      render(); K.say('擦掉一个，重新数一数。');
    }
  });
  check.addEventListener('click', submit);
  K.$('#count-listen').addEventListener('click', hear);
  K.$('#count-help').addEventListener('click', hint);
  reload.addEventListener('click', render);
  K.$('#start-btn').addEventListener('click', hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo || state.showPrint) {
      clearTimeout(timer); stopAudio(); level = 0; demo = true; locked = true; ink = 'leaf';
      marks = state.showPrint ? [0,1,2,3].map(slot => ({slot, kind:'leaf'})) : [];
      render();
    }
    if (state.play) { reset(); hear(); }
  };
  render();
})();
