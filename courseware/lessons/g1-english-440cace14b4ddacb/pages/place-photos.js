const config = {
  "rounds": [
    {
      "target": "photo-one",
      "src": "__IMG:classroom__",
      "alt": "上课的教室照片",
      "cue": "/api/classroom-media/__STAGE__/media/tts-place-photos-10-f5395b96aa8e5167b91a5ac9f954346677c181f9e6869490ca9d39fce0485976.wav"
    },
    {
      "target": "photo-group",
      "src": "__IMG:classroom__",
      "alt": "同一间上课的教室照片",
      "cue": "/api/classroom-media/__STAGE__/media/tts-place-photos-11-2cfac31b76063931736ab88338aa70ab9d8a3af5da2eedc7d24f1035a4988cab.wav"
    }
  ]
};
(() => {
  const card = K.$('#photo-card');
  const replay = K.$('#tour-listen');
  const targets = [K.$('#photo-one'), K.$('#photo-group')];
  let mode = 'practice';
  let round = 0;
  let heard = false;
  let busy = false;
  let selected = false;
  let attempts = 0;
  let clip = null;
  let timer = null;

  function photo(task) {
    const img = document.createElement('img');
    img.src = task.src;
    img.alt = task.alt;
    img.draggable = false;
    img.addEventListener('error', () => K.say('照片暂未加载，请稍后重试。', 'no'), {once:true});
    return img;
  }

  function place(target, task) {
    const slot = K.$('.photo-slot', target);
    slot.replaceChildren(...(task ? [photo(task)] : []));
    slot.classList.toggle('has-photo', Boolean(task));
  }

  function canChoose() {
    return mode === 'practice' && heard && !busy;
  }

  function updateControls() {
    card.disabled = !canChoose();
    card.classList.toggle('is-selected', selected);
    card.setAttribute('aria-pressed', String(selected));
    targets.forEach(target => { target.disabled = !canChoose(); });
    const playingCue = clip !== null;
    replay.disabled = mode !== 'practice' || busy || playingCue;
    replay.setAttribute('aria-busy', String(playingCue));
    replay.classList.toggle('needs-cue', mode === 'practice' && !heard && !busy && !playingCue);
  }

  function stopCue() {
    if (!clip) return;
    clip.onended = null;
    clip.onerror = null;
    clip.pause();
    clip = null;
  }

  function hear() {
    if (mode !== 'practice' || busy || clip) return;
    selected = false;
    const url = config.rounds[round].cue;
    const audio = new Audio(url);
    clip = audio;
    updateControls();
    const failed = () => {
      if (clip !== audio) return;
      stopCue();
      K.say('声音暂时没播出来。请再点声音按钮。', 'no');
      updateControls();
    };
    audio.onended = () => {
      if (clip !== audio) return;
      stopCue();
      heard = true;
      updateControls();
      K.say('可以拖照片，也可以先点照片再点人。');
    };
    audio.onerror = failed;
    audio.play().catch(failed);
  }

  function renderRound() {
    const task = config.rounds[round];
    card.replaceChildren(photo(task));
    card.setAttribute('aria-label', task.alt);
    targets.forEach(target => target.classList.remove('wrong'));
    K.levels(config.rounds.length, round);
    updateControls();
  }

  function clearProgress() {
    clearTimeout(timer);
    stopCue();
    K.$('#finish')?.classList.add('gone');
    round = 0;
    heard = false;
    busy = false;
    selected = false;
    attempts = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    targets.forEach(target => place(target, null));
  }

  function reset() {
    mode = 'practice';
    clearProgress();
    K.$$('#play .teach-hl').forEach(element => element.classList.remove('teach-hl'));
    renderRound();
    K.say('点声音按钮，听这一轮。');
  }

  function selectCard() {
    if (!canChoose()) return;
    selected = true;
    updateControls();
    K.sfx.pick();
    K.say('把照片送到一张人物图。');
  }

  function deliver(target) {
    if (!canChoose()) return;
    if (!target) {
      K.say('请把照片拖到一张人物图上。');
      return;
    }
    targets.forEach(el => el.classList.remove('wrong'));
    const task = config.rounds[round];
    if (target.id !== task.target) {
      attempts += 1;
      target.classList.add('wrong');
      K.shake(target);
      K.sfx.no();
      K.say(attempts === 1 ? '可以再试，也可以再听。' : '再听 my 或 our，想想从谁的角度介绍。', 'no');
      return;
    }
    selected = false;
    busy = true;
    stopCue();
    updateControls();
    place(target, task);
    card.replaceChildren();
    K.sfx.ok();
    K.star(1, target);
    K.levels(config.rounds.length, round + 1);
    K.say('照片送到了。', 'ok');
    timer = setTimeout(() => {
      if (round + 1 === config.rounds.length) {
        mode = 'finished';
        updateControls();
        K.finish({title:'照片送到了', sub:'两张照片进了导览册。', again:reset});
        return;
      }
      round += 1;
      heard = false;
      busy = false;
      attempts = 0;
      renderRound();
      K.say('点声音按钮，听下一轮。');
    }, round + 1 === config.rounds.length ? 1100 : 650);
  }

  K.hud({title:'送照片',icon:'',levels:config.rounds.length});
  K.owl();
  K.ready({title:'送照片',sub:'点开始，听老师读题。',emoji:'看图听课'});
  K.onStart = reset;
  K.onState = state => {
    if (state.mode === 'practice') {
      reset();
      return;
    }
    if (state.mode !== 'demo' || !['solo', 'group'].includes(state.choice)) return;
    clearProgress();
    mode = 'demo';
    round = state.choice === 'solo' ? 0 : 1;
    renderRound();
    place(targets[round], config.rounds[round]);
    K.say('先看老师怎样送照片。');
  };
  K.drag(card, {
    enabled:canChoose,
    targets:() => targets,
    onTap:selectCard,
    onDrop:(_, target) => deliver(target)
  });
  card.addEventListener('keydown', event => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    selectCard();
  });
  targets.forEach(target => target.addEventListener('click', () => {
    if (selected) deliver(target);
    else if (canChoose()) K.say('先点照片，再点人物图。');
  }));
  replay.addEventListener('click', hear);
  K.$$('.photo-target > img').forEach(img => img.addEventListener('error', () => {
    img.parentElement.classList.add('tour-image-missing');
    K.say('人物照片暂未加载，请稍后重试。', 'no');
  }, {once:true}));
  window.addEventListener('pagehide', stopCue);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !clip) return;
    stopCue();
    heard = false;
    updateControls();
  });
  reset();
})();
