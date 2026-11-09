(function () {
  'use strict';

  const demonstration = {
    clue: 'under', slots: { car: 'under-left', bear: 'under-right', hat: 'on-left' },
  };
  const rounds = [
    { clue: 'under', answer: 'car', slots: { car: 'under-right', bear: 'under-left', hat: 'on-left' } },
    { clue: 'on', answer: 'hat', slots: { car: 'on-left', bear: 'under-left', hat: 'on-right' } },
  ];

  function createModel() {
    return {
      level: 0,
      excluded: new Set(),
      target() { return rounds[this.level]; },
      attempt(toy) {
        const round = this.target();
        if (!round || !round.slots[toy] || this.excluded.has(toy)) return 'ignored';
        if (toy === round.answer) {
          this.level++;
          return 'confirmed';
        }
        this.excluded.add(toy);
        return 'excluded';
      },
      reset() { this.level = 0; this.excluded.clear(); },
      next() { this.excluded.clear(); },
    };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { createModel };
    return;
  }

  const K = window.K;
  const model = createModel();
  const toys = Object.fromEntries(K.$$('.guess-toy').map((button) => [button.dataset.toy, button]));
  const cues = {
    under: '__CUE:p08-under__', on: '__CUE:p08-on__',
    yes: '__CUE:p08-yes__', no: '__CUE:p08-no__',
  };
  let audio = null;
  let timer = null;
  let busy = false;
  let broken = false;

  function stop() {
    clearTimeout(timer);
    if (audio) audio.pause();
    audio = null;
  }

  function speak(key, after) {
    stop();
    const done = () => {
      if (after) timer = setTimeout(after, 450);
    };
    const url = cues[key];
    if (!url || url.startsWith('__CUE:')) return done();
    const line = new Audio(url);
    audio = line;
    line.addEventListener('ended', () => {
      if (audio === line) done();
    }, { once: true });
    line.play().catch(() => {
      if (audio !== line) return;
      K.say('点小喇叭，可以再听线索。');
      done();
    });
  }

  function render(round) {
    for (const [name, button] of Object.entries(toys)) {
      button.dataset.slot = round.slots[name];
      button.disabled = false;
      button.classList.remove('excluded', 'confirmed');
    }
    K.levels(rounds.length, model.level);
  }

  function reset(quiet) {
    stop();
    model.reset();
    busy = false;
    render(model.target());
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.say('先听位置，再猜一件。');
    if (!quiet && !broken) speak(model.target().clue);
  }

  function choose(toy) {
    if (busy || broken) return;
    const result = model.attempt(toy);
    const button = toys[toy];
    if (result === 'excluded') {
      button.classList.add('excluded');
      button.disabled = true;
      K.say('它不是这次猜的物品，再试一件。');
      speak('no');
    } else if (result === 'confirmed') {
      busy = true;
      button.dataset.slot = 'confirmed';
      button.classList.add('confirmed');
      K.star(1, button);
      K.say('猜到了，听听肯定回答。', 'ok');
      speak('yes', () => {
        busy = false;
        if (!model.target()) {
          K.finish({ title: '两件都猜到了', sub: '听线索，试着猜，再听回答。', again: reset });
          return;
        }
        model.next();
        render(model.target());
        K.say('换个位置，听一条新的线索。');
        speak(model.target().clue);
      });
    }
  }

  K.hud({ icon: '', title: '听到线索，猜一件', levels: rounds.length });
  K.owl();
  K.ready({ emoji: '', title: '听到线索，猜一件', sub: '听老师说位置，点图片猜物品。' });
  K.onStart = () => { reset(true); busy = true; };
  K.$('#start-btn').addEventListener('click', () => { busy = false; if (!broken) speak(model.target().clue); });
  for (const [name, button] of Object.entries(toys)) {
    button.addEventListener('click', () => choose(name));
  }
  K.$('#guess-listen').addEventListener('click', () => {
    if (!busy && !broken && model.target()) speak(model.target().clue);
  });
  K.onState = (state) => {
    if (state.mode === 'play') {
      reset();
      return;
    }
    if (state.mode !== 'demo') return;
    stop();
    busy = true;
    model.reset();
    render(demonstration);
    if (state.feedback === 'no') toys.car.classList.add('excluded');
    if (state.feedback === 'yes') {
      toys.car.classList.add('excluded');
      toys.bear.dataset.slot = 'confirmed';
      toys.bear.classList.add('confirmed');
    }
  };

  const fail = K.$('#guess-media-error');
  const images = K.$$('#guess-room img');
  const showError = () => {
    broken = true;
    stop();
    fail.classList.remove('hide');
  };
  for (const image of images) {
    image.addEventListener('error', showError);
    if (image.complete && !image.naturalWidth) showError();
  }
  K.$('button', fail).addEventListener('click', () => {
    let pending = images.length;
    for (const image of images) {
      image.onload = () => {
        if (--pending !== 0) return;
        broken = false;
        fail.classList.add('hide');
        reset();
      };
      image.src = image.getAttribute('src');
    }
  });
  render(model.target());
})();
