(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('game-config').textContent);
  const game = document.getElementById('game-layout');
  const sound = document.getElementById('sound');
  const cue = document.getElementById('speaker-cue');
  const next = document.getElementById('next-round');
  const stamp = document.getElementById('stamp');
  const slot = document.getElementById('photo-slot');
  const slotPicture = document.getElementById('slot-picture');
  const slotOriginal = slotPicture?.getAttribute('src');
  const targets = Array.from(game.querySelectorAll('[data-choice]'));
  const byKey = new Map(targets.map(target => [target.dataset.choice, target]));
  const trial = () => config.trials[round];
  let round = 0;
  let misses = 0;
  let active = false;
  let accepted = false;
  let clip = null;

  K.hud({icon:'', title:config.title, levels:config.trials.length});
  K.owl();
  K.ready({emoji:'', title:config.title, sub:'', btn:'start-btn'});

  function stopAudio() {
    if (!clip) return;
    clip.pause();
    clip.currentTime = 0;
    clip = null;
  }
  function replay() {
    stopAudio();
    if (!active || accepted || !trial().audio || trial().audio.startsWith('__VOICE:')) return;
    clip = new Audio(trial().audio);
    const current = clip;
    current.addEventListener('error', () => sound.classList.add('audio-error'), {once:true});
    current.play().then(() => {
      if (current === clip) sound.classList.remove('audio-error');
    }).catch(() => {
      if (current === clip) sound.classList.add('audio-error');
    });
  }
  function speaker(key) {
    cue.textContent = key === 'a' ? '小橙开口' : key === 'b' ? '小青开口' : '';
    game.querySelectorAll('.portrait').forEach(portrait => {
      portrait.classList.toggle('speaker', key && portrait.id === 'maker-' + key);
    });
  }
  function clearPicture() {
    targets.forEach(target => target.classList.remove('selected', 'hinted'));
    if (slotPicture) {
      slotPicture.src = slotOriginal;
      slotPicture.alt = '橙围裙孩子';
      slot.classList.remove('selected');
    }
  }
  function showPicture(key) {
    const target = byKey.get(key);
    if (!target) return;
    target.classList.add('selected');
    if (slotPicture) {
      const photo = target.querySelector('img');
      slotPicture.src = photo.src;
      slotPicture.alt = photo.alt;
      slot.classList.add('selected');
    }
  }
  function paintRound() {
    misses = 0;
    accepted = false;
    next.hidden = true;
    clearPicture();
    speaker(active ? trial().speaker : null);
    K.levels(config.trials.length, round);
    K.say(active ? '听清录音，再看照片上的位置。' : '先看老师怎样找照片。');
  }
  function begin() {
    stopAudio();
    active = true;
    round = 0;
    K.stars = 0;
    document.getElementById('star-n').textContent = '0';
    paintRound();
    replay();
  }
  function choose(key) {
    const chosen = byKey.get(key);
    if (!active || accepted || !chosen || game.classList.contains('picture-error')) return;
    if (key !== trial().key) {
      misses++;
      K.sfx.no();
      if (config.mode !== 'lights') K.shake(chosen);
      K.say(misses === 1 ? '再听一遍，先找声音里的线索。' : '先看是哪一个人，再找照片上的位置。', 'no');
      if (misses >= 3) byKey.get(trial().key).classList.add('hinted');
      replay();
      return;
    }
    accepted = true;
    stopAudio();
    showPicture(key);
    K.star(1, chosen);
    K.sfx.ok();
    K.say(config.mode === 'stamp' ? '照片上的印章盖好了。' : '找到这一处了，继续听下一轮。', 'ok');
    next.hidden = false;
  }
  function advance() {
    if (!accepted) return;
    if (round + 1 < config.trials.length) {
      round++;
      paintRound();
      replay();
      return;
    }
    next.hidden = true;
    active = false;
    K.levels(config.trials.length, config.trials.length);
    K.finish({title:'照片任务完成', sub:'已记录这次听选。你可以再玩一次。', again:begin});
  }
  targets.forEach(target => target.addEventListener('click', () => choose(target.dataset.choice)));
  if (stamp) {
    K.drag(stamp, {
      enabled:() => active && !accepted,
      targets:() => targets,
      onTap:() => K.say('把印章拖到照片，也可以点照片。'),
      onDrop:(_piece, target) => target ? choose(target.dataset.choice) : K.sfx.drop(),
    });
  }
  game.querySelectorAll('img').forEach(image => image.addEventListener('error', () => game.classList.add('picture-error')));
  sound.addEventListener('click', replay);
  next.addEventListener('click', advance);
  document.getElementById('start-btn').addEventListener('click', begin);
  K.onState = state => {
    if (Object.prototype.hasOwnProperty.call(state, 'demo')) {
      active = false;
      stopAudio();
      paintRound();
      if (state.demo) {
        if (config.mode === 'stamp') speaker('a');
        showPicture(state.demo);
      }
    }
    if (state.handoff === true) begin();
    if (state.handoff === false) {
      active = false;
      stopAudio();
    }
  };
  window.addEventListener('message', event => {
    if (event.data?.type === 'PAUSE_WIDGET_AUDIO') stopAudio();
  });
  window.addEventListener('pagehide', stopAudio);

  window.__test = async () => {
    const checks = [];
    const check = (label, condition) => K.check(checks, label, condition);
    K.sim.click(document.getElementById('start-btn'));
    const incorrect = targets.find(target => target.dataset.choice !== trial().key);
    K.sim.click(incorrect);
    check('first wrong leaves the answer hidden', !game.querySelector('.selected,.hinted') && K.stars === 0 && next.hidden);
    await K.cp('first-wrong');
    const demo = config.mode === 'stamp' ? 'a-nose' : config.mode === 'cards' ? 'face' : 'nose';
    K.onState({demo});
    check('teacher visibly marks the image', byKey.get(demo).classList.contains('selected'));
    await K.cp('teacher-demo');
    K.onState({demo:null, handoff:true});
    for (let i = 0; i < config.trials.length; i++) {
      const answer = byKey.get(trial().key);
      K.sim.click(answer);
      check('correct answer marks the picture ' + i, answer.classList.contains('selected') && K.stars === i + 1 && !next.hidden);
      if (i === 0) await K.cp('correct');
      K.sim.click(next);
    }
    check('finish visible', !document.getElementById('finish')?.classList.contains('gone'));
    await K.cp('finish');
    K.sim.click(document.getElementById('btn-again'));
    check('replay clears all progress', round === 0 && K.stars === 0 && !game.querySelector('.selected,.hinted') && next.hidden);
    await K.cp('reset');
    stopAudio();
    return checks;
  };
  paintRound();
})();
