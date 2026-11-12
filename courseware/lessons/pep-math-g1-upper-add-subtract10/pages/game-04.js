(function () {
  // 弹弓打灯：灯板上有十盏亮着的灯。拉开弹弓、瞄准、松手，按任务打灭几盏灯。
  // 第1关“打灭几盏”，第2关“只留下几盏亮着”，第3关蓝灯绿灯：先打灭全部蓝灯，再打灭全部绿灯。
  // 灯板挂在墙上，小球朝墙飞去：落在哪盏灯上就打中哪盏，途中不会碰到别的灯（拉弹弓时显示落点准星）。
  var Dr = K.draw;
  var SX = 230, SY = 470, PULL = 150, KV = 9.8, G = 900, LR = 36, TH = 0.75;
  var LEVELS = [
    [{ t: 'take', k: 2 }, { t: 'take', k: 3 }],
    [{ t: 'keep', k: 7 }, { t: 'keep', k: 4 }],
    [{ t: 'color', blue: 4, c: 'blue' }, { t: 'color', blue: 4, c: 'green' }]
  ];
  function lampPos(i) { return { x: 772 + (i % 5) * 96, y: 236 + Math.floor(i / 5) * 118 }; }
  function goalText(m) {
    if (m.t === 'take') return '打灭 ' + m.k + ' 盏灯';
    if (m.t === 'keep') return '只留下 ' + m.k + ' 盏亮着';
    return '把' + (m.c === 'blue' ? '蓝' : '绿') + '灯全部打灭';
  }
  function startRound(g) {
    var d = g.data, m = d.tasks[d.round];
    d.m = m; d.roundMiss = 0; d.off = 0; d.win = null; d.ball = null; d.drag = false; d.pull = { x: 0, y: 0 }; d.auto = null;
    d.lamps = [];
    for (var i = 0; i < 10; i++) d.lamps.push({ on: true, col: m.t === 'color' ? (i < m.blue ? 'blue' : 'green') : 'warm', flash: 0, relight: 0 });
    d.need = m.t === 'take' ? m.k : m.t === 'keep' ? 10 - m.k : (m.c === 'blue' ? m.blue : 10 - m.blue);
    g.banner(goalText(m), m.t === 'keep' ? '十盏里要打灭几盏？' : '拉开弹弓，瞄准，松手', 2.2);
  }
  function lit(d) { return d.lamps.filter(function (l) { return l.on; }).length; }
  function wanted(d, l) { return l.on && (d.m.t !== 'color' || l.col === d.m.c); }
  function fire(g, vx, vy) { var d = g.data; d.ball = { x: SX, y: SY, vx: vx, vy: vy, t: 0 }; d.pull = { x: 0, y: 0 }; K.sfx.whoosh(); }
  function solve(d, idx) {
    var tp = lampPos(idx), vx = (tp.x - SX) / TH, vy = (tp.y - SY - 0.5 * G * TH * TH) / TH, px = -vx / KV, py = -vy / KV;
    return Math.hypot(px, py) <= PULL - 4 ? { vx: vx, vy: vy, px: px, py: py } : null;
  }
  function landing(vx, vy) { return { x: SX + vx * TH, y: SY + vy * TH + 0.5 * G * TH * TH }; }
  function hit(g, i) {
    var d = g.data, l = d.lamps[i], p = lampPos(i);
    l.on = false; l.flash = 0.5; g.sparkle(p.x, p.y, '#FFE066'); K.sfx.pop();
    var wrongColor = d.m.t === 'color' && l.col !== d.m.c;
    if (!wrongColor) d.off++;
    if (wrongColor || d.off > d.need) {
      if (!wrongColor) d.off--;
      l.relight = 0.8; g.shake(0.4); d.roundMiss++;
      g.miss(); K.sfx.no();
      if (wrongColor) g.say(d.roundMiss === 1 ? '先看上面的要求，再看看这盏的颜色' : '只打' + (d.m.c === 'blue' ? '蓝' : '绿') + '灯', 'no');
      else g.say(d.roundMiss === 1 ? '打多了！灯会再亮起来' : '数一数：要打灭几盏？', 'no');
      return;
    }
    if (d.off === d.need) {
      d.win = { t: 0 }; K.sfx.coin(); g.confetti(40);
      K.log.push('sub:10-' + d.need + '=' + (10 - d.need));
    }
  }

  var game = K.game({
    levels: 3,
    finishMark: '★★★',
    starsFor: function () { return 3; },
    winPause: 2,
    levelName: function (l) { return ['打灭几盏，就是减几', '留下几盏，要打灭几盏？', '蓝灯绿灯，打哪种就减哪种'][l]; },
    winText: function (l) { return ['从 10 里拿走几，就减几。', '10 减几等于剩下的，先想好再打。', '同一块灯板，拿走的颜色不同，减法也不同。'][l]; },
    doneTitle: '灯都打对啦！',
    doneText: '减法从 10 开始：拿走几，就减几；剩下的就是得数。',
    bubbleAt: function () { return { x: 980, y: 108 }; },
    reset: function (g, level) {
      var tasks = g.autoLoop ? [{ t: 'take', k: 1 }] : LEVELS[level];
      g.data = { level: level, round: 0, rounds: tasks.length, tasks: tasks, lamps: [], off: 0, need: 0 };
      startRound(g);
    },
    autopilot: function (g, dt) {
      var d = g.data;
      if (d.win || d.ball) return;
      if (!d.auto) {
        if (d.off >= d.need) return;
        var s = null;
        for (var i = 0; i < 10 && !s; i++) if (wanted(d, d.lamps[i]) && d.lamps[i].relight <= 0) s = solve(d, i);
        if (!s) return;
        d.auto = { s: s, t: 0 };
      }
      d.auto.t += dt;
      var q = Math.min(1, d.auto.t / 0.45);
      d.drag = true; d.pull = { x: d.auto.s.px * q, y: d.auto.s.py * q };
      if (d.auto.t > 0.6) { d.drag = false; fire(g, d.auto.s.vx, d.auto.s.vy); d.auto = null; }
    },
    update: function (g, dt) {
      var d = g.data;
      d.lamps.forEach(function (l) { l.flash = Math.max(0, l.flash - dt); if (l.relight > 0) { l.relight -= dt; if (l.relight <= 0) { l.on = true; l.flash = 0.4; } } });
      if (d.win) {
        d.win.t += dt;
        if (d.win.t > 2.8) { d.round++; if (d.round >= d.rounds) { d.win = null; g.win(); return; } startRound(g); }
        return;
      }
      if (!g.auto) {
        var pd = Math.hypot(g.pointer.x - (SX + d.pull.x), g.pointer.y - (SY + d.pull.y));
        if (g.pointer.down && !d.ball && (d.drag || pd < 130)) {
          d.drag = true; var px = g.pointer.x - SX, py = g.pointer.y - SY, pl = Math.hypot(px, py) || 1;
          if (pl > PULL) { px = px / pl * PULL; py = py / pl * PULL; }
          d.pull = { x: px, y: py };
        } else if (d.drag && !g.pointer.down) {
          d.drag = false;
          if (Math.hypot(d.pull.x, d.pull.y) > 24) fire(g, -d.pull.x * KV, -d.pull.y * KV); else d.pull = { x: 0, y: 0 };
        }
      }
      var b = d.ball;
      if (b) {
        b.t = Math.min(TH, b.t + dt); b.x = SX + b.vx * b.t; b.y = SY + b.vy * b.t + 0.5 * G * b.t * b.t;
        if (b.t >= TH) {
          d.ball = null; var best = -1, bd = LR + 16;
          for (var i = 0; i < 10; i++) { var p = lampPos(i), dd = Math.hypot(b.x - p.x, b.y - p.y); if (dd < bd) { bd = dd; best = i; } }
          if (best >= 0 && d.lamps[best].on) hit(g, best);
          else {
            g.miss();
            g.burst(b.x, b.y, { n: 6, color: '#C8A27A', lift: 0 });
            g.say('看准星，再试着对准一盏亮灯', 'no');
          }
        }
      }
    },
    draw: function (g, c) {
      var d = g.data && g.data.lamps ? g.data : { lamps: [], pull: { x: 0, y: 0 } };
      var wall = c.createLinearGradient(0, 0, 0, 720); wall.addColorStop(0, '#FBEED7'); wall.addColorStop(1, '#F3DDB8');
      c.fillStyle = wall; c.fillRect(0, 0, 1280, 720);
      c.fillStyle = '#C9A27A'; c.fillRect(0, 640, 1280, 80); c.fillStyle = '#B28A62'; for (var x = 0; x < 1280; x += 120) c.fillRect(x, 640, 4, 80);
      c.fillStyle = '#7A5230'; Dr.rr(c, 700, 160, 520, 300, 26); c.fill();
      c.fillStyle = '#3A2A20'; Dr.rr(c, 714, 174, 492, 272, 18); c.fill();
      c.fillStyle = '#7A5230'; c.fillRect(940, 460, 40, 180);
      d.lamps.forEach(function (l, i) {
        var p = lampPos(i), on = l.on, col = l.col === 'blue' ? ['#9FD3FF', '#4C8DDB'] : l.col === 'green' ? ['#B6F0A8', '#40A845'] : ['#FFF3A0', '#FFC531'];
        if (on) { c.fillStyle = 'rgba(255,240,150,' + (0.25 + 0.1 * Math.sin(g.t * 4 + i)) + ')'; Dr.circle(c, p.x, p.y, LR + 16); }
        var gr = c.createRadialGradient(p.x - 10, p.y - 12, 4, p.x, p.y, LR);
        gr.addColorStop(0, on ? '#FFFFFF' : '#8A8A8A'); gr.addColorStop(1, on ? col[1] : '#4E4E4E');
        c.fillStyle = gr; Dr.circle(c, p.x, p.y, LR);
        if (l.col !== 'warm') { c.lineWidth = 6; c.strokeStyle = col[1]; c.beginPath(); c.arc(p.x, p.y, LR + 4, 0, Math.PI * 2); c.stroke(); }
        if (l.flash > 0) { c.fillStyle = 'rgba(255,255,255,' + l.flash + ')'; Dr.circle(c, p.x, p.y, LR + 8); }
      });
      c.strokeStyle = '#6B3E1F'; c.lineWidth = 18; c.lineCap = 'round';
      c.beginPath(); c.moveTo(SX, 640); c.lineTo(SX, 540); c.moveTo(SX, 540); c.lineTo(SX - 46, SY); c.moveTo(SX, 540); c.lineTo(SX + 46, SY); c.stroke();
      var px = SX + d.pull.x, py = SY + d.pull.y;
      c.strokeStyle = '#3B2414'; c.lineWidth = 6; c.beginPath(); c.moveTo(SX - 46, SY); c.lineTo(px, py); c.lineTo(SX + 46, SY); c.stroke();
      if (!d.ball && g.state === 'play') { c.fillStyle = '#E4572E'; Dr.circle(c, px, py, 16); }
      if (d.drag && Math.hypot(d.pull.x, d.pull.y) > 24) {
        var vx = -d.pull.x * KV, vy = -d.pull.y * KV, land = landing(vx, vy);
        c.fillStyle = 'rgba(228,87,46,.5)';
        for (var t = 0.05; t < TH; t += 0.05) Dr.circle(c, SX + vx * t, SY + vy * t + 0.5 * G * t * t, 5 - 2.5 * t / TH);
        c.strokeStyle = '#E4572E'; c.lineWidth = 5; c.beginPath(); c.arc(land.x, land.y, 22, 0, Math.PI * 2); c.stroke();
        c.beginPath(); c.moveTo(land.x - 34, land.y); c.lineTo(land.x + 34, land.y); c.moveTo(land.x, land.y - 34); c.lineTo(land.x, land.y + 34); c.stroke();
      }
      if (d.ball) { var br = 16 - 8 * d.ball.t / TH; c.fillStyle = '#E4572E'; Dr.circle(c, d.ball.x, d.ball.y, br); c.fillStyle = 'rgba(255,255,255,.6)'; Dr.circle(c, d.ball.x - br / 3, d.ball.y - br / 3, br / 3); }
    },
    drawTop: function (g, c) {
      var d = g.data && g.data.m ? g.data : null;
      c.fillStyle = 'rgba(255,253,246,.96)'; Dr.rr(c, 22, 14, 600, 118, 24); c.fill(); c.lineWidth = 4; c.strokeStyle = '#C98A47'; c.stroke();
      if (d) {
        Dr.text(c, goalText(d.m), 322, 52, 38, '#6B4423', { weight: 900 });
        Dr.text(c, '亮着 ' + lit(d) + ' 盏', 322, 104, 30, '#A0521C');
        for (var r = 0; r < d.rounds; r++) { c.fillStyle = r < d.round ? '#58B45C' : r === d.round ? '#FF8A2A' : 'rgba(255,253,246,.92)'; Dr.circle(c, 960 + (r - (d.rounds - 1) / 2) * 38, 44, 13); }
      }
      if (d && d.win) {
        var w = d.win, s = 0.6 + 0.4 * Math.min(1, w.t / 0.35), rest = 10 - d.need;
        var sub = d.m.t === 'color' ? '打灭 ' + d.need + ' 盏' + (d.m.c === 'blue' ? '蓝' : '绿') + '灯，还亮着 ' + rest + ' 盏' : '10 盏里打灭 ' + d.need + ' 盏，还亮着 ' + rest + ' 盏';
        c.save(); c.translate(375, 300); c.scale(s, s);
        c.fillStyle = '#FF8A2A'; Dr.rr(c, -330, -80, 660, 160, 34); c.fill();
        Dr.text(c, '10 − ' + d.need + ' = ' + rest, 0, -26, 62, '#FFF', { weight: 900 });
        Dr.text(c, sub, 0, 42, 32, '#FFF3E0');
        c.restore();
      }
    }
  });
  game.follow('#as10b-board', function () { return { x: 700, y: 160, w: 520, h: 300 }; });
  game.follow('#as10b-sling', function () { return { x: SX - 90, y: SY - 60, w: 180, h: 230 }; });
  game.follow('#as10b-goal', function () { return { x: 22, y: 14, w: 600, h: 118 }; });
  K.ready({ emoji: '灯牌工坊', title: '弹弓打灯', sub: '拉开弹弓瞄准灯板，按任务打灭几盏灯' });
})();
