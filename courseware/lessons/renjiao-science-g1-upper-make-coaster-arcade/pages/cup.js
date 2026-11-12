(() => {
  K.ready({title: '空杯接力', sub: '看准杯垫再轻放，把两次试放收进观察记录。'});
  const art = {backdrop: '__IMG:workshop__', sticker: '__IMG:wide-coaster__'};
  const reference = new Image();
  reference.src = '__IMG:wide-coaster__';
  const left = 100, right = 862, railY = 348, base = 51;
  const materials = {
    narrow: {radius: 37, flat: true},
    curled: {radius: 80, flat: false},
    mixed: {radius: 38, flat: false},
    ready: {radius: 80, flat: true},
  };
  const levels = [
    {before: 'narrow', belt: ['narrow', 'ready'], speed: 84, tolerance: 66,
      hints: ['对齐垫子的中间，再轻轻放。', '慢一点，杯底和垫子要对在一起。']},
    {before: 'curled', belt: ['curled', 'narrow', 'ready'], speed: 102, tolerance: 54,
      hints: ['看看下面，垫子的边平不平？', '试完这张，再用同一个杯子比较。']},
    {before: 'mixed', belt: ['mixed', 'curled', 'ready'], speed: 126, tolerance: 44,
      hints: ['俯看杯底，还要从旁边看看。', '让整圈杯底有垫子，垫边也要平。']},
  ];

  const observations = [];
  const bounds = (x, y, w, h = w) => ({x: x - w / 2, y: y - h / 2, w, h});
  const clamp = (n, min, max) => Math.max(min, Math.min(n, max));
  const has = (input, key) => input.held(key) || input.press(key);
  const bot = (...keys) => ({held: key => keys.includes(key), press: key => keys.includes(key)});
  const wanted = (w, l) => w.before ? 'ready' : l.before;
  const hitRange = (w, l) => l.tolerance + (w.help ? 24 : 0);

  function reset() {
    return {x: 428, t: 0, stride: 0, press: false, hold: 0, moveFx: 0, trial: null,
      before: null, after: null, latest: null, help: false, demo: false};
  }

  function belt(w, l) {
    const length = right - left;
    return l.belt.map((kind, i) => ({
      kind,
      x: left + (328 + i * length / l.belt.length + w.stride) % length,
    }));
  }

  function update(w, l, input, dt, fb) {
    const action = input.press('action') && !w.press;
    w.press = input.press('action');
    w.t += dt;
    w.moveFx = Math.max(0, w.moveFx - dt);

    if (w.trial) {
      w.trial.t += dt;
      if (w.trial.t < .25) return;
      const {kind, x} = w.trial;
      const mat = materials[kind];
      const result = {kind, covers: mat.radius >= base, flat: mat.flat};

      const views = {top: result.covers ? 'covers' : 'extends', side: result.flat ? 'flat' : 'raised'};
      w.latest = result;
      w.trial = null;
      w.hold = .98;
      if (!w.before && kind === l.before) {
        w.before = result;
        fb.observe('before', views);
        fb.award(x, railY);
      } else if (w.before && result.covers && result.flat) {
        w.after = result;
        fb.observe('after', views);
        fb.award(x, railY);
      } else {
        fb.lost(x, railY);
      }
      return;
    }
    if (w.hold > 0) {
      w.hold -= dt;
      return;
    }

    w.stride += dt * l.speed * (w.help ? .7 : 1);
    const move = Number(has(input, 'right')) - Number(has(input, 'left'));
    if (move) {
      w.x = clamp(w.x + move * dt * 288, 118, 852);
      if (w.moveFx === 0) {
        fb.move();
        fb.fx(w.x, 204, '#f2ce8f');
        w.moveFx = .19;
      }
    }
    if (!action) return;

    const sample = belt(w, l).reduce((nearest, item) =>
      Math.abs(item.x - w.x) < Math.abs(nearest.x - w.x) ? item : nearest);
    fb.drop();
    fb.fx(w.x, 215, '#ffedb4');
    if (Math.abs(sample.x - w.x) <= hitRange(w, l)) {
      w.trial = {...sample, start: w.x, t: 0};
    } else {
      fb.lost(w.x, railY);
    }
  }

  function rect(c, x, y, w, h, color, radius = 18) {
    K.draw.rr(c, x, y, w, h, radius);
    c.fillStyle = color;
    c.fill();
  }
  function disc(c, x, y, radius, fill, stroke, width = 3) {
    c.beginPath();
    c.arc(x, y, radius, 0, 2 * Math.PI);
    c.fillStyle = fill;
    c.fill();
    if (stroke) {
      c.lineWidth = width;
      c.strokeStyle = stroke;
      c.stroke();
    }
  }
  function top(c, x, y, mat, {cup = false, scale = 1, rim = false} = {}) {
    c.save();
    c.translate(x, y);
    c.scale(scale, scale);
    if (mat) {
      disc(c, 0, 0, mat.radius, '#a6ba91', '#466f5c');
      if (!mat.flat) {
        c.beginPath();
        c.arc(0, 0, mat.radius, -.68, .68);
        c.quadraticCurveTo(mat.radius * .43, 0, mat.radius * Math.cos(.68), -mat.radius * Math.sin(.68));
        c.fillStyle = '#d99461';
        c.fill();
      }
    }
    if (cup) {
      if (rim) {
        c.save();
        c.setLineDash([8, 6]);
        c.lineWidth = 3;
        c.strokeStyle = '#fff5d7';
        c.beginPath();
        c.arc(0, 0, base, 0, 2 * Math.PI);
        c.stroke();
        c.restore();
        disc(c, 0, 0, base, '#e98a4c50', '#b95637');
      } else {
        disc(c, 45, 2, 19, '#c76843', '#854a33');
        disc(c, 47, 2, 10, '#f1be82', '#854a33');
        disc(c, 0, 0, base, '#ee9a60', '#9c553d', 4);
        disc(c, 0, 0, 39, '#f3ca99', '#b06c49');
      }
    }
    c.restore();
  }
  function profile(c, x, y, mat, scale = 1) {
    c.save();
    c.translate(x, y);
    c.scale(scale, scale);
    const lift = mat.flat ? 0 : 30;
    c.lineWidth = 3;
    c.strokeStyle = '#9b775d';
    c.beginPath();c.moveTo(-93, 7);c.lineTo(93, 7);c.stroke();
    c.beginPath();
    c.moveTo(-mat.radius, 0);
    c.lineTo(mat.radius * .44, 0);
    c.quadraticCurveTo(mat.radius * .80, 0, mat.radius, -lift);
    c.lineTo(mat.radius, -lift + 8);
    c.quadraticCurveTo(mat.radius * .80, 8, mat.radius * .44, 8);
    c.lineTo(-mat.radius, 8);
    c.closePath();
    c.fillStyle = '#a6ba91';
    c.strokeStyle = '#466f5c';
    c.fill();c.stroke();
    c.restore();
  }

  function drawnTrial(c, sample, x, y, width, height) {
    const mat = materials[sample.kind];
    rect(c, x, y, width, height, '#f5dfb8', 12);
    top(c, x + width * .29, y + height * .48, mat, {cup: true, rim: true, scale: Math.min(.51, width / 360)});
    profile(c, x + width * .76, y + height * .53, mat, Math.min(.55, width / 395));
    const marks = [[.29, sample.covers], [.76, sample.flat]];
    for (const [dx, okay] of marks) {
      const px = x + width * dx;
      const py = y + height - 17;
      disc(c, px, py, 10, okay ? '#52785e' : '#b05b43');
      c.lineWidth = 2;
      c.strokeStyle = '#fff3d9';
      c.beginPath();
      c.moveTo(px - 5, py);
      c.lineTo(px - 1, py + (okay ? 4 : 0));
      c.lineTo(px + 5, py - (okay ? 5 : 0));
      c.stroke();
    }
  }

  function emptyTrial(c, x, y, width, height) {
    rect(c, x, y, width, height, '#ead6b6', 12);
    c.strokeStyle = '#a78664';
    c.lineWidth = 3;
    c.setLineDash([7, 7]);
    K.draw.rr(c, x + 8, y + 8, width - 16, height - 16, 10);
    c.stroke();
    c.setLineDash([]);
  }

  function draw(w, l, c) {
    c.fillStyle = '#233d33b8';
    c.fillRect(0, 0, 1280, 720);
    rect(c, 23, 101, 875, 495, '#f8e5c2', 22);
    rect(c, 917, 101, 340, 495, '#304b40', 22);
    K.draw.text(c, '空杯接力', 200, 146, 39, '#314b40');
    K.draw.text(c, '观察记录', 1087, 145, 39, '#fff0cf');
    K.draw.text(c, '先试', 1087, 182, 27, '#fff0cf');
    K.draw.text(c, '再试', 1087, 390, 27, '#fff0cf');

    c.save();
    K.draw.rr(c, 46, 242, 830, 204, 19);
    c.clip();
    rect(c, 46, 242, 830, 204, '#47695d');
    const dash = w.stride % 60;
    for (let n = -1; n < 15; n++) {
      rect(c, 46 + n * 60 + dash, 253, 23, 182, '#55786a', 8);
    }
    rect(c, 46, 244, 830, 12, '#a0af87', 2);
    rect(c, 46, 431, 830, 12, '#a0af87', 2);

    for (const item of belt(w, l)) {
      const mat = materials[item.kind];
      const relevant = !w.before && item.kind === l.before;
      const close = Math.abs(item.x - w.x) <= hitRange(w, l);
      rect(c, item.x - 91, 266, 182, 155, close ? '#edd199' : '#ddd4ac', 19);
      if (relevant) {
        c.strokeStyle = '#fff2cd';c.lineWidth = 4;
        K.draw.rr(c, item.x - 90, 266, 180, 155, 19);
        c.stroke();
      }
      top(c, item.x, 322, mat, {scale: .63});
      profile(c, item.x, 397, mat, .72);
    }
    c.restore();

    const place = w.trial ? Math.min(1, w.trial.t / .25) : 0;
    const cupX = w.trial ? w.trial.start + (w.trial.x - w.trial.start) * place : w.x;
    const cupY = 203 + (322 - 203) * place;
    const heldMat = w.hold > 0 && w.latest;
    if (!heldMat) {
      c.save();
      c.strokeStyle = '#b96a47';
      c.lineWidth = 3;
      c.setLineDash([9, 7]);
      c.beginPath();c.moveTo(cupX, cupY + 40);c.lineTo(cupX, 323);c.stroke();
      c.restore();
      top(c, cupX, cupY, null, {cup: true, scale: .79});
    }

    const bottom = w.after || (w.before && w.latest !== w.before ? w.latest : null);
    if (w.before) drawnTrial(c, w.before, 943, 201, 288, 154);
    else emptyTrial(c, 943, 201, 288, 154);
    if (bottom) drawnTrial(c, bottom, 943, 410, 288, 154);
    else if (w.latest && !w.before) drawnTrial(c, w.latest, 943, 201, 288, 154);
    else emptyTrial(c, 943, 410, 288, 154);

    if (reference.complete && reference.naturalWidth) {
      c.save();
      K.draw.rr(c, 59, 461, 101, 101, 12);c.clip();
      c.drawImage(reference, 59, 461, 101, 101);
      c.restore();
    } else {
      top(c, 109, 510, materials.ready, {cup: true, scale: .57});
    }
    const note = w.hold > 0 && w.latest
      ? '从上面看杯底，从侧面看垫边。'
      : w.before ? '让同一个空杯换张垫子再试。' : '先跟上有白边的垫子，轻轻放下。';
    K.draw.text(c, note, 175, 508, 28, '#314b40', {align: 'left'});
  }

  function recordPanel(card) {
    const figure = K.el('figure', 'coaster-observation', null, card);
    figure.setAttribute('aria-label', '观察记录卡');
    const caption = K.el('figcaption', '', null, figure);
    caption.textContent = '观察记录卡';
    const canvas = K.el('canvas', '', null, figure);
    canvas.width = 744; canvas.height = 186;
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', observations.map((record, index) => {
      const problem = [
        !record.before.covers && '杯底伸出',
        !record.before.flat && '垫边翘起',
      ].filter(Boolean).join('、');
      return '第' + (index + 1) + '关：先试发现' + problem + '。再试杯底垫住，边平。';
    }).join(''));
    const c = canvas.getContext('2d');
    observations.forEach((record, i) => {
      const x = 5 + i * 248;
      K.draw.text(c, '第 ' + (i + 1) + ' 关', x + 118, 19, 24, '#304b40');
      drawnTrial(c, record.before, x, 36, 114, 112);
      drawnTrial(c, record.after, x + 123, 36, 114, 112);
      K.draw.text(c, '先试', x + 57, 166, 22, '#304b40');
      K.draw.text(c, '再试', x + 180, 166, 22, '#304b40');
    });
    const foot = K.el('p', 'coaster-observation-foot', null, figure);
    foot.textContent = '实物试放和口头描述：待观察。';
    card.insertBefore(figure, K.$('button', card));
  }

  const options = K.gameTemplates.arcade({
    art, levels,
    observation: {
      sceneId: 'scene-cup',
      trials: {
        before: {top: ['extends', 'covers'], side: ['flat', 'raised']},
        after: {top: ['covers'], side: ['flat']}
      }
    },
    cues: [
      {goal: 'sameCup', steps: ['firstTest', 'sameCup'], hint: 'firstTest', hint2: 'compare', praise: 'wellDone'},
      {goal: 'compare', steps: ['compare', 'sameCup'], hint: 'compare', hint2: 'sameCup', praise: 'wellDone'},
      {goal: 'compare', steps: ['compare', 'sameCup'], hint: 'compare', hint2: 'sameCup', praise: 'wellDone'},
    ],
    doneText: '空杯稳稳站好了，工坊杯垫贴纸到手！',
  }, {
    backdrop: '#3e574b',
    controls: [['left', '←', '把空杯移向左边'], ['right', '→', '把空杯移向右边'],
      ['action', '轻放', '把空杯轻放在垫子上']],
    validate(l) {
      if (!l.belt.includes(l.before) || !l.belt.includes('ready')) throw new Error('试放要有改进前后的比较');
    },
    reset, update, draw, goal: () => 2,
    adapt(w, misses) { w.help = misses >= 2; },
    player: w => bounds(w.x, 203, 104),
    target(w, l) {
      const sample = belt(w, l).find(item => item.kind === wanted(w, l));
      return bounds(sample.x, railY, 126);
    },
    pilot(w, l) {
      if (w.trial || w.hold > 0) return bot();
      const item = belt(w, l).find(sample => sample.kind === wanted(w, l));
      const delta = item.x - w.x;
      if (Math.abs(delta) < hitRange(w, l) * .45) return w.press ? bot() : bot('action');
      return bot(delta < 0 ? 'left' : 'right');
    },
  });

  const setup = options.setup;
  options.setup = g => {
    setup(g);
    g.follow('#game-samples', () => bounds(1087, 382, 276, 358));
  };
  const resetGame = options.reset;
  options.reset = (g, i) => {
    resetGame(g, i);
    if (i === 0) observations.length = 0;
  };
  const drawGame = options.draw;
  options.draw = (g, c) => {
    drawGame(g, c);
    const w = g.data.w;
    if (w?.after && !g.auto && !observations[g.level]) {
      observations[g.level] = {before: w.before, after: w.after};
    }
    if (g.state === 'done') {
      const card = K.$('#finish .card');
      if (!g.auto && card && !card.querySelector('.coaster-observation')) recordPanel(card);
    }
  };
  K.game(options);
})();
