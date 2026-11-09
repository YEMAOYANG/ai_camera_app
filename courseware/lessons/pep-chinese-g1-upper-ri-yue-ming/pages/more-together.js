(() => {
  const art = {
    follow: { src: '__IMG:people-follow__', alt: '一个孩子跟着另一个孩子向右走' },
    people: { src: '__IMG:people-group__', alt: '走在一起的人群' },
    trees: { src: '__IMG:tree-grove__', alt: '一片并排生长的树' },
    forest: { src: '__IMG:forest-view__', alt: '很深很密的一片林子' },
  };
  const piece = glyph => ({ id: glyph, glyph, alt: glyph });
  const visual = (id, crop) => ({ ...art[id], id, crop });
  const assemble = (word, artwork, parts, extra, layout, hint) =>
    ({ word, artwork, parts, layout, hint, choices: [...parts, extra].map(piece) });
  const choose = (word, artwork, choices, answer, reveal, hint) =>
    ({ word, artwork, choices, answer, reveal, hint });
  const guesses = ['tears', 'seedlings', 'frame'].map(id => visual(id));
  const jobs = [
    { ...visual('build', 'left'), id: 'hold', alt: '扶住纸板' },
    { ...visual('build', 'center'), id: 'pass', alt: '把胶带递给同伴' },
    { ...visual('build', 'right'), id: 'fix', alt: '用胶带贴牢纸边' },
  ];
  const wordArt = [
    ['力气', 'field', ['golden', 'dust']],
    ['尘土', 'dust', ['hands', 'trees']],
    ['双手', 'hands', ['golden', 'forest']],
    ['金黄', 'golden', ['hands', 'forest']],
    ['树林', 'trees', ['hands', 'care']],
    ['森林', 'forest', ['hands', 'dust']],
    ['关心', 'care', ['dust', 'trees']],
    ['开心', 'happy', ['hands', 'forest']],
  ];
  const lessons = {
    '明和男从哪里来': () => [
      assemble('明', 'sunMoon', ['日', '月'], '田', 'row', '先看看日和月哪一个放左边。'),
      assemble('男', 'field', ['田', '力'], '木', 'stack', '田和力一上一下，先看看上格。'),
    ],
    '小下面是什么': () => [
      choose('小', 'tip', ['土', '大', '木'].map(piece), '大', 'tip', '看尖端下面是不是一点点变宽。'),
      choose('小', 'dust', ['大', '土', '月'].map(piece), '土', 'dust', '仔细看光束里的细小颗粒。'),
    ],
    '人和木怎么排': () => [
      assemble('从', 'follow', ['人', '人'], '木', 'row', '看两个挨着的人部件。'),
      assemble('众', 'people', ['人', '人', '人'], '月', 'crown', '看看上面和下面分别能放几个。'),
      assemble('林', 'trees', ['木', '木'], '人', 'row', '两个木左右并排。'),
      assemble('森', 'forest', ['木', '木', '木'], '力', 'crown', '上面一个木，下面还有两个位置。'),
    ],
    '部件给我线索': () => [
      choose('泪', 'studio', guesses, 'tears', 'tears', '看左边的水和右边的眼睛。'),
      choose('苗', 'studio', guesses, 'seedlings', 'seedlings', '看看草字头下面像什么地方。'),
      choose('歪', 'studio', guesses, 'frame', 'frame', '上面的不，和下面的正合在一起。'),
    ],
    '三个人合做一件事': () => [
      choose('先', 'build', jobs, 'hold', 'build', '纸板没有站稳，先看看哪双手能帮忙。'),
      choose('接着', 'build', jobs, 'pass', 'build', '纸板扶稳了，看看中间的孩子手里有什么。'),
      choose('最后', 'build', jobs, 'fix', 'built', '胶带递过来了，谁能把纸边贴牢？'),
    ],
    '词语开窗': () => wordArt.map(([word, id, alternatives]) =>
      choose(word, 'studio', [id, ...alternatives].map(asset => visual(asset)), id, id,
        '把这个词放进老师说过的情境，再看一看三幅图。')),
  };
  const rounds = lessons[document.title]?.();
  if (!rounds) throw new Error('没有找到本课互动');
  const cooperative = document.title === '三个人合做一件事';
  const panel = K.$('#ry-panel');
  const photo = K.$('#ry-scene-picture');
  const result = K.$('#ry-result');
  const bank = K.$('#ry-bank');
  const slots = K.$('#ry-slots');
  const pictureFallback = K.el('div', 'ry-picture-unavailable', '图片暂不可用', panel);
  panel.insertBefore(pictureFallback, result);
  pictureFallback.style.display = 'none';
  photo.addEventListener('error', () => {
    photo.style.display = 'none';
    pictureFallback.style.display = '';
  });

  let level = 0;
  let demo = false;
  let advancing = false;
  let attempts = 0;
  let selected = null;
  let filled = [];
  let suppressClick = 0;
  let transitionTimer;

  function artwork(id) {
    photo.style.display = '';
    pictureFallback.style.display = 'none';
    photo.alt = art[id].alt;
    photo.src = art[id].src;
  }

  function completedWord(round) {
    if (round.word === '小') return round.answer === '大' ? '尖' : '尘';
    return round.word;
  }

  function wrong(control) {
    attempts += 1;
    K.sfx.no();
    K.shake(control);
    K.say(attempts === 1 ? '慢一点，再看看画面和部件。' : rounds[level].hint, 'no');
  }

  function advance() {
    if (demo || advancing) return;
    const round = rounds[level];
    advancing = true;
    if (round.reveal) artwork(round.reveal);
    result.textContent = completedWord(round);
    if (cooperative) showJobs(level + 1);
    K.say('做对了，看看画面里的变化。', 'ok');
    K.sfx.ok();
    K.star(1);
    K.levels(rounds.length, level + 1);
    transitionTimer = setTimeout(() => {
      advancing = false;
      level += 1;
      if (level < rounds.length) {
        render();
      } else {
        K.finish({title:'工作室任务完成',sub:'再试一次，还可以练习这一页。',again:reset});
      }
    }, 500);
  }

  function place(control, target) {
    if (demo || advancing || !target) return;
    const index = Number(target.dataset.slot);
    if (filled[index]) return;
    const round = rounds[level];
    if (round.parts[index] !== control.dataset.option) {
      wrong(target);
      return;
    }
    filled[index] = true;
    target.textContent = control.dataset.option;
    target.classList.add('placed');
    control.disabled = true;
    control.classList.remove('selected');
    selected = null;
    K.sfx.drop();
    K.say('拼好一块，再看剩下的位置。', 'ok');
    if (filled.every(Boolean)) advance();
  }

  function makeSlot(part, index) {
    const target = document.createElement('button');
    target.type = 'button';
    target.className = 'ry-slot';
    target.dataset.slot = index;
    target.setAttribute('aria-label', '第' + (index + 1) + '个部件位置');
    if (demo) {
      target.classList.add('placed');
      target.textContent = part;
    }
    target.addEventListener('click', () => {
      if (selected && Date.now() >= suppressClick) place(selected, target);
    });
    return target;
  }

  function makeChoice(option, index) {
    const control = document.createElement('button');
    control.type = 'button';
    control.id = 'ry-choice-' + index;
    control.className = 'ry-choice';
    control.dataset.option = option.id;
    control.setAttribute('aria-label', option.alt);
    if (option.src) {
      control.dataset.picture = option.id;
      if (option.crop) control.dataset.crop = option.crop;
      const image = document.createElement('img');
      image.alt = option.alt;
      image.src = option.src;
      control.append(image);
    } else {
      control.textContent = option.glyph;
    }
    const round = rounds[level];
    if (demo && round.answer === option.id) control.classList.add('success');
    control.addEventListener('click', () => {
      if (demo || advancing || Date.now() < suppressClick) return;
      if (round.parts) {
        if (selected) selected.classList.remove('selected');
        selected = control;
        control.classList.add('selected');
        K.sfx.pick();
      } else if (option.id === round.answer) {
        control.classList.add('success');
        advance();
      } else {
        wrong(control);
      }
    });
    if (round.parts) K.drag(control, {
      enabled: () => !demo && !advancing && !control.disabled,
      targets: () => Array.from(slots.children),
      onTap: () => control.click(),
      onDrop: (_control, target, event) => {
        suppressClick = Date.now() + 180;
        if (event.type !== 'pointercancel') place(control, target);
      },
    });
    return control;
  }

  function showJobs(count) {
    slots.dataset.layout = 'job-sequence';
    slots.replaceChildren();
    jobs.forEach((job, index) => {
      const tile = K.el('div', 'ry-job', null, slots);
      tile.dataset.crop = job.crop;
      if (index < count) {
        const image = document.createElement('img');
        image.src = job.src;
        image.alt = job.alt;
        tile.append(image);
      }
    });
  }

  function render() {
    const round = rounds[level];
    selected = null;
    attempts = 0;
    K.drags = [];
    slots.replaceChildren();
    bank.replaceChildren();
    filled = Array(round.parts?.length || 0).fill(false);
    artwork(demo && round.reveal ? round.reveal : round.artwork);
    result.textContent = demo ? completedWord(round) : round.word;
    if (round.parts) {
      slots.dataset.layout = round.layout;
      round.parts.forEach((part, index) => slots.append(makeSlot(part, index)));
    } else if (cooperative) {
      showJobs(demo ? level + 1 : level);
    }
    (demo ? round.choices : K.shuffle(round.choices)).forEach((choice, index) => bank.append(makeChoice(choice, index)));
    K.levels(rounds.length, demo ? 0 : level);
    K.say(demo ? '听老师解释，看看画面怎么变化。' :
      round.parts ? '先看字的样子，选卡片放进空格。' : '先听题和提示，再看看三张卡片。');
  }

  function reset() {
    clearTimeout(transitionTimer);
    level = 0;
    advancing = false;
    demo = false;
    suppressClick = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$('#finish')?.classList.add('gone');
    render();
  }

  K.hud({icon:'字',title:document.title,levels:rounds.length});
  K.owl();
  K.ready({title:document.title,sub:'先听老师，再看图动手',emoji:'字'});
  K.onStart = reset;
  K.onState = state => {
    if (state.phase === 'play') {
      reset();
    } else if (Number.isInteger(state.demoRound) && state.demoRound >= 0 && state.demoRound < rounds.length) {
      clearTimeout(transitionTimer);
      advancing = false;
      level = state.demoRound;
      demo = true;
      render();
    }
  };
  render();
})();
