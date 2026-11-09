(function () {
  const glyphs = {
    尺: [
      ['横折', 'M 29 23 Q 52 21 72 21 L 66 40'],
      ['横', 'M 28 42 L 66 40'],
      ['撇', 'M 29 23 C 30 53 24 73 11 84'],
      ['捺', 'M 47 49 C 53 65 67 79 86 83'],
    ],
    刀: [
      ['横折钩', 'M 22 27 Q 48 25 79 25 C 76 45 75 67 69 80 L 61 73'],
      ['撇', 'M 52 26 C 49 54 38 72 19 85'],
    ],
    本: [
      ['横', 'M 20 36 L 80 34'],
      ['竖', 'M 50 17 L 49 88'],
      ['撇', 'M 48 39 C 38 57 25 67 13 74'],
      ['捺', 'M 52 40 C 61 54 73 65 88 72'],
      ['横', 'M 35 67 L 65 65'],
    ],
    不: [
      ['横', 'M 20 26 L 81 24'],
      ['撇', 'M 55 28 C 47 48 29 62 15 68'],
      ['竖', 'M 50 44 L 50 87'],
      ['点', 'M 62 48 Q 75 54 85 65'],
    ],
    少: [
      ['竖', 'M 50 16 L 50 55'],
      ['撇', 'M 32 34 Q 26 46 17 53'],
      ['点', 'M 66 31 Q 76 35 83 43'],
      ['撇', 'M 69 50 C 57 68 36 82 16 86'],
    ],
  };
  const board = K.$('#schoolbag-writing');
  const first = document.title === board.dataset.firstTitle;
  if (!first && document.title !== board.dataset.secondTitle) throw new Error('Unexpected writing lesson title');
  const group = first ? ['尺', '刀'] : ['本', '不', '少'];
  const face = K.$('#schoolbag-glyph');
  const grid = K.$('#schoolbag-grid');
  const choices = K.$('#schoolbag-strokes');
  let glyphIndex = 0;
  let revealed = 0;
  let mode = 'play';
  let errors = 0;
  let sequence = 0;
  let locked = false;

  K.hud({icon:'字',title:document.title,levels:group.length});
  K.owl();
  K.ready({emoji:'字',title:document.title,sub:'看格子里的位置，选下一笔'});

  function drawing(glyph, complete, emphasized) {
    const paths = glyphs[glyph].map(([, route], i) => {
      const color = i === emphasized ? '#C75B24' : i < complete ? '#2C5147' : '#E6E0CF';
      return `<path d="${route}" stroke="${color}" stroke-width="4.2" fill="none" stroke-linejoin="round" stroke-linecap="round"/>`;
    }).join('');
    return `<svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">
      <rect x="3" y="3" width="94" height="94" rx="3" fill="#FFFCF1" stroke="#87AB9C" stroke-width="1.2"/>
      <path d="M 3 50 H 97 M 50 3 V 97" stroke="#ABC3B9" stroke-width=".8" stroke-dasharray="2 2"/>${paths}</svg>`;
  }

  function render() {
    const glyph = group[glyphIndex];
    const paths = glyphs[glyph];
    face.textContent = glyph;
    grid.innerHTML = drawing(glyph, revealed);
    grid.dataset.revealed = String(revealed);
    choices.replaceChildren();
    if (revealed >= paths.length) return;
    const options = [revealed, ...paths.map((_, i) => i).filter(i => i !== revealed).slice(0, 2)];
    for (const index of K.shuffle(options)) {
      const button = K.el('button', 'schoolbag-stroke', null, choices);
      button.type = 'button';
      button.dataset.stroke = String(index);
      button.setAttribute('aria-label', `${glyph}字的${paths[index][0]}图`);
      button.innerHTML = drawing(glyph, revealed, index);
      button.addEventListener('click', () => choose(index, button));
    }
  }

  function reset() {
    sequence += 1;
    glyphIndex = 0;
    revealed = 0;
    mode = 'play';
    errors = 0;
    locked = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(group.length, 0);
    render();
    K.say('看已经写出的笔画，再选接下来的一笔');
  }

  function choose(index, button) {
    if (!K.started || locked || mode !== 'play') return;
    if (index !== revealed) {
      errors += 1;
      K.sfx.no();
      K.shake(button);
      if (errors === 1) K.say('看看已经写了哪几笔，再试一次', 'no');
      else if (errors === 2) K.say('注意这一笔从格子的哪里开始', 'no');
      else {
        K.highlight(`[data-stroke="${revealed}"]`);
        K.say('看看老师提示的这一笔', 'no');
      }
      return;
    }
    errors = 0;
    revealed += 1;
    K.sfx.tick(revealed);
    if (revealed < glyphs[group[glyphIndex]].length) {
      render();
      K.say('这一笔放好了，看看下一笔', 'ok');
      return;
    }
    K.star(1, grid);
    K.levels(group.length, glyphIndex + 1);
    render();
    K.say('格子里的笔画排好了', 'ok');
    locked = true;
    const token = sequence;
    setTimeout(() => {
      if (token !== sequence) return;
      if (glyphIndex + 1 === group.length) {
        K.finish({title:'笔顺图排好啦',sub:'在纸上写一次，请大人看看',again:reset});
      } else {
        glyphIndex += 1;
        revealed = 0;
        locked = false;
        render();
      }
    }, 820);
  }

  K.onStart = reset;
  K.onState = state => {
    if (state.phase === 'play') { reset(); return; }
    if (!group.includes(state.glyph) || !Number.isInteger(state.reveal)) return;
    sequence += 1;
    locked = false;
    mode = 'demo';
    glyphIndex = group.indexOf(state.glyph);
    revealed = Math.min(glyphs[state.glyph].length, Math.max(0, state.reveal));
    render();
  };
  K.$('#schoolbag-writing-reset').addEventListener('click', reset);
  reset();
})();
