(() => {
  'use strict';
  const title = '听口令指模型的部位';
  const trials = [
    {keys:['leg-l','leg-r'],needed:1,audio:'__VOICE:p09-14__'},
    {keys:['hand-l','hand-r'],needed:2,audio:'__VOICE:p09-15__'},
    {keys:['head'],needed:1,audio:'__VOICE:p09-16__'},
    {keys:['foot-l','foot-r'],needed:2,audio:'__VOICE:p09-17__'}
  ];
  const targets = K.$$('.pointer-target');
  const byKey = new Map(targets.map(target => [target.dataset.part,target]));
  const selected = new Set();
  const next = K.$('#pointer-next');
  const sound = K.$('#pointer-sound');
  const image = K.$('#pointer-body img');
  let round = 0;
  let misses = 0;
  let active = false;
  let imageError = false;
  let clip = null;
  K.hud({icon:'',title,levels:trials.length});
  K.owl();
  K.ready({emoji:'',title,sub:'',btn:'start-btn'});

  function stopAudio() {
    if (clip) clip.pause();
    clip = null;
  }
  function replay() {
    stopAudio();
    if (!active || !next.hidden || trials[round].audio.startsWith('__VOICE:')) return;
    clip = new Audio(trials[round].audio);
    const current = clip;
    current.play().then(() => sound.classList.remove('audio-error')).catch(() => {
      if (clip === current) sound.classList.add('audio-error');
    });
  }
  function clearSelection() {
    selected.clear();
    targets.forEach(target => {
      target.classList.remove('chosen','hinted');
      target.setAttribute('aria-pressed','false');
    });
  }
  function mark(target) {
    selected.add(target.dataset.part);
    target.classList.remove('hinted');
    target.classList.add('chosen');
    target.setAttribute('aria-pressed','true');
  }
  function setRound() {
    misses = 0;
    next.hidden = true;
    clearSelection();
    K.levels(trials.length,round);
    K.say(imageError ? '小宇的图还没打开，请重新进入。' : '听口令，在小宇的图上点。');
  }
  function begin() {
    active = true;
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    setRound();
    replay();
  }
  targets.forEach(target => target.addEventListener('click',() => {
    if (!active || !next.hidden || imageError) return;
    const key = target.dataset.part;
    const trial = trials[round];
    if (selected.has(key)) {
      K.say('这里已经亮了。再听听还要不要指另一处。');
      return;
    }
    if (!trial.keys.includes(key)) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '再听一遍，先找是哪个部位。' : '听清要找一个还是多个。','no');
      if (misses >= 3) trial.keys.filter(part => !selected.has(part)).forEach(part => byKey.get(part).classList.add('hinted'));
      replay();
      return;
    }
    mark(target);
    K.sfx.tick(selected.size - 1);
    if (selected.size < trial.needed) {
      K.say('点亮一处了，还要找到另一处。','ok');
      return;
    }
    stopAudio();
    K.star(1,target);
    K.say('这一轮指对了！','ok');
    next.hidden = false;
  }));
  next.addEventListener('click',() => {
    if (next.hidden) return;
    round++;
    if (round < trials.length) {
      setRound();
      replay();
      return;
    }
    active = false;
    next.hidden = true;
    K.levels(trials.length,trials.length);
    K.finish({title:'小宇的部位都指到了',sub:'你完成了这次听音指认。',again:begin});
  });
  image.addEventListener('error',() => {
    imageError = true;
    targets.forEach(target => { target.disabled = true; });
    K.say('小宇的图还没打开，请重新进入。','no');
  });
  K.onState = (state) => {
    if (state.demo && !imageError) {
      if (active || state.demo === 'head' || state.demo === 'hand-l') clearSelection();
      active = false;
      stopAudio();
      next.hidden = true;
      mark(byKey.get(state.demo));
    }
    if (state.handoff) begin();
  };
  K.$('#start-btn').addEventListener('click',begin);
  sound.addEventListener('click',replay);
  window.addEventListener('message',event => { if (event.data?.type === 'PAUSE_WIDGET_AUDIO') stopAudio(); });
  window.addEventListener('pagehide',stopAudio);
  setRound();
})();
