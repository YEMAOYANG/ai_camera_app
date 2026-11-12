(function () {
  // 切灯泡：灯泡从下面抛上来，每个灯泡上有一道算式。先算一算，只切开得数等于目标数的灯泡。
  // 第1关找等于 10 的加法；第2关加上 0 和 10（十减零、零加十）；第3关目标数会变（7、4、1），分清十减三和十减七。
  var Dr = K.draw, M = '−', R = 60, GRAV = 760;
  var WAVES = [
    [{ target: 10, need: 6, good: ['1+9', '9+1', '2+8', '8+2', '4+6', '6+4', '5+5'], bad: ['4+5', '2+7', '1+8', '5+4', '6+3', '2+6', '3+5'] }],
    [{ target: 10, need: 6, good: ['10' + M + '0', '0+10', '10+0', '5+5', '6+4', '2+8'], bad: ['10' + M + '1', '10' + M + '10', '0+9', '9+0', '1+8', '10' + M + '2'] }],
    [{ target: 7, need: 2, good: ['10' + M + '3'], bad: ['10' + M + '7', '9+1', '10' + M + '2', '10' + M + '4'] },
     { target: 4, need: 2, good: ['10' + M + '6'], bad: ['10' + M + '4', '6+4', '10' + M + '5', '10' + M + '7'] },
     { target: 1, need: 2, good: ['10' + M + '9'], bad: ['10' + M + '1', '9+1', '10' + M + '8', '10' + M + '10'] }]
  ];
  var DEMO = [{ target: 10, need: 2, good: ['3+7'], bad: ['3+6'] }];
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function value(s) { var m = s.match(/^(\d+)([+−])(\d+)$/); return m[2] === '+' ? +m[1] + +m[3] : +m[1] - +m[3]; }
  function show(s) { return s.replace('+', ' + ').replace(M, ' ' + M + ' '); }
  function wave(d) { return d.waves[d.wave]; }
  function startWave(g) {
    var d = g.data, w = wave(d);
    d.cut = 0; d.since = 0; d.spawnT = 0.6; d.waveMiss = 0;
    g.banner('切出等于 ' + w.target + ' 的灯泡', '先算一算，再切', 2);
  }
  function spawn(d) {
    var w = wave(d), good = d.since >= 2 || Math.random() < 0.45, x = rnd(200, 1080);
    d.since = good ? 0 : d.since + 1;
    d.bulbs.push({ s: good ? pick(w.good) : pick(w.bad), x: x, y: 790, vx: (640 - x) * rnd(0.12, 0.22), vy: -rnd(860, 960), st: 'fly', t: 0, rot: 0, vr: rnd(-1, 1) });
  }
  function segHit(b, x1, y1, x2, y2) {
    var dx = x2 - x1, dy = y2 - y1, l2 = dx * dx + dy * dy, t = l2 ? Math.max(0, Math.min(1, ((b.x - x1) * dx + (b.y - y1) * dy) / l2)) : 0;
    return Math.hypot(x1 + dx * t - b.x, y1 + dy * t - b.y) < R;
  }
  function slice(g, b) {
    var d = g.data, w = wave(d), v = value(b.s);
    if (v === w.target) {
      b.st = 'cut'; b.t = 0; d.cut++; K.sfx.coin(); g.sparkle(b.x, b.y, '#FFE066'); g.float(show(b.s) + ' = ' + v, b.x, b.y - 80, { size: 40, color: '#2F8A3A' });
      K.log.push('cut:' + b.s);
      if (d.cut >= w.need) {
        d.bulbs.forEach(function (o) { if (o.st === 'fly') o.st = 'fade'; });
        if (d.wave + 1 < d.waves.length) { d.wave++; g.after(0.9, function () { if (g.state === 'play') startWave(g); }); d.pause = 0.9; }
        else g.after(0.6, function () { g.win(); });
      }
      return;
    }
    b.st = 'bad'; b.t = 0; g.burst(b.x, b.y, { n: 12, color: '#9AA4AE' }); d.waveMiss++;
    g.miss(); K.sfx.no();
    g.say(d.waveMiss === 1 ? '算一算：它等于 ' + w.target + ' 吗？' : show(b.s) + ' 等于 ' + v + '，不是 ' + w.target, 'no');
  }
  function drawBulb(c, b, t) {
    c.save(); c.translate(b.x, b.y); c.rotate(b.rot);
    c.fillStyle = 'rgba(255,240,150,' + (0.18 + 0.08 * Math.sin(t * 5 + b.x)) + ')'; Dr.circle(c, 0, 0, R + 18);
    c.fillStyle = '#8E9AA6'; Dr.rr(c, -26, R - 8, 52, 40, 8); c.fill();
    c.strokeStyle = '#6B7782'; c.lineWidth = 4; for (var k = 0; k < 3; k++) { c.beginPath(); c.moveTo(-26, R + 2 + k * 11); c.lineTo(26, R + 2 + k * 11); c.stroke(); }
    var gr = c.createRadialGradient(-18, -20, 6, 0, 0, R); gr.addColorStop(0, '#FFFFFF'); gr.addColorStop(1, '#FFD84D');
    c.fillStyle = gr; Dr.circle(c, 0, 0, R);
    c.rotate(-b.rot); Dr.text(c, show(b.s), 0, 2, b.s.length > 4 ? 30 : 36, '#5A3A12', { weight: 900 });
    c.restore();
  }
  function drawHalf(c, b, side, t) {
    c.save(); c.translate(b.x + side * (20 + b.t * 260), b.y + b.t * b.t * 400); c.rotate(side * b.t * 3);
    c.beginPath(); c.rect(side > 0 ? 0 : -R - 30, -R - 30, R + 30, 2 * R + 80); c.clip();
    c.translate(-side * 0, 0); var tmp = { x: 0, y: 0, rot: 0, s: b.s }; drawBulb(c, tmp, t);
    c.restore();
  }

  var game = K.game({
    levels: 3,
    finishMark: '★★★',
    starsFor: function () { return 3; },
    winPause: 2,
    levelName: function (l) { return ['找等于 10 的加法', '还有 0 和 10', '目标数会变'][l]; },
    winText: function (l) { return ['合起来是 10 的，一个都没放过！', '十减零还是十，零加十也是十！', '十减三是七，十减七是三，分清啦！'][l]; },
    doneTitle: '灯泡都切对啦！',
    doneText: '先算出得数，再看等不等于要找的数。',
    bubbleAt: function () { return { x: 640, y: 170 }; },
    reset: function (g, level) {
      g.data = { level: level, wave: 0, waves: g.autoLoop ? DEMO : WAVES[level], bulbs: [], trail: [], pause: 0 };
      startWave(g);
    },
    autopilot: function (g) {
      var d = g.data, w = wave(d);
      if (d.pause > 0) return;
      for (var i = 0; i < d.bulbs.length; i++) {
        var b = d.bulbs[i];
        if (b.st !== 'fly' || value(b.s) !== w.target || b.vy < -140 || b.y > 600) continue;
        var x1 = b.x - 100, x2 = b.x + 100, y1 = b.y - 30, y2 = b.y + 30;
        var clash = d.bulbs.some(function (o) { return o !== b && o.st === 'fly' && segHit(o, x1, y1, x2, y2); });
        if (clash) continue;
        d.trail = [{ x: x1, y: y1, t: g.t }, { x: x2, y: y2, t: g.t }];
        slice(g, b);
        return;
      }
    },
    update: function (g, dt) {
      var d = g.data;
      if (d.pause > 0) d.pause -= dt;
      if (!g.auto) {
        if (g.pointer.down) d.trail.push({ x: g.pointer.x, y: g.pointer.y, t: g.t });
        g.taps.forEach(function (p) { if (!p.key) d.trail.push({ x: p.x, y: p.y, t: g.t }); });
      }
      d.trail = d.trail.filter(function (p) { return g.t - p.t < 0.15; });
      if (!g.auto && d.trail.length) {
        for (var i = 0; i < d.bulbs.length; i++) {
          var b = d.bulbs[i]; if (b.st !== 'fly') continue;
          var hit = false;
          if (d.trail.length === 1) hit = Math.hypot(d.trail[0].x - b.x, d.trail[0].y - b.y) < R;
          for (var k = 1; k < d.trail.length && !hit; k++) hit = segHit(b, d.trail[k - 1].x, d.trail[k - 1].y, d.trail[k].x, d.trail[k].y);
          if (hit) { slice(g, b); if (g.state !== 'play') return; }
        }
      }
      if (d.pause <= 0 && g.state === 'play') {
        d.spawnT -= dt;
        if (d.spawnT <= 0) { spawn(d); if (Math.random() < 0.3) spawn(d); d.spawnT = rnd(d.level ? 1.0 : 1.2, d.level ? 1.3 : 1.5); }
      }
      d.bulbs.forEach(function (b) {
        b.t += dt;
        if (b.st === 'fly' || b.st === 'fade') { b.vy += GRAV * dt; b.x += b.vx * dt; b.y += b.vy * dt; b.rot += b.vr * dt; }
        if (b.y > 820 && b.vy > 0) b.st = 'gone';
        if ((b.st === 'cut' || b.st === 'bad') && b.t > 0.8) b.st = 'gone';
        if (b.st === 'fade' && b.t > 0.5) b.st = 'gone';
      });
      d.bulbs = d.bulbs.filter(function (b) { return b.st !== 'gone'; });
    },
    draw: function (g, c) {
      var d = g.data && g.data.bulbs ? g.data : { bulbs: [], trail: [] };
      var sky = c.createLinearGradient(0, 0, 0, 720); sky.addColorStop(0, '#1E2A5A'); sky.addColorStop(1, '#3B4C8C');
      c.fillStyle = sky; c.fillRect(0, 0, 1280, 720);
      c.fillStyle = 'rgba(255,255,255,.7)';
      for (var i = 0; i < 40; i++) { var sx = (i * 197) % 1280, sy = (i * 113) % 520 + 20; Dr.circle(c, sx, sy, 1.5 + (i % 3) * 0.6 + Math.sin(g.t * 2 + i) * 0.6); }
      c.fillStyle = '#2A2340'; c.beginPath(); c.moveTo(0, 720); c.lineTo(0, 650); c.lineTo(160, 620); c.lineTo(320, 660); c.lineTo(520, 610); c.lineTo(760, 655); c.lineTo(980, 615); c.lineTo(1280, 650); c.lineTo(1280, 720); c.fill();
      d.bulbs.forEach(function (b) {
        c.save();
        if (b.st === 'fade') c.globalAlpha = Math.max(0, 1 - b.t / 0.5);
        if (b.st === 'cut') { c.globalAlpha = Math.max(0, 1 - b.t / 0.8); drawHalf(c, b, -1, g.t); drawHalf(c, b, 1, g.t); }
        else if (b.st === 'bad') { c.globalAlpha = Math.max(0, 1 - b.t / 0.5); c.filter = 'grayscale(1)'; drawBulb(c, b, g.t); }
        else drawBulb(c, b, g.t);
        c.restore();
      });
      if (d.trail.length > 1) {
        c.strokeStyle = 'rgba(255,255,255,.9)'; c.lineWidth = 10; c.lineCap = 'round'; c.lineJoin = 'round';
        c.beginPath(); c.moveTo(d.trail[0].x, d.trail[0].y); for (var k = 1; k < d.trail.length; k++) c.lineTo(d.trail[k].x, d.trail[k].y); c.stroke();
        c.strokeStyle = 'rgba(120,200,255,.6)'; c.lineWidth = 20; c.stroke();
      }
    },
    drawTop: function (g, c) {
      var d = g.data && g.data.bulbs ? g.data : null;
      if (!d) return;
      var w = wave(d);
      c.fillStyle = 'rgba(255,253,246,.96)'; Dr.rr(c, 340, 14, 600, 100, 26); c.fill(); c.lineWidth = 4; c.strokeStyle = '#FFC531'; c.stroke();
      Dr.text(c, '切出等于', 520, 64, 38, '#6B4423', { weight: 900 }); Dr.text(c, String(w.target), 670, 62, 64, '#E4572E', { weight: 900 }); Dr.text(c, '的灯泡', 800, 64, 38, '#6B4423', { weight: 900 });
      c.fillStyle = 'rgba(255,253,246,.96)'; Dr.rr(c, 960, 14, 298, 100, 26); c.fill(); c.lineWidth = 4; c.strokeStyle = '#C98A47'; c.stroke();
      Dr.text(c, '切对 ' + d.cut + ' / ' + w.need, 1109, 64, 32, '#6B4423', { weight: 900 });
      if (d.waves.length > 1) for (var r = 0; r < d.waves.length; r++) { c.fillStyle = r < d.wave ? '#58B45C' : r === d.wave ? '#FF8A2A' : 'rgba(255,253,246,.92)'; Dr.circle(c, 160 + r * 40, 60, 13); }
    }
  });
  game.follow('#as10d-target', function () { return { x: 340, y: 14, w: 600, h: 100 }; });
  game.follow('#as10d-sky', function () { return { x: 60, y: 140, w: 1160, h: 500 }; });
  game.follow('#as10d-score', function () { return { x: 960, y: 14, w: 298, h: 100 }; });
  K.ready({ emoji: '灯牌工坊', title: '切灯泡', sub: '先算一算，用手指划开得数等于目标数的灯泡' });
})();
