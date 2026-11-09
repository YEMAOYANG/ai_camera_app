const config = {
  "key": "welcome-guest",
  "title": "听声音，迎接新客人",
  "label": "学校开放日",
  "layout": "visit",
  "rewardTitle": "迎客记录",
  "optionIds": [
    "guest-person",
    "guest-action"
  ],
  "assets": {
    "child": {
      "src": "__IMG:child__",
      "alt": "站在课桌旁的孩子"
    },
    "teacher": {
      "src": "__IMG:teacher__",
      "alt": "给学生上课的老师"
    },
    "guest-door": {
      "src": "__IMG:guest-door__",
      "alt": "孩子带客人走到教室门口"
    },
    "greeting": {
      "src": "__IMG:greeting__",
      "alt": "客人与老师面对面问候"
    },
    "solo-desk": {
      "src": "__IMG:solo-desk__",
      "alt": "孩子独自在自己的课桌旁"
    }
  },
  "rounds": [
    {
      "cue": "/api/classroom-media/__STAGE__/media/tts-welcome-guest-9-194eae8ffca34a10a02eb164fada8518e2ed4e3af4faf32af21d66fa9d307923.wav",
      "target": "teacher",
      "options": [
        "teacher",
        "child"
      ]
    },
    {
      "cue": "/api/classroom-media/__STAGE__/media/tts-welcome-guest-10-d2ffdb59cae56747c7a12ad4cc62b626b05af55c640afa626a246314ed96bb57.wav",
      "target": "greeting",
      "options": [
        "solo-desk",
        "greeting"
      ]
    }
  ],
  "demo": {
    "intro": {
      "index": 0,
      "asset": "guest-door"
    },
    "greeting": {
      "index": 1,
      "asset": "greeting"
    }
  },
  "initial": "guest-door",
  "correct": "迎客记录添了一幅画。",
  "hint": "再听一次。看画面里的人在做什么。",
  "finish": "客人来参观了"
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
