(() => {
  const K = window.K;
  const configs = {
    '把新书放上架': { mode: 'add', demo: [3, 1, 2], rounds: [[1, 3, 5], [2, 4, 4]] },
    '两张借书单': { mode: 'subtract', demo: [9, -4, -2], rounds: [[9, -2, -5], [10, -6, -4]] },
    '把两次变化排好': { mode: 'order', demo: [3, 4, -1], rounds: [[2, 5, -3], [8, -3, 2]] },
  };
  const config = configs[document.title];
  if (!config) throw new Error('Unknown reading-corner activity');
  const shelf = K.$('#shelf-now');
  const cue = K.$('#event-cue');
  const choices = K.$('#event-choices');
  const traces = K.$('#event-traces');
  const send = K.$('#apply-event');
  const undo = K.$('#undo-selection');
  const next = K.$('#next-round');
  const moments = ['#stage-zero', '#stage-one', '#stage-two'].map(id => K.$(id));
  const selected = new Set();
  let active, history, quantities, lessonCase, deck, card, step, round, wrong, demo, nextBook;

  function bookPicture(parent) {
    const picture = K.el('img', 'book-img', null, parent);
    picture.alt = '';
    picture.addEventListener('error', () => picture.replaceWith(K.el('span', 'book-placeholder', '')));
    picture.src = '__IMG:single-book__';
  }

  function pictures(parent, amount) {
    const set = K.el('div', 'book-set', null, parent);
    for (let index = 0; index < amount; index += 1) bookPicture(set);
    set.setAttribute('aria-hidden', 'true');
  }

  const mark = change => change < 0 ? '→' : '←';
  const actionName = change => change < 0 ? '借出' : '收进';
  const expected = () => lessonCase[step + 1];
  const actionable = () => !demo && step < 2;

  function prepareDeck() {
    if (!actionable() || config.mode === 'subtract') { deck = []; return; }
    const value = expected();
    if (config.mode === 'order') {
      deck = K.shuffle(step === 0 ? lessonCase.slice(1) : [value]);
      return;
    }
    const alternatives = [value - 1, value + 1, value - 2, value + 2]
      .filter(n => n > 0 && n <= 6 && n + active.length <= 10);
    deck = K.shuffle([value, ...alternatives.slice(0, 2)]);
  }

  function start(steps, isDemo, showStep = 0) {
    lessonCase = steps;
    nextBook = 0;
    active = Array.from({ length: steps[0] }, () => ++nextBook);
    history = [];
    quantities = [active.length];
    step = 0;
    wrong = 0;
    card = null;
    selected.clear();
    demo = isDemo;
    while (step < showStep) {
      move(expected(), active.slice(0, -expected()));
    }
    prepareDeck();
    render();
  }

  function move(change, borrowed) {
    const ids = change > 0 ? Array.from({ length: change }, () => ++nextBook) : borrowed;
    active = change > 0 ? active.concat(ids) : active.filter(id => !ids.includes(id));
    history.push({ change, ids });
    quantities.push(active.length);
    step += 1;
  }

  function renderShelf() {
    shelf.replaceChildren();
    shelf.dataset.count = String(active.length);
    K.$('#shelf-count').textContent = active.length;
    const pickable = actionable() && config.mode === 'subtract';
    for (let index = 0; index < 10; index += 1) {
      const id = active[index];
      const box = K.el(id && pickable ? 'button' : 'div', 'book-slot', null, shelf);
      if (!id) continue;
      box.dataset.bookId = String(id);
      bookPicture(box);
      if (pickable) {
        box.type = 'button';
        box.setAttribute('aria-label', `架上第${index + 1}本书`);
        box.setAttribute('aria-pressed', 'false');
        box.addEventListener('click', () => {
          if (selected.has(id)) selected.delete(id);
          else selected.add(id);
          box.classList.toggle('selected', selected.has(id));
          box.setAttribute('aria-pressed', String(selected.has(id)));
          K.sfx.pick();
        });
      }
    }
  }

  function renderChoices() {
    choices.replaceChildren();
    K.drags.length = 0;
    deck.forEach((change, index) => {
      const tile = K.el('button', 'event-choice', null, choices);
      tile.type = 'button';
      tile.id = `event-choice-${index + 1}`;
      tile.dataset.change = change;
      tile.dataset.out = String(change < 0);
      tile.setAttribute('aria-label', `${actionName(change)}${Math.abs(change)}本书`);
      tile.setAttribute('aria-pressed', 'false');
      K.el('b', 'change-mark', config.mode === 'order' ? (change < 0 ? '−' : '＋') : String(change), tile);
      pictures(tile, Math.abs(change));
      const pick = () => {
        if (!actionable()) return;
        card = tile;
        for (const button of choices.children) {
          button.classList.toggle('selected', button === card);
          button.setAttribute('aria-pressed', String(button === card));
        }
        K.sfx.pick();
      };
      K.drag(tile, {
        enabled: actionable,
        targets: () => [shelf, send],
        onTap: pick,
        onDrop: (_, target, event) => { if (target && event.type !== 'pointercancel') submit(change); },
      });
      tile.addEventListener('click', pick);
    });
  }

  function render() {
    moments.forEach((moment, index) => {
      moment.querySelector('b').textContent = quantities[index] ?? '○';
      moment.classList.toggle('done', index < step);
      moment.classList.toggle('active', index === step);
    });
    renderShelf();
    renderChoices();
    cue.replaceChildren();
    cue.classList.remove('needs-count');
    const change = expected();
    cue.dataset.out = String(change < 0);
    if (step < 2) {
      K.el('span', 'cue-shelf', '▦', cue).setAttribute('aria-hidden', 'true');
      K.el('b', 'cue-arrow', mark(change), cue);
      K.el('span', 'cue-amount', String(Math.abs(change)), cue);
      pictures(cue, Math.abs(change));
    } else {
      K.el('b', 'cue-arrow', '✓', cue);
      K.el('span', 'cue-amount', String(active.length), cue);
    }
    cue.setAttribute('aria-label', step < 2 ? `第${step + 1}次${actionName(change)}${Math.abs(change)}本` : `最后有${active.length}本`);
    traces.replaceChildren();
    history.forEach(({ change }, index) => {
      const trace = K.el('div', change < 0 ? 'trace out' : 'trace', null, traces);
      trace.dataset.change = change;
      K.el('b', '', `${index === 0 ? '①' : '②'} ${mark(change)}`, trace);
      pictures(trace, Math.abs(change));
    });
    send.disabled = !actionable();
    undo.disabled = !actionable();
    next.classList.toggle('hide', demo || step !== 2);
    send.textContent = config.mode === 'subtract' ? '→' : '✓';
    if (actionable()) K.say(config.mode === 'subtract' ? '选出这次要借的书。' : '看这次的方向和本数。');
    else if (!demo) K.say('两次变化都完成了。', 'ok');
  }

  function hint() {
    wrong += 1;
    cue.classList.add('needs-count');
    K.sfx.no();
    K.shake(config.mode === 'subtract' ? send : choices);
    if (wrong === 1) K.say('再看看这次的方向和本数。', 'no');
    else K.say('先看亮起的这一步，再数一遍。', 'no');
    if (wrong >= 3) {
      if (config.mode === 'subtract') {
        for (const slot of [...shelf.children].slice(0, -expected())) slot.classList.add('example-glow');
      } else {
        for (const tile of choices.children) tile.classList.toggle('example-glow', Number(tile.dataset.change) === expected());
      }
    }
  }

  function submit(choice) {
    if (!actionable()) return;
    const change = config.mode === 'subtract' ? -selected.size : choice;
    if (change !== expected()) { hint(); return; }
    const borrowed = config.mode === 'subtract' ? [...selected] : active.slice(0, Math.max(0, -change));
    move(change, borrowed);
    selected.clear();
    card = null;
    wrong = 0;
    prepareDeck();
    render();
    K.sfx.ok();
    K.say(step === 1 ? `架上现在有${active.length}本，接着做第二次。` : `最后有${active.length}本。`, 'ok');
    if (step === 2) { K.star(1, next); K.levels(config.rounds.length, round + 1); }
  }

  function play() {
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(config.rounds.length, 0);
    start(config.rounds[round], false);
  }

  send.addEventListener('click', () => submit(card && Number(card.dataset.change)));
  shelf.addEventListener('click', () => { if (config.mode !== 'subtract' && card) submit(Number(card.dataset.change)); });
  undo.addEventListener('click', () => { card = null; selected.clear(); renderShelf(); renderChoices(); });
  next.addEventListener('click', () => {
    if (demo || step !== 2 || round >= config.rounds.length) return;
    round += 1;
    if (round === config.rounds.length) {
      next.classList.add('hide');
      K.finish({ title: '书架整理好啦', sub: '每次都从架上现有的书接着算。', again: play });
    } else start(config.rounds[round], false);
  });
  K.hud({ icon: '◈', title: document.title, levels: config.rounds.length });
  K.owl();
  K.ready({ emoji: '▦', title: document.title, sub: '听老师讲，动手试一试。' });
  K.onStart = play;
  K.onState = state => {
    if (state.play === true) play();
    else if ([0, 1, 2].includes(state.demoStep)) {
      const example = config.mode === 'order' && state.demoCase === 'subtract-first' ? [7, -4, 2] : config.demo;
      start(example, true, state.demoStep);
    }
  };
  start(config.rounds[0], false);
})();
