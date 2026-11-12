(() => {
  const art = {backdrop: '__IMG:workshop__', sticker: '__IMG:round-lid__'};
  const reference = new Image();
  reference.src = '__IMG:string__';
  K.ready({title: '圆线追光', sub: '选好绳长，绕回起点，让一圈灯都亮起来。'});

  const center = {x: 787, y: 354};
  const fullTurn = 2 * Math.PI;
  const levels = [
    {radius: 148, initial: 148, speed: 1.35, period: 1.5, window: 1.5,
      marks: [1.10, 2.80, 4.45, fullTurn],
      hints: ['看一看笔尖和虚线。', '笔尖回到圆边，沿着灯继续。']},
    {radius: 188, initial: 124, speed: 1.58, period: 1.4, window: 1.05,
      marks: [1.02, 2.40, 3.72, 5.02, fullTurn],
      hints: ['先比较线的长短，再看灯。', '用上下箭头让笔尖碰到圆边。']},
    {radius: 125, initial: 184, speed: 1.86, period: 1.35, window: .78,
      marks: [.83, 1.89, 3.01, 4.13, 5.14, fullTurn],
      hints: ['你能让笔尖贴着这一圈吗？', '上下调到圆边，等灯亮了再走。']},
  ];

  const region = (x, y, size) => ({x: x - size / 2, y: y - size / 2, w: size, h: size});
  const point = (r, a) => ({x: center.x + r * Math.cos(a), y: center.y + r * Math.sin(a)});
  const clamp = (x, min, max) => Math.max(min, Math.min(x, max));
  const has = (input, key) => input.held(key) || input.press(key);
  const bot = (...keys) => ({held: key => keys.includes(key), press: key => keys.includes(key)});
  const targetAngle = (w, l) => l.marks[w.mark] ?? fullTurn;
  const pen = w => point(w.radius, w.angle * (w.direction || 1));
  const tolerance = w => w.help ? 23 : 13;

  function reset(l) {
    return {radius: l.initial, direction: 0, angle: 0, ink: false, pressed: false,
      mark: 0, t: 0, help: false, bump: false, clickFx: 0, completed: false};
  }

  function gateOpen(w, l) {
    return (w.t + w.mark * .29) % l.period < Math.min(l.period, l.window + (w.help ? .46 : 0));
  }

  function update(w, l, input, dt, fb) {
    w.t += dt;
    w.clickFx = Math.max(0, w.clickFx - dt);
    const adjust = Number(has(input, 'up')) - Number(has(input, 'down'));
    const turn = Number(has(input, 'right')) - Number(has(input, 'left'));

    if (!w.ink && w.angle === 0 && adjust) {
      w.radius = clamp(w.radius + adjust * 108 * dt, 98, 202);
      if (w.clickFx === 0) {
        const p = pen(w);
        fb.move();
        fb.fx(p.x, p.y);
        w.clickFx = .14;
      }
    }

    const action = input.press('action');
    if (action && !w.pressed) {
      const p = pen(w);
      if (!w.ink && Math.abs(w.radius - l.radius) > tolerance(w)) {
        fb.lost(p.x, p.y);
      } else {
        w.radius = l.radius;
        w.ink = !w.ink;
        fb.drop();
        fb.fx(p.x, p.y, '#f7d483');
      }
    }
    w.pressed = action;
    if (!w.ink || !turn || w.completed) return;
    if (!w.direction) {
      w.direction = turn;
      fb.move();
    }
    if (turn !== w.direction) return;

    const next = targetAngle(w, l);
    const angle = w.angle + dt * l.speed * (w.help ? .83 : 1);
    if (angle < next) {
      w.angle = angle;
      return;
    }
    const target = point(l.radius, next * w.direction);
    if (!gateOpen(w, l)) {
      w.angle = Math.max(w.angle, next - .045);
      if (!w.bump) {
        fb.lost(target.x, target.y);
        w.bump = true;
      }
      return;
    }
    w.angle = next;
    w.bump = false;
    w.mark++;
    w.completed = w.mark === l.marks.length;
    fb.award(target.x, target.y);
  }

  function rect(c, x, y, w, h, color, radius = 18) {
    K.draw.rr(c, x, y, w, h, radius);
    c.fillStyle = color;
    c.fill();
  }
  function dot(c, x, y, r, color) {
    c.fillStyle = color;
    K.draw.circle(c, x, y, r);
  }
  function orbit(c, radius, end, color, width, dash = []) {
    c.save();
    c.setLineDash(dash);
    c.strokeStyle = color;
    c.lineWidth = width;
    c.lineCap = 'round';
    c.beginPath();
    c.arc(center.x, center.y, radius, 0, end, end < 0);
    c.stroke();
    c.restore();
  }
  function rope(c, p, raised) {
    c.save();
    c.strokeStyle = '#9b5e3b';
    c.lineWidth = 5;
    c.beginPath();
    c.moveTo(center.x, center.y);
    if (raised) c.quadraticCurveTo((p.x + center.x) / 2, (p.y + center.y) / 2 + 10, p.x, p.y);
    else c.lineTo(p.x, p.y);
    c.stroke();
    c.restore();
  }
  function drawPen(c, w) {
    const p = pen(w);
    c.save();
    c.translate(p.x, p.y);
    c.rotate(w.angle * (w.direction || 1) + Math.PI / 2);
    rect(c, -12, -72, 24, 53, '#356f8c', 8);
    rect(c, -12, -73, 24, 13, '#c3865e', 7);
    c.beginPath();
    c.moveTo(-12, -21);
    c.lineTo(12, -21);
    c.lineTo(0, 0);
    c.closePath();
    c.fillStyle = '#e4b37a';
    c.fill();
    dot(c, 0, 0, w.ink ? 6 : 4, '#254b46');
    c.restore();
  }

  function draw(w, l, c) {
    const p = pen(w);
    c.fillStyle = '#233c33ae';
    c.fillRect(0, 0, 1280, 720);
    rect(c, 23, 101, 355, 495, '#2b473d');
    rect(c, 398, 101, 859, 495, '#fbefd3', 24);
    rect(c, 413, 116, 829, 464, '#f7e3bd', 16);
    rect(c, 47, 183, 306, 171, '#f7e3bd', 15);
    if (reference.complete && reference.naturalWidth) {
      c.save();
      K.draw.rr(c, 47, 183, 306, 171, 15);
      c.clip();
      c.drawImage(reference, 47, 183, 306, 171);
      c.restore();
    } else {
      c.strokeStyle = '#99592e';
      c.lineWidth = 8;
      c.beginPath();
      c.moveTo(88, 272);c.lineTo(312, 272);c.stroke();
      dot(c, 88, 272, 12, '#356f58');
      dot(c, 312, 272, 12, '#356f8c');
    }

    K.draw.text(c, '圆线追光', 200, 145, 40, '#fff0cf');
    K.draw.text(c, '绳长', 201, 400, 30, '#fff0cf');
    rect(c, 62, 427, 276, 54, '#193930', 16);
    const notch = r => 74 + (r - 98) * 2.43;
    rect(c, 74, 443, Math.max(5, notch(w.radius) - 74), 22, '#eaa470', 8);
    c.strokeStyle = '#fff0cf'; c.lineWidth = 3;
    c.strokeRect(notch(l.radius) - 12, 434, 24, 39);
    K.draw.text(c, w.ink ? '绕回起点' : '对准圆边再落笔', 200, 538, 28, '#fff0cf');

    orbit(c, l.radius, fullTurn, '#a78965', 4, [10, 10]);
    const start = point(l.radius, 0);
    dot(c, start.x, start.y, 17, '#fff2d7');
    c.strokeStyle = '#518a73'; c.lineWidth = 4;
    c.beginPath(); c.arc(start.x, start.y, 16, 0, fullTurn); c.stroke();

    if (w.angle > 0) orbit(c, l.radius, w.angle * w.direction, '#306c57', 9);
    for (let i = 0; i < l.marks.length; i++) {
      const m = point(l.radius, l.marks[i] * (w.direction || 1));
      if (i < w.mark) {
        K.draw.star(c, m.x, m.y, 15, '#d79b3c');
      } else if (i === w.mark && w.direction) {
        const open = gateOpen(w, l);
        const pulsing = open ? 22 + Math.sin(w.t * 7) * 3 : 15;
        dot(c, m.x, m.y, pulsing, open ? '#f8d78d' : '#e9d1ac');
        K.draw.star(c, m.x, m.y, 14, open ? '#d88835' : '#8d7764');
      } else {
        dot(c, m.x, m.y, 8, '#b49a77');
      }
    }
    rope(c, p, !w.ink);
    dot(c, center.x, center.y, 18, '#39705a');
    dot(c, center.x, center.y, 6, '#f5ce80');
    drawPen(c, w);
  }

  const options = K.gameTemplates.arcade({
    art, levels,
    cues: [
      {goal: 'roundGoal', hint: 'fixedLength', hint2: 'roundGoal', praise: 'roundComplete'},
      {goal: 'longerLine', hint: 'fixedLength', hint2: 'roundGoal', praise: 'roundComplete'},
      {goal: 'fixedLength', hint: 'fixedLength', hint2: 'roundGoal', praise: 'roundComplete'},
    ],
    doneText: '圆线接上啦，工坊圆盖贴纸到手！'
  }, {
    backdrop: '#3b5348',
    controls: [
      ['left', '←', '向左绕'], ['right', '→', '向右绕'],
      ['up', '↑', '加长绳子'], ['down', '↓', '缩短绳子'],
      ['action', '落笔', '落笔或抬笔']
    ],
    validate(l) {
      if (!l.marks.length || l.marks.at(-1) !== fullTurn) throw new Error('圆线必须绕回起点');
    },
    reset, goal: l => l.marks.length, update, draw,
    adapt(w, n) { w.help = n >= 2; },
    player(w) { const p = pen(w); return region(p.x, p.y, 102); },
    target(w, l) { const p = point(l.radius, targetAngle(w, l) * (w.direction || 1)); return region(p.x, p.y, 98); },
    pilot(w, l) {
      if (w.ink) {
        const closeToGate = targetAngle(w, l) - w.angle < .13;
        return closeToGate && !gateOpen(w, l) ? bot() : bot('right');
      }
      if (Math.abs(w.radius - l.radius) <= 7) return w.pressed ? bot() : bot('action');
      return bot(w.radius < l.radius ? 'up' : 'down');
    },
  });

  const setup = options.setup;
  options.setup = g => {
    setup(g);
    g.follow('#game-pivot', () => region(center.x, center.y, 110));
  };
  const resetGame = options.reset;
  options.reset = (g, i) => {
    resetGame(g, i);
    if (g.autoLoop) g.data.w.ink = true;
  };
  K.game(options);
})();
