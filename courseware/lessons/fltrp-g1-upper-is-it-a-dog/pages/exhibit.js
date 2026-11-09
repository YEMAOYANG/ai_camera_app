(() => {
  const objects = {
    dog: ['__IMG:dog__', '四脚站在地上的小狗'],
    monkey: ['__IMG:monkey__', '抓着树枝的猴子'],
    monster: ['__IMG:monster__', '想象故事里的怪兽玩偶'],
    kite: ['__IMG:kite__', '带有牵线和尾带的风筝'],
    'dog-kite': ['__IMG:dog-kite__', '画着狗脸并连着线轴的风筝'],
  };
  const activities = {
    '听猜测，再揭图': {
      kind: 'reveal',
      rounds: [
        { guess:'dog', object:'monkey', other:'kite', cue:'/api/classroom-media/__STAGE__/media/tts-hear-and-reveal-11-c70ee10f96f5092aef20e25cde22128cd11a47e3c4e4b46eb270bb43b46dcf87.wav' },
        { guess:'kite', object:'kite', other:'monster', cue:'/api/classroom-media/__STAGE__/media/tts-hear-and-reveal-12-767d9369fe14f908d31f7ba3fac6c1f20772ca546230fea7b4541cb7b585f4c9.wav' },
      ],
    },
    '把真实照片放上展台': {
      kind: 'sort',
      rounds: [
        { guess:'dog', object:'dog-kite', other:'monkey', cue:'/api/classroom-media/__STAGE__/media/tts-hear-and-reveal-11-c70ee10f96f5092aef20e25cde22128cd11a47e3c4e4b46eb270bb43b46dcf87.wav' },
        { guess:'kite', object:'kite', other:'dog', cue:'/api/classroom-media/__STAGE__/media/tts-hear-and-reveal-12-767d9369fe14f908d31f7ba3fac6c1f20772ca546230fea7b4541cb7b585f4c9.wav' },
      ],
    },
    '轮流问，轮流答': {
      kind: 'roles',
      rounds: [
        { guess:'dog', object:'kite', other:'monkey', cue:'/api/classroom-media/__STAGE__/media/tts-hear-and-reveal-11-c70ee10f96f5092aef20e25cde22128cd11a47e3c4e4b46eb270bb43b46dcf87.wav' },
        { guess:'monkey', object:'monkey', other:'dog', cue:'/api/classroom-media/__STAGE__/media/tts-trade-roles-13-105765d729e41860b9c71fcd9a575a77f67577158abb71d6379149484c63f5d1.wav' },
      ],
    },
  };
  const name = document.title;
  const activity = activities[name];
  if (!activity) throw new Error('Missing exhibit activity configuration');

  const cueButton = K.$('#listen-cue');
  const guessFrame = K.$('#guess-photo');
  const card = K.$('#exhibit-target');
  const options = K.$('#match-options');
  const choices = [K.$('#match-left'), K.$('#match-right')];
  const slots = K.$$('#evidence-photos .photo-frame');
  const retry = K.$('#retry-art');
  let mode = 'practice';
  let phase = 'listen';
  let round = 0;
  let attempts = 0;
  let selected = false;
  let clip = null;
  let timer = null;
  let imageErrors = false;
  let retryCount = 0;
  const awards = [];

  function task() {
    return activity.rounds[round];
  }

  function canPlay() {
    return mode === 'practice' && !imageErrors;
  }

  function showingChoices() {
    return phase === 'guess' || phase === 'answer' || phase === 'award';
  }

  function canSort() {
    return canPlay() && activity.kind === 'sort' && phase === 'answer';
  }

  function objectImage(key) {
    const [src, alt] = objects[key];
    const image = document.createElement('img');
    image.src = retryCount ? src + '?attempt=' + retryCount : src;
    image.alt = alt;
    image.draggable = false;
    image.addEventListener('error', () => {
      if (!image.isConnected) return;
      imageErrors = true;
      K.say('照片没有打开。可以点重试。', 'no');
      syncControls();
    }, {once:true});
    return image;
  }

  function put(frame, key) {
    frame.replaceChildren(...(key ? [objectImage(key)] : []));
    frame.classList.toggle('has-photo', Boolean(key));
  }

  function syncControls() {
    cueButton.disabled = !canPlay() || clip !== null || phase === 'award' || phase === 'finished';
    cueButton.setAttribute('aria-busy', String(clip !== null));
    cueButton.classList.toggle('needs-cue', !cueButton.disabled && phase === 'listen');
    card.disabled = !(canPlay() && phase === 'reveal') && !canSort();
    card.classList.toggle('is-selected', selected);
    card.setAttribute('aria-pressed', String(selected));
    options.classList.toggle('is-waiting', !showingChoices());
    for (const choice of choices) {
      choice.disabled = !canPlay() || (phase !== 'guess' && phase !== 'answer');
    }
    retry.hidden = !imageErrors;
  }

  function render() {
    const current = task();
    const exposed = phase === 'answer' || phase === 'award' || phase === 'finished';
    put(guessFrame, phase === 'listen' || phase === 'guess' ? null : current.guess);
    card.classList.toggle('is-covered', !exposed);
    card.replaceChildren(...(exposed ? [objectImage(current.object)] : []));
    card.setAttribute('aria-label', exposed ? objects[current.object][1] : '揭开待检验的图');
    slots.forEach((slot, index) => put(slot, awards[index]));
    choices.forEach(choice => {
      choice.classList.remove('is-wrong', 'is-correct');
      choice.replaceChildren();
      choice.removeAttribute('aria-label');
    });
    if (phase === 'guess') {
      const pictures = round === 0 ? [current.other, current.guess] : [current.guess, current.other];
      choices.forEach((choice, index) => {
        const key = pictures[index];
        choice.dataset.choice = key;
        choice.setAttribute('aria-label', objects[key][1]);
        choice.append(objectImage(key));
      });
    }
    if (phase === 'answer' || phase === 'award') {
      const different = current.guess === current.object ? current.other : current.object;
      const outcomes = activity.kind === 'sort' ? ['different','same'] : ['same','different'];
      choices.forEach((choice, index) => {
        const same = outcomes[index] === 'same';
        const second = same ? current.guess : different;
        choice.dataset.choice = outcomes[index];
        choice.setAttribute('aria-label', objects[current.guess][1] + '和' + objects[second][1]);
        choice.append(objectImage(current.guess), objectImage(second));
      });
    }
    syncControls();
  }

  function stopCue() {
    if (!clip) return;
    clip.onended = null;
    clip.onerror = null;
    clip.pause();
    clip = null;
  }

  function hearCue() {
    if (cueButton.disabled) return;
    const src = task().cue;
    const playing = new Audio(src);
    clip = playing;
    syncControls();
    const failed = () => {
      if (clip !== playing) return;
      stopCue();
      syncControls();
      K.say('声音没有播出来。可以再点一次。', 'no');
    };
    playing.onerror = failed;
    playing.onended = () => {
      if (clip !== playing) return;
      stopCue();
      if (phase !== 'listen') {
        syncControls();
        return;
      }
      if (activity.kind === 'roles') {
        phase = 'guess';
        K.say('先选老师问到的东西。');
      } else if (activity.kind === 'sort') {
        phase = 'answer';
        K.say('拖照片，也可以先点照片再点一组。');
      } else {
        phase = 'reveal';
        K.say('点开遮住的照片。');
      }
      render();
    };
    playing.play().catch(failed);
  }

  function reveal() {
    if (!canPlay() || phase !== 'reveal') return;
    phase = 'answer';
    attempts = 0;
    render();
    K.say('看清照片，再选一组。');
  }

  function selectPhoto() {
    if (!canSort()) return;
    selected = true;
    syncControls();
    K.say('选一组，把照片送过去。');
  }

  function choose(choice) {
    if (!canPlay() || !choice || (phase !== 'guess' && phase !== 'answer')) return;
    const current = task();
    const expected = phase === 'guess' ? current.guess : current.guess === current.object ? 'same' : 'different';
    choices.forEach(button => button.classList.remove('is-wrong'));
    if (choice.dataset.choice !== expected) {
      attempts += 1;
      choice.classList.add('is-wrong');
      K.shake(choice);
      K.sfx.no();
      const hint = phase === 'guess' ? '再听问句里的最后一个词。' : '看完整照片，和猜到的东西比一比。';
      K.say(attempts === 1 ? '再试一次。' : hint, 'no');
      return;
    }
    if (phase === 'guess') {
      phase = 'reveal';
      render();
      K.say('问到的东西放好了。点开照片看看。');
      return;
    }
    selected = false;
    phase = 'award';
    stopCue();
    awards[round] = current.object;
    render();
    choice.classList.add('is-correct');
    K.star(1, choice);
    K.sfx.ok();
    K.levels(activity.rounds.length, round + 1);
    K.say('这张照片已经入册。', 'ok');
    timer = setTimeout(advance, 850);
  }

  function advance() {
    if (round + 1 === activity.rounds.length) {
      phase = 'finished';
      syncControls();
      K.finish({title:'展品入册了',sub:'你看清两张照片，也练过了问和答。',again:reset});
      return;
    }
    round += 1;
    attempts = 0;
    phase = 'listen';
    render();
    K.say('点声音按钮，听下一轮。');
  }

  function clearProgress() {
    clearTimeout(timer);
    stopCue();
    K.$('#finish')?.classList.add('gone');
    awards.length = 0;
    round = 0;
    attempts = 0;
    selected = false;
    imageErrors = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$$('#play .teach-hl').forEach(element => element.classList.remove('teach-hl'));
    K.levels(activity.rounds.length, 0);
  }

  function reset() {
    clearProgress();
    mode = 'practice';
    phase = 'listen';
    render();
    K.say('点声音按钮，听这一轮。');
  }

  K.$('#activity-heading').textContent = name;
  K.hud({title:'风筝展',icon:'',levels:activity.rounds.length});
  K.owl();
  K.ready({title:name,sub:'点开始，听老师读题。',emoji:'风筝展'});
  K.onStart = reset;
  K.onState = state => {
    if (state.mode === 'practice') {
      reset();
      return;
    }
    if (state.mode !== 'demo' || !activity.rounds[state.round]) return;
    clearProgress();
    mode = 'demo';
    round = state.round;
    phase = state.step === 'answer' ? 'answer' : activity.kind === 'roles' ? 'guess' : 'reveal';
    render();
    K.say('先看老师示范。');
  };
  cueButton.addEventListener('click', hearCue);
  card.addEventListener('click', () => phase === 'reveal' ? reveal() : selectPhoto());
  for (const choice of choices) {
    choice.addEventListener('click', () => {
      if (canSort() && !selected) {
        K.say('可以先点这张照片。');
        return;
      }
      choose(choice);
    });
  }
  K.drag(card, {
    enabled:canSort,
    targets:() => choices,
    onTap:selectPhoto,
    onDrop:(_, choice) => choose(choice),
  });
  retry.addEventListener('click', () => {
    retryCount += 1;
    imageErrors = false;
    render();
  });
  window.addEventListener('pagehide', stopCue);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden || !clip) return;
    stopCue();
    syncControls();
  });
  reset();
})();
