(() => {
  const K = window.K;
  const lane = K.$('#trial-window');
  const panel = K.$('#trial-options');
  const buttons = [K.$('#trial-option-a'), K.$('#trial-option-b')];
  const release = K.$('#trial-release');
  const replay = K.$('#trial-watch');
  const record = K.$('#trial-record');
  const title = K.$('#trial-prompt');
  let phase = 0;
  let misses = 0;
  let timer = 0;
  let demo = false;
  let running = false;

  const paths = (left, right) => '<svg viewBox="0 0 220 146" aria-hidden="true">'
    + '<path d="M23 129h174" stroke="#a4c6ba" stroke-width="4"/>'
    + '<path d="' + left + '" fill="none" stroke="#d18b37" stroke-width="8" stroke-linecap="round"/>'
    + '<path d="' + right + '" fill="none" stroke="#237978" stroke-width="8" stroke-linecap="round"/>'
    + '</svg>';
  const startIcon = (different) => paths('M40 42h52m-26 2v40', different ? 'M126 72h52m-26 2v40' : 'M126 42h52m-26 2v40');
  const routeIcon = (same) => paths(same ? 'M56 25v90' : 'M55 25q-25 20 0 43t0 47', 'M158 25v90');
  const spinIcon = (both) => paths(both ? 'M69 99a24 24 0 1 1 17-35l-2-16m2 16-16-3' : 'M61 37v70m-9-11 9 11 9-11', 'M165 99a24 24 0 1 1 17-35l-2-16m2 16-16-3');
  const craft = (inverted) => '<img style="transform:' + (inverted ? 'rotate(180deg)' : 'none') + '" src="__IMG:paper-rotor__" alt="">';
  const observations = {
    0: {title: '先找一样高的起点', labels: ['一个高一个低', '起点一样高'], pictures: [startIcon(true), startIcon(false)], correct: 1},
    2: {title: '这次谁先碰到地面', labels: ['平纸条先落', '纸蜻蜓先落'], pictures: ['<img src="__IMG:flat-strip__" alt="">', craft(false)], correct: 0},
    3: {title: '这次路线一样吗', labels: ['路线不一样', '路线一样'], pictures: [routeIcon(false), routeIcon(true)], correct: 0},
    4: {title: '这次谁转起来了', labels: ['两件都转', '只有纸蜻蜓转'], pictures: [spinIcon(true), spinIcon(false)], correct: 1},
    5: {title: '这次飞翼在什么位置', labels: ['飞翼朝下', '飞翼在上'], pictures: [craft(true), craft(false)], correct: 1},
  };

  function draw() {
    const row = observations[phase];
    K.levels(5, phase === 0 ? 0 : phase === 1 ? 1 : Math.min(phase - 1, 5));
    panel.classList.toggle('hide', !row || running);
    release.classList.toggle('hide', phase !== 1 || running);
    replay.classList.toggle('hide', phase < 2 || phase === 6 || running);
    release.disabled = demo || running;
    replay.disabled = demo || running;
    title.textContent = running ? '看它们落下来' : row?.title || (phase === 1 ? '一起轻轻松手' : '观察都记好了');
    buttons.forEach((button, index) => {
      button.classList.remove('hint');
      button.disabled = demo || running;
      if (row) {
        button.innerHTML = row.pictures[index];
        button.setAttribute('aria-label', row.labels[index]);
      }
    });
  }

  function reset() {
    clearTimeout(timer);
    phase = 0;
    misses = 0;
    demo = false;
    running = false;
    record.replaceChildren();
    lane.classList.remove('released');
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.say('先摆好两件，再一起松手');
    draw();
  }

  function animate(forTeacher = false) {
    if (running || (demo && !forTeacher)) return;
    clearTimeout(timer);
    running = true;
    lane.classList.remove('released');
    void lane.offsetWidth;
    lane.classList.add('released');
    K.sfx.drop();
    K.say('先看谁落地，再看路线和动作');
    draw();
    timer = setTimeout(() => {
      running = false;
      if (phase === 1) phase = 2;
      misses = 0;
      draw();
      K.say('把这一次看到的现象记下来');
    }, 2300);
  }

  function choose(index) {
    const row = observations[phase];
    if (!row || demo || running) return;
    if (index !== row.correct) {
      misses += 1;
      K.sfx.no();
      K.shake(buttons[index]);
      buttons[index].classList.add('hint');
      K.say(phase === 0 ? '沿起点线看一看' : '重看一次，留意这一处变化', 'no');
      if (misses > 1) K.highlight(phase === 0 ? '#trial-start-line' : '#trial-window');
      return;
    }
    if (phase > 1) {
      const tile = K.el('span', '', row.pictures[index], record);
      tile.setAttribute('aria-label', row.labels[index]);
    }
    K.star(1, buttons[index]);
    K.sfx.ok();
    phase += 1;
    misses = 0;
    draw();
    if (phase === 6) K.finish({title: '试飞记录好了', sub: '只记这一次看到的现象', again: reset});
  }

  buttons.forEach((button, index) => { button.onclick = () => choose(index); });
  release.onclick = () => animate();
  replay.onclick = () => animate();
  K.$$('.trial-strip img, .trial-rotor img').forEach((img) => {
    img.onerror = () => {
      if (img.parentElement.querySelector('.trial-retry')) return;
      const retry = K.el('button', 'trial-retry', '↻', img.parentElement);
      retry.setAttribute('aria-label', '重新加载' + img.alt);
      retry.onclick = () => { img.src = img.src; };
      img.onload = () => { retry.remove(); };
    };
  });
  K.hud({icon: '', title: '松手后看清楚', levels: 5});
  K.owl();
  K.onStart = reset;
  K.onState = (state) => {
    if (state.trialDemo === false) reset();
    if (state.trialDemo === 'set') { reset(); demo = true; phase = 1; draw(); }
    if (state.trialDemo === 'drop') { demo = true; phase = 1; animate(true); }
    if (state.trialDemo === 'record') { demo = true; phase = 2; draw(); }
  };
  reset();
  K.ready({emoji: '↻', title: '松手后看清楚', sub: '看两件作品在空中怎样动'});
})();
