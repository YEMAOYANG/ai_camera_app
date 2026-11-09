(() => {
  const K = window.K;
  const lane = K.$('#test-lane');
  const pathCard = K.$('#test-path');
  const frames = K.$('#test-motion-frames');
  const options = K.$('#test-options');
  const buttons = [K.$('#test-a'), K.$('#test-b')];
  const release = K.$('#test-release');
  const again = K.$('#test-watch');
  const retry = K.$('#test-retry');
  const record = K.$('#test-record');
  const slots = [...record.children];
  const prompt = K.$('#test-prompt');
  const phases = {
    0:{title:'看两只手的起点', correct:1, pictures:['__IMG:setup-high__','__IMG:setup-same__'], alt:['起点一个高一个低','从同样高度一起放落'], hint:'沿着那条起点线比一比。'},
    2:{title:'飞翼翻到下面了吗', correct:0, pictures:['__IMG:motion-upright__','__IMG:motion-flip__'], alt:['飞翼一直在上','飞翼上下翻动'], hint:'重看飞翼有没有翻到纸身下面。'},
    3:{title:'走过的路线稳不稳', correct:1, pictures:['__IMG:motion-steady__','__IMG:motion-sway__'], alt:['路线比较稳','路线左右飘'], hint:'再看纸蜻蜓经过哪些地方。'},
    4:{title:'飞翼有没有绕着转', correct:0, pictures:['__IMG:motion-spin__','__IMG:motion-still__'], alt:['飞翼绕身子转','飞翼方向不变'], hint:'重看飞翼的方向有没有变。'},
  };
  const broken = new Set();
  let phase = 0;
  let demo = false;
  let running = false;
  let misses = 0;
  let timer;

  function disableForMedia() {
    const blocked = demo || running || broken.size > 0;
    retry.classList.toggle('hide', !broken.size);
    [release, again, ...buttons].forEach(control => { control.disabled = blocked; });
  }

  function monitor(img) {
    img.addEventListener('error', () => { broken.add(img); disableForMedia(); });
    img.addEventListener('load', () => { broken.delete(img); disableForMedia(); });
  }

  function draw() {
    const row = phases[phase];
    K.levels(4, Math.max(0, phase - (phase > 1 ? 1 : 0)));
    options.classList.toggle('hide', running || !row);
    release.classList.toggle('hide', running || phase !== 1);
    again.classList.toggle('hide', running || phase < 2 || phase > 4);
    pathCard.classList.toggle('hide', running || phase !== 3);
    frames.classList.toggle('hide', running || phase < 2 || phase > 4);
    if (phase >= 2 && phase <= 4 && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const graphic = row.pictures[row.correct];
      if (frames.getAttribute('src') !== graphic) { broken.delete(frames); frames.src = graphic; }
      frames.alt = '同一次飞行的三个瞬间';
    }
    prompt.textContent = running ? '看它们落下来' : row?.title || (phase === 1 ? '一起轻轻松手' : '这次观察都记好了');
    if (row) buttons.forEach((button,i) => {
      const img = button.querySelector('img');
      if (img.getAttribute('src') !== row.pictures[i]) {
        broken.delete(img);
        img.src = row.pictures[i];
      }
      img.alt = row.alt[i];
      button.setAttribute('aria-label', row.alt[i]);
    });
    disableForMedia();
  }

  function reset() {
    clearTimeout(timer);
    phase = 0;
    misses = 0;
    running = false;
    demo = false;
    lane.classList.remove('falling');
    lane.classList.add('is-low');
    record.querySelectorAll('img').forEach(img => broken.delete(img));
    slots.forEach(slot => { slot.replaceChildren(); slot.classList.remove('filled'); });
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    draw();
    K.say('先把两件纸蜻蜓摆到一样高');
  }

  function fly(forTeacher = false) {
    if (running || broken.size || (demo && !forTeacher)) return;
    clearTimeout(timer);
    running = true;
    lane.classList.remove('is-low','falling');
    void lane.offsetWidth;
    lane.classList.add('falling');
    K.sfx.drop();
    draw();
    timer = setTimeout(() => {
      running = false;
      if (phase < 2) phase = 2;
      draw();
      K.say('按这一次看到的样子记录');
    },1270);
  }

  function addObservation(current, row, index) {
    const slot = slots[current - 2];
    if (slot.firstChild) broken.delete(slot.firstChild);
    slot.replaceChildren();
    slot.classList.add('filled');
    const item = K.el('img','',null,slot);
    monitor(item);
    item.alt = row.alt[index];
    item.src = row.pictures[index];
  }

  function choose(i) {
    const row = phases[phase];
    if (!row || demo || running || broken.size) return;
    if (i !== row.correct) {
      misses += 1;
      K.shake(buttons[i]);
      K.sfx.no();
      K.say(row.hint,'no');
      if (misses > 1) K.highlight(phase === 0 ? '#test-level' : '#test-lane');
      return;
    }
    K.star(1,buttons[i]);
    K.sfx.ok();
    if (phase === 0) {
      lane.classList.remove('is-low');
    } else {
      addObservation(phase, row, i);
    }
    misses = 0;
    phase += 1;
    draw();
    if (phase === 5) K.finish({title:'三项都记好了', sub:'说出自己看到的现象', again:reset});
  }

  K.$$('.flight-table img').forEach(monitor);
  retry.onclick = () => broken.forEach(img => { img.src = img.getAttribute('src'); });
  buttons.forEach((button,i) => { button.onclick = () => choose(i); });
  release.onclick = () => fly();
  again.onclick = () => fly();
  K.hud({icon:'',title:'同高松手，再看再记',levels:4});
  K.owl();
  K.onStart = reset;
  K.onState = (state) => {
    if (state.flightDemo === false) reset();
    if (state.flightDemo === 'align') { reset(); demo = true; phase = 1; lane.classList.remove('is-low'); draw(); }
    if (state.flightDemo === 'drop') { demo = true; phase = 1; fly(true); }
    if (state.flightDemo === 'record') {
      demo = true;
      phase = 3;
      for (const turn of [2,3,4]) addObservation(turn, phases[turn], phases[turn].correct);
      draw();
    }
  };
  reset();
  K.ready({emoji:'',title:'同高松手，再看再记',sub:'听老师示范，再看飞翼怎样动'});
})();
