(() => {
  'use strict';
  const title = '把成对的部位装到模型上';
  const trials = [
    {keys:['hand-l','hand-r'],audio:'__VOICE:p07-14__'},
    {keys:['leg-l','leg-r'],audio:'__VOICE:p07-15__'},
    {keys:['foot-l','foot-r'],audio:'__VOICE:p07-16__'}
  ];
  const pieces = K.$$('.assembly-piece');
  const docks = K.$$('.assembly-dock');
  const pieceFor = new Map(pieces.map(piece => [piece.dataset.part,piece]));
  const dockFor = new Map(docks.map(dock => [dock.dataset.dock,dock]));
  const shell = K.$('#model-shell');
  const sound = K.$('#assembly-sound');
  const next = K.$('#assembly-next');
  const placed = new Set();
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
  function showPiece(key) {
    const piece = pieceFor.get(key);
    const dock = dockFor.get(key);
    const image = piece.querySelector('img');
    const inserted = dock.querySelector('img');
    inserted.src = image.src;
    inserted.alt = image.alt;
    inserted.hidden = false;
    dock.classList.add('filled');
    piece.classList.remove('hinted');
    piece.disabled = true;
    placed.add(key);
  }
  function setRound() {
    misses = 0;
    next.hidden = true;
    pieces.forEach(piece => piece.classList.remove('hinted'));
    K.levels(trials.length,round);
    K.say(imageError ? '部件图没有打开，请重新进入。' : '先听口令，再找两块图。');
  }
  function begin() {
    active = true;
    round = 0;
    placed.clear();
    pieces.forEach(piece => { piece.disabled = imageError; });
    docks.forEach(dock => {
      const image = dock.querySelector('img');
      image.hidden = true;
      image.removeAttribute('src');
      dock.classList.remove('filled');
    });
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    setRound();
    replay();
  }
  function choose(piece,dock) {
    const key = piece.dataset.part;
    if (!active || !next.hidden || placed.has(key) || imageError) return;
    const remaining = trials[round].keys.filter(part => !placed.has(part));
    if (!remaining.includes(key) || dock?.dataset.dock !== key) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '还没装进去，重新听一听。' : '先分清是哪一对，再看空槽。','no');
      if (misses >= 3) remaining.forEach(part => pieceFor.get(part).classList.add('hinted'));
      replay();
      return;
    }
    showPiece(key);
    K.star(1,dock);
    K.sfx.ok();
    if (remaining.length === 1) {
      stopAudio();
      next.hidden = false;
      K.say('两个位置都装好了！','ok');
    } else {
      K.say('装好一边了，再找另一块。','ok');
    }
  }
  pieces.forEach(piece => {
    K.drag(piece,{
      enabled:() => active && next.hidden && !piece.disabled && !imageError,
      targets:() => docks,
      onTap:() => choose(piece,dockFor.get(piece.dataset.part)),
      onDrop:(_,dock) => choose(piece,dock)
    });
    piece.addEventListener('click',event => {
      if (event.detail === 0) choose(piece,dockFor.get(piece.dataset.part));
    });
  });
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
    K.finish({title:'模型的三对部件装齐了',sub:'看一看，两只手、两条腿和两只脚。',again:begin});
  });
  [shell,...pieces.map(piece => piece.querySelector('img'))].forEach(image => image.addEventListener('error',() => {
    imageError = true;
    pieces.forEach(piece => { piece.disabled = true; });
    K.say('部件图没有打开，请重新进入。','no');
  }));
  K.onState = (state) => {
    if (state.demo && !imageError) {
      active = false;
      stopAudio();
      showPiece(state.demo);
    }
    if (state.handoff) begin();
  };
  K.$('#start-btn').addEventListener('click',begin);
  sound.addEventListener('click',replay);
  window.addEventListener('message',event => { if (event.data?.type === 'PAUSE_WIDGET_AUDIO') stopAudio(); });
  window.addEventListener('pagehide',stopAudio);
  setRound();
})();
