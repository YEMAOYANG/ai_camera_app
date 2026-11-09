(function () {
  // 降落伞凑十：花架上已经有几盆幼苗，天上用降落伞送来装着 1～5 盆的托盘。
  // 左右移动小兔接住“正好能把花架摆满”的那一盘。第1关按 9、8、7、6、5 的顺序；第2关顺序打乱，还有小虫捣乱。
  var Dr = K.draw;
  var GROUND = 628, TOP = GROUND - 112, HALF = 84;
  var PAT = { 1: [[0, 0]], 2: [[-26, 0], [26, 0]], 3: [[-36, 12], [0, -12], [36, 12]], 4: [[-26, -14], [26, -14], [-26, 14], [26, 14]], 5: [[-40, -14], [40, -14], [0, 0], [-40, 14], [40, 14]] };
  var CHUTES = [['#FF6B6B', '#FFF3E0'], ['#4DABF7', '#FFF3E0'], ['#FFD43B', '#FFF3E0'], ['#9775FA', '#FFF3E0']];
  var img = new Image(), imgOk = false;
  img.onload = function () { imgOk = true; };
  img.src = '__IMG:seedling__';
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pot(c, x, y, s) {
    if (imgOk) { c.drawImage(img, x - s / 2, y - s / 2, s, s); return; }
    c.fillStyle = '#C8743F'; c.beginPath(); c.moveTo(x - s * 0.3, y); c.lineTo(x + s * 0.3, y); c.lineTo(x + s * 0.22, y + s * 0.4); c.lineTo(x - s * 0.22, y + s * 0.4); c.closePath(); c.fill();
    c.fillStyle = '#5BB655'; Dr.circle(c, x - s * 0.13, y - s * 0.12, s * 0.14); Dr.circle(c, x + s * 0.13, y - s * 0.15, s * 0.14);
  }
  function cell(i) { return { x: 44 + (i % 5) * 72 + 32, y: 74 + Math.floor(i / 5) * 72 + 32 }; }
  function half(it) { return it.k === 'tray' ? 42 : 22; }

  function startRound(g) {
    var d = g.data, k;
    if (d.level === 0) k = [9, 8, 7, 6, 5][d.round];
    else { var pool = [5, 6, 7, 8, 9].filter(function (v) { return v !== d.lastK; }); k = pool[Math.floor(Math.random() * pool.length)]; }
    d.lastK = k; d.have = k; d.shown = k; d.need = 10 - k; d.roundMiss = 0; d.since = 0; d.hint = 0; d.stop = false;
    d.items = d.items.filter(function (it) { return it.k === 'bug' && it.st === 'fall'; });
    d.spawnT = 0.8;
    g.banner('花架上有 ' + k + ' 盆', '还差几盆，才能凑成 10？', 2);
  }
  function spawnTray(d) {
    var n;
    if (d.since >= 2 || Math.random() < 0.42) { n = d.need; d.since = 0; }
    else { var opts = [1, 2, 3, 4, 5].filter(function (v) { return v !== d.need; }); n = opts[Math.floor(Math.random() * opts.length)]; d.since++; }
    var x, tries = 0;
    do { x = rnd(160, 1120); tries++; } while (tries < 12 && d.items.some(function (o) { return o.k === 'tray' && o.st === 'fall' && Math.abs(o.x - x) < 300; }));
    d.items.push({ k: 'tray', n: n, x: x, y: -60, vy: rnd(d.speed[0], d.speed[1]), ph: rnd(0, 6), t: 0, chute: 1, col: CHUTES[Math.floor(Math.random() * 4)], st: 'fall' });
  }

  function drawRabbit(g, c, d) {
    var x = d.px, lean = Math.max(-0.14, Math.min(0.14, d.pvx / 2600)), sq = d.squash;
    c.fillStyle = 'rgba(30,60,20,.25)'; c.beginPath(); c.ellipse(x, GROUND + 6, 90, 15, 0, 0, Math.PI * 2); c.fill();
    c.save(); c.translate(x, GROUND); c.rotate(lean); c.scale(1 + 0.08 * sq, 1 - 0.1 * sq);
    c.fillStyle = '#E9E2DA'; Dr.rr(c, -44, -38, 32, 40, 14); c.fill(); Dr.rr(c, 12, -38, 32, 40, 14); c.fill();
    c.fillStyle = '#F7F3EE'; c.beginPath(); c.ellipse(0, -92, 58, 62, 0, 0, Math.PI * 2); c.fill();
    var hy = -176, ear = Math.sin(g.t * 3) * 0.06;
    [-1, 1].forEach(function (s) {
      c.save(); c.translate(s * 22, hy - 40); c.rotate(s * 0.18 + ear);
      c.fillStyle = '#F7F3EE'; c.beginPath(); c.ellipse(0, -46, 17, 50, 0, 0, Math.PI * 2); c.fill();
      c.fillStyle = '#F9B9C7'; c.beginPath(); c.ellipse(0, -46, 8, 36, 0, 0, Math.PI * 2); c.fill(); c.restore();
    });
    c.fillStyle = '#FFFFFF'; Dr.circle(c, 0, hy, 54);
    c.fillStyle = '#2A1A10'; Dr.circle(c, -20, hy - 8, 7); Dr.circle(c, 20, hy - 8, 7);
    c.fillStyle = '#FFF'; Dr.circle(c, -18, hy - 10, 2.4); Dr.circle(c, 22, hy - 10, 2.4);
    c.fillStyle = '#F48FA5'; c.beginPath(); c.ellipse(0, hy + 10, 7, 5, 0, 0, Math.PI * 2); c.fill();
    c.strokeStyle = '#8A5A50'; c.lineWidth = 3; c.lineCap = 'round'; c.beginPath(); c.moveTo(-8, hy + 20); c.quadraticCurveTo(0, hy + 27, 8, hy + 20); c.stroke();
    c.fillStyle = 'rgba(255,120,140,.3)'; Dr.circle(c, -34, hy + 12, 9); Dr.circle(c, 34, hy + 12, 9);
    c.fillStyle = '#C8862F'; c.beginPath(); c.moveTo(-88, -112); c.lineTo(88, -112); c.lineTo(70, -46); c.lineTo(-70, -46); c.closePath(); c.fill();
    c.save(); c.clip(); c.strokeStyle = 'rgba(120,70,20,.55)'; c.lineWidth = 3;
    for (var yy = -104; yy < -46; yy += 12) { c.beginPath(); c.moveTo(-90, yy); c.lineTo(90, yy); c.stroke(); }
    for (var xx = -90; xx <= 90; xx += 16) { c.beginPath(); c.moveTo(xx, -112); c.lineTo(xx * 0.8, -46); c.stroke(); }
    c.restore();
    c.fillStyle = '#E3A24A'; Dr.rr(c, -94, -122, 188, 16, 8); c.fill();
    c.fillStyle = '#E9E2DA'; Dr.circle(c, -82, -112, 15); Dr.circle(c, 82, -112, 15);
    c.restore();
  }
  function drawTray(c, it) {
    c.save(); c.translate(it.x, it.y); c.rotate(it.rot || 0);
    var ch = it.chute;
    if (ch > 0.02) {
      c.save(); c.globalAlpha *= ch; var cy = -120;
      c.strokeStyle = 'rgba(80,55,35,.75)'; c.lineWidth = 2;
      [-66, -22, 22, 66].forEach(function (sx) { c.beginPath(); c.moveTo(sx * 1.25, cy); c.lineTo(sx * 0.8, -40); c.stroke(); });
      for (var k = 0; k < 6; k++) { c.fillStyle = it.col[k % 2]; c.beginPath(); c.moveTo(0, cy); c.arc(0, cy, 88, Math.PI + k * Math.PI / 6, Math.PI + (k + 1) * Math.PI / 6); c.closePath(); c.fill(); }
      c.restore();
    }
    c.fillStyle = '#7A4A24'; Dr.rr(c, -72, -42, 144, 84, 12); c.fill();
    c.fillStyle = '#FDE7C4'; Dr.rr(c, -64, -34, 128, 68, 9); c.fill();
    (PAT[it.n] || []).forEach(function (p) { pot(c, p[0], p[1] - 2, 40); });
    c.strokeStyle = '#C98A47'; c.lineWidth = 8; Dr.rr(c, -68, -38, 136, 76, 11); c.stroke();
    c.restore();
  }
  function drawBug(c, it, t) {
    c.save(); c.translate(it.x, it.y);
    c.fillStyle = '#7BC043'; for (var i = 3; i >= 0; i--) Dr.circle(c, -i * 16, Math.sin(t * 8 + i) * 4, 15 - i);
    c.fillStyle = '#5A9A2E'; Dr.circle(c, 12, 0, 17);
    c.fillStyle = '#FFF'; Dr.circle(c, 18, -5, 6); c.fillStyle = '#1F1A10'; Dr.circle(c, 20, -5, 3);
    c.strokeStyle = '#3E6B1F'; c.lineWidth = 2.5; c.beginPath(); c.moveTo(14, -14); c.lineTo(20, -28); c.moveTo(22, -12); c.lineTo(32, -24); c.stroke();
    c.restore();
  }

  var game = K.game({
    levels: 2,
    lives: 3,
    winPause: 2.2,
    levelName: function (l) { return l ? '顺序打乱，小心毛毛虫' : '按顺序凑十'; },
    winText: function () { return '9和1、8和2、7和3、6和4、5和5，都组成 10！'; },
    doneTitle: '花架摆满啦！',
    doneText: '一个部分是几，另一个部分就是 10 减它；两个部分交换，合起来还是 10。',
    failTitle: '毛毛虫太多啦',
    retryText: '先数清空格子，再去接正好的那一盘。',
    bubbleAt: function (g) { return { x: g.data.px || 640, y: GROUND - 310 }; },
    reset: function (g, level) {
      g.data = { level: level, round: 0, rounds: level ? 4 : 5, speed: level ? [135, 165] : [105, 130], items: [], fly: [], px: 640, tx: 640, pvx: 0, squash: 0,
        have: 0, shown: 0, need: 0, spawnT: 1, bugT: 2.5, since: 0, lastK: 0, roundWin: null };
      startRound(g);
    },
    autopilot: function (g) {
      var d = g.data, best = null;
      d.items.forEach(function (it) { if (it.st === 'fall' && it.k === 'tray' && it.n === d.need && (!best || it.y > best.y)) best = it; });
      var tx = best ? best.x : 640;
      d.items.forEach(function (it) {
        if (it.st !== 'fall' || it === best) return;
        var bad = it.k === 'bug' || it.n !== d.need;
        if (bad && it.y + half(it) > TOP - 170 && Math.abs(it.x - tx) < 160 && (!best || it.y > best.y - 40)) tx += it.x < tx ? 130 : -130;
      });
      d.tx = Math.max(100, Math.min(1180, tx));
    },
    update: function (g, dt) {
      var d = g.data;
      if (!g.auto && g.pointer.active) d.tx = Math.max(100, Math.min(1180, g.pointer.x));
      if (g.keys.left) d.tx = Math.max(100, d.tx - 760 * dt);
      if (g.keys.right) d.tx = Math.min(1180, d.tx + 760 * dt);
      var dx = (d.tx - d.px) * (1 - Math.exp(-dt * 11)); dx = Math.max(-1150 * dt, Math.min(1150 * dt, dx));
      d.pvx = dx / Math.max(dt, 0.001); d.px += dx; d.squash = Math.max(0, d.squash - dt * 4);
      if (d.roundWin) {
        d.roundWin.t += dt;
        if (d.roundWin.t > 2.6) { d.roundWin = null; d.round++; if (d.round >= d.rounds) { g.win(); return; } startRound(g); }
      } else if (!d.stop) {
        d.spawnT -= dt;
        if (d.spawnT <= 0) { if (d.items.filter(function (o) { return o.k === 'tray' && o.st === 'fall'; }).length < 2) spawnTray(d); d.spawnT = rnd(d.level ? 1.2 : 1.6, d.level ? 1.5 : 1.9); }
        if (d.level) { d.bugT -= dt; if (d.bugT <= 0) { var bx = rnd(180, 1100); d.items.push({ k: 'bug', x: bx, bx: bx, y: -30, vy: rnd(64, 84), amp: rnd(90, 150), fq: rnd(1.1, 1.6), ph: rnd(0, 6), t: 0, st: 'fall' }); d.bugT = rnd(2.6, 3.6); } }
      }
      d.items.forEach(function (it) {
        it.t += dt;
        if (it.st === 'fall') {
          it.y += it.vy * dt;
          if (it.k === 'tray') { it.x += Math.sin(it.t * 1.3 + it.ph) * 26 * dt; it.rot = Math.sin(it.t * 1.6 + it.ph) * 0.06; }
          else it.x = it.bx + Math.sin(it.t * it.fq + it.ph) * it.amp;
          var bottom = it.y + half(it);
          if (!d.stop && !d.roundWin && bottom >= TOP && bottom <= TOP + 46 && Math.abs(it.x - d.px) <= HALF + (it.k === 'tray' ? 34 : 12)) {
            d.squash = 1;
            if (it.k === 'bug') { it.st = 'flee'; it.vy = -320; g.hurt(); if (g.state === 'play') g.say('哎呀！小心毛毛虫', 'no'); return; }
            if (it.n === d.need) {
              it.st = 'poof'; it.t = 0; K.sfx.coin(); d.stop = true; g.burst(it.x, TOP, { n: 14 });
              for (var j = 0; j < it.n; j++) { var to = cell(d.have + j); d.fly.push({ x0: it.x + (j - (it.n - 1) / 2) * 26, y0: TOP - 10, x1: to.x, y1: to.y, t: -j * 0.14, idx: d.have + j }); }
              d.pending = { k: d.have, n: it.n }; d.have = 10;
              d.items.forEach(function (o) { if (o !== it && o.k === 'tray' && o.st === 'fall') { o.st = 'bounce'; o.vy = -220; o.vx = (o.x < 640 ? -1 : 1) * 260; o.vr = (o.x < 640 ? -1 : 1) * 2; } });
            } else {
              g.miss(); d.roundMiss++; K.sfx.no(); g.shake(0.5);
              var many = it.n > d.need, side = it.x < d.px ? -1 : 1;
              it.st = 'bounce'; it.vy = -480; it.vx = side * rnd(220, 300); it.vr = side * rnd(3, 5);
              if (many) for (var s = 0; s < it.n - d.need; s++) g.burst(it.x, TOP - 20, { n: 2, color: '#C8743F', size: 9, speed: 300 });
              if (d.roundMiss === 1) g.say(many ? '太多啦，花架放不下！' : '还不够，格子还空着呢！', 'no');
              else { d.hint = 3; g.say('数一数空格子，再去接', 'no'); }
            }
            return;
          }
          if (it.st === 'fall' && bottom > GROUND + 8) { if (it.k === 'bug') { it.st = 'flee'; it.vy = -260; } else { it.st = 'ground'; it.t = 0; } }
        } else if (it.st === 'bounce') { it.vy += 1100 * dt; it.y += it.vy * dt; it.x += it.vx * dt; it.rot = (it.rot || 0) + it.vr * dt; it.chute = Math.max(0, it.chute - dt * 4); if (it.y > 900 || it.x < -220 || it.x > 1500) it.st = 'gone'; }
        else if (it.st === 'flee') { it.y += it.vy * dt; if (it.y < -80) it.st = 'gone'; }
        else if (it.st === 'ground') { it.chute = Math.max(0, it.chute - dt * 3); if (it.t > 0.9) it.st = 'gone'; }
        else if (it.st === 'poof' && it.t > 0.25) it.st = 'gone';
      });
      d.items = d.items.filter(function (it) { return it.st !== 'gone'; });
      d.fly.forEach(function (f) {
        f.t += dt;
        if (f.t >= 0.55 && !f.done) {
          f.done = true; d.shown = Math.max(d.shown, f.idx + 1); K.sfx.tick(f.idx + 1); g.float(f.idx + 1, f.x1, f.y1 - 34); g.sparkle(f.x1, f.y1);
          if (d.shown >= 10 && d.pending) { var p = d.pending; d.pending = null; d.roundWin = { t: 0, k: p.k, n: p.n }; K.sfx.win(); g.confetti(50); }
        }
      });
      d.fly = d.fly.filter(function (f) { return !f.done; });
      if (d.hint > 0) d.hint -= dt;
    },
    draw: function (g, c) {
      var d = g.data && g.data.items ? g.data : { items: [], fly: [], px: 640, pvx: 0, squash: 0, shown: 0 };
      var sky = c.createLinearGradient(0, 0, 0, GROUND); sky.addColorStop(0, '#6FC3F5'); sky.addColorStop(0.55, '#BFE7FB'); sky.addColorStop(1, '#FFF1C9');
      c.fillStyle = sky; c.fillRect(0, 0, 1280, 720);
      Dr.cloud(c, (180 + g.t * 12) % 1420 - 70, 300, 1); Dr.cloud(c, (900 + g.t * 8) % 1420 - 70, 250, 0.8);
      c.fillStyle = 'rgba(220,244,240,.95)'; c.strokeStyle = '#7FB9A8'; c.lineWidth = 4;
      c.beginPath(); c.moveTo(880, 520); c.lineTo(880, 420); c.quadraticCurveTo(1030, 300, 1180, 420); c.lineTo(1180, 520); c.closePath(); c.fill(); c.stroke();
      var gr = c.createLinearGradient(0, GROUND - 30, 0, 720); gr.addColorStop(0, '#7CCC55'); gr.addColorStop(1, '#4C9C37');
      c.fillStyle = gr; c.fillRect(0, GROUND - 18, 1280, 720);
      d.items.forEach(function (it) { if (it.st === 'ground') { c.save(); c.globalAlpha = Math.max(0, 1 - it.t / 0.9); drawTray(c, it); c.restore(); } });
      drawRabbit(g, c, d);
      d.items.forEach(function (it) {
        if (it.st === 'ground') return;
        c.save(); if (it.st === 'poof') c.globalAlpha = Math.max(0, 1 - it.t / 0.25);
        if (it.k === 'tray') drawTray(c, it); else drawBug(c, it, g.t);
        c.restore();
      });
    },
    drawTop: function (g, c) {
      var d = g.data && g.data.items ? g.data : { shown: 0, fly: [] };
      c.fillStyle = 'rgba(255,253,246,.95)'; Dr.rr(c, 22, 18, 540, 206, 24); c.fill(); c.lineWidth = 4; c.strokeStyle = '#C98A47'; c.stroke();
      Dr.text(c, '花架', 70, 46, 30, '#8A5A24');
      for (var i = 0; i < 10; i++) {
        var p = cell(i);
        c.fillStyle = i < d.shown ? '#FFE7C2' : '#F3E6CF'; Dr.rr(c, p.x - 32, p.y - 32, 64, 64, 12); c.fill(); c.lineWidth = 2.5; c.strokeStyle = '#D8C3A0'; c.stroke();
        if (i < d.shown) pot(c, p.x, p.y + 2, 58);
        else if (d.hint > 0) { c.fillStyle = 'rgba(255,138,42,' + (0.25 + 0.2 * Math.sin(g.t * 8)) + ')'; Dr.rr(c, p.x - 32, p.y - 32, 64, 64, 12); c.fill(); Dr.text(c, String(i - d.shown + 1), p.x, p.y + 2, 38, '#C47A12', { weight: 900 }); }
      }
      c.fillStyle = '#58B45C'; Dr.rr(c, 428, 40, 116, 166, 20); c.fill();
      Dr.text(c, String(d.shown), 486, 112, 96, '#FFF', { weight: 900 }); Dr.text(c, '盆', 486, 180, 28, '#FFF');
      if (g.state !== 'ready' && d.level != null) {
        for (var r = 0; r < (d.rounds || 0); r++) { c.fillStyle = r < d.round ? '#58B45C' : r === d.round ? '#FF8A2A' : 'rgba(255,253,246,.92)'; Dr.circle(c, 640 + (r - (d.rounds - 1) / 2) * 36, 40, 12); }
        if (d.level === 1) for (var h = 0; h < 3; h++) Dr.heart(c, 1132 + h * 48, 44, 17, h < g.lives);
      }
      (d.fly || []).forEach(function (f) {
        if (f.t < 0) return;
        var q = Math.min(1, f.t / 0.55), e = 1 - Math.pow(1 - q, 3);
        pot(c, f.x0 + (f.x1 - f.x0) * e, f.y0 + (f.y1 - f.y0) * e - Math.sin(q * Math.PI) * 160, 60 - 6 * q);
      });
      if (d.roundWin) {
        var w = d.roundWin, s = 0.6 + 0.4 * Math.min(1, w.t / 0.35);
        c.save(); c.translate(640, 380); c.scale(s, s);
        c.fillStyle = '#FF8A2A'; Dr.rr(c, -330, -84, 660, 168, 36); c.fill();
        Dr.text(c, w.k + ' 和 ' + w.n + ' 组成 10', 0, -26, 66, '#FFF', { weight: 900 });
        Dr.text(c, '换一换：' + w.n + ' 和 ' + w.k + ' 也组成 10', 0, 44, 36, '#FFF3E0');
        c.restore();
      }
    }
  });
  game.follow('#r10e-shelf', function () { return { x: 22, y: 18, w: 540, h: 206 }; });
  game.follow('#r10e-rabbit', function (g) { var x = g.data && g.data.px ? g.data.px : 640; return { x: x - 95, y: GROUND - 260, w: 190, h: 270 }; });
  game.follow('#r10e-sky', function () { return { x: 140, y: 240, w: 1000, h: 230 }; });
  K.ready({ emoji: '🪂', title: '降落伞凑十', sub: '左右移动小兔，接住正好能把花架摆满的那一盘' });
})();
