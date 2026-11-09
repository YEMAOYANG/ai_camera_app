const config = {
  "key": "find-places",
  "title": "听声音，收进路线",
  "label": "参观路线",
  "layout": "album",
  "rewardTitle": "我的参观册",
  "optionIds": [
    "find-school",
    "find-classroom"
  ],
  "assets": {
    "school": {
      "src": "__IMG:school__",
      "alt": "校园外景"
    },
    "classroom": {
      "src": "__IMG:classroom__",
      "alt": "教室内景"
    }
  },
  "rounds": [
    {
      "cue": "/api/classroom-media/__STAGE__/media/tts-find-places-11-7f7974e41f248589c280faae9bc78a924989d39d1e9f14302b4397636898b4de.wav",
      "target": "classroom",
      "options": [
        "school",
        "classroom"
      ]
    },
    {
      "cue": "/api/classroom-media/__STAGE__/media/tts-find-places-12-c013074403998ea4356f4b291eabd7bc0531c1afcd3c0075a2eaca300dc5aae0.wav",
      "target": "school",
      "options": [
        "school",
        "classroom"
      ]
    }
  ],
  "demo": {
    "school": {
      "index": 1,
      "asset": "school"
    },
    "classroom": {
      "index": 0,
      "asset": "classroom"
    }
  },
  "correct": "照片放进参观册了。",
  "hint": "再听一次。看看画面在室内还是室外。",
  "finish": "参观路线准备好了"
};

(() => {
  const choices = config.optionIds.map(id => K.$('#' + id));
  const replay = K.$('#tour-listen');
  const gallery = K.$('.tour-gallery');
  let round = 0;
  let mode = 'practice';
  let heard = false;
  let busy = false;
  let attempts = 0;
  let clip = null;
  let timer = null;

  function image(key) {
    const img = document.createElement('img');
    img.src = config.assets[key].src;
    img.alt = config.assets[key].alt;
    img.draggable = false;
    img.addEventListener('error', () => {
      if (img.parentElement) img.parentElement.classList.add('tour-image-missing');
      K.say('图片暂未加载，请稍后重试。', 'no');
    }, {once:true});
    return img;
  }

  function place(index, key) {
    const cell = gallery.children[index];
    cell.replaceChildren(...(key ? [image(key)] : []));
    cell.classList.toggle('has-photo', Boolean(key));
  }

  function updateControls() {
    for (const choice of choices) choice.disabled = mode !== 'practice' || !heard || busy;
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
      K.say('听到了，选对应的画。');
    };
    audio.onerror = failed;
    audio.play().catch(failed);
  }

  function renderRound() {
    const task = config.rounds[round];
    choices.forEach((choice, i) => {
      const key = task.options[i];
      choice.dataset.asset = key;
      choice.setAttribute('aria-label', config.assets[key].alt);
      choice.classList.remove('correct', 'wrong', 'tour-image-missing');
      choice.replaceChildren(image(key));
    });
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
    attempts = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    place(0, config.initial || null);
    place(1, null);
  }

  function reset() {
    mode = 'practice';
    clearProgress();
    K.$$('#play .teach-hl').forEach(element => element.classList.remove('teach-hl'));
    renderRound();
    K.say('点声音按钮，听这一轮。');
  }

  function choose(choice) {
    if (mode !== 'practice' || !heard || busy) return;
    choices.forEach(el => el.classList.remove('wrong'));
    const task = config.rounds[round];
    if (choice.dataset.asset !== task.target) {
      attempts += 1;
      choice.classList.add('wrong');
      K.shake(choice);
      K.sfx.no();
      K.say(attempts === 1 ? '可以再试，也可以再听。' : config.hint, 'no');
      return;
    }
    choice.classList.add('correct');
    busy = true;
    stopCue();
    updateControls();
    K.sfx.ok();
    K.star(1, choice);
    place(round, task.target);
    K.levels(config.rounds.length, round + 1);
    K.say(config.correct, 'ok');
    timer = setTimeout(() => {
      if (round + 1 === config.rounds.length) {
        mode = 'finished';
        updateControls();
        K.finish({title:config.finish, sub:'你听完两轮，完成了导览任务。', again:reset});
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

  K.hud({title:config.label, icon:'', levels:config.rounds.length});
  K.owl();
  K.ready({title:config.label, sub:'点开始，听老师读题。', emoji:'看图听课'});
  K.onStart = reset;
  K.onState = state => {
    if (state.mode === 'practice') {
      reset();
      return;
    }
    if (state.mode !== 'demo' || !config.demo[state.choice]) return;
    clearProgress();
    mode = 'demo';
    const demo = config.demo[state.choice];
    round = demo.index;
    renderRound();
    place(demo.index, demo.asset);
    K.say('先看老师怎样做。');
  };
  replay.addEventListener('click', hear);
  choices.forEach(choice => choice.addEventListener('click', () => choose(choice)));
  window.addEventListener('pagehide', stopCue);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !clip) return;
    stopCue();
    heard = false;
    updateControls();
  });
  reset();
})();
