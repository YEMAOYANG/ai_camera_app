(function () {
  // 小熊跑酷收幼苗：自动向前跑，点一下（或按空格）跳起来，收集幼苗放上花架。第1关一盆一盆数，第2关两盆两盆数。
  var Dr = K.draw;
  var GROUND = 610, BX = 300, JUMP = 830, GRAV = 2200;
  var img = new Image(), imgOk = false;
  img.onload = function () { imgOk = true; };
  img.src = '__IMG:seedling__';

  function rnd(a, b) { return a + Math.random() * (b - a); }
  function cell(i) { return { x: 44 + (i % 5) * 72 + 32, y: 74 + Math.floor(i / 5) * 72 + 32 }; }
  function pot(c, x, y, s) {
    if (imgOk) { c.drawImage(img, x - s / 2, y - s / 2, s, s); return; }
    c.fillStyle = '#C8743F'; c.beginPath(); c.moveTo(x - s * 0.3, y); c.lineTo(x + s * 0.3, y); c.lineTo(x + s * 0.22, y + s * 0.4); c.lineTo(x - s * 0.22, y + s * 0.4); c.closePath(); c.fill();
    c.fillStyle = '#5BB655'; Dr.circle(c, x - s * 0.13, y - s * 0.12, s * 0.14); Dr.circle(c, x + s * 0.13, y - s * 0.15, s * 0.14); Dr.circle(c, x, y - s * 0.3, s * 0.13);
  }
  function jump(g) { var d = g.data; if (!d.onGround || d.stumble > 0) return; d.vy = -JUMP; d.onGround = false; K.sfx.jump(); }

  function drawWorld(g, c) {
    var d = g.data, s = d.scroll || 0;
    var sky = c.createLinearGradient(0, 0, 0, GROUND);
    sky.addColorStop(0, '#78C9F5'); sky.addColorStop(0.6, '#C9ECFB'); sky.addColorStop(1, '#FFF3D2');
    c.fillStyle = sky; c.fillRect(0, 0, 1280, 720);
    c.fillStyle = '#FFE07A'; Dr.circle(c, 1130, 120, 50);
    [[200, 120, 1], [620, 80, 0.8], [980, 170, 1.15]].forEach(function (cl, i) { Dr.cloud(c, ((cl[0] - s * 0.05 * (i + 1)) % 1500 + 1500) % 1500 - 110, cl[1], cl[2]); });
    c.fillStyle = '#A9DCAF'; c.beginPath(); c.moveTo(0, 720);
    for (var x = 0; x <= 1280; x += 20) c.lineTo(x, 470 - 40 * Math.sin((x + s * 0.2) * 0.006) - 18 * Math.sin((x + s * 0.2) * 0.017));
    c.lineTo(1280, 720); c.closePath(); c.fill();
    // greenhouses passing in the distance
    for (var k = -1; k < 3; k++) {
      var gx = ((k * 760 - s * 0.35) % 1520 + 1520) % 1520 - 260, gy = 470;
      c.fillStyle = 'rgba(220,244,240,.9)'; c.strokeStyle = '#7FB9A8'; c.lineWidth = 4;
      c.beginPath(); c.moveTo(gx, gy + 70); c.lineTo(gx, gy); c.quadraticCurveTo(gx + 110, gy - 90, gx + 220, gy); c.lineTo(gx + 220, gy + 70); c.closePath(); c.fill(); c.stroke();
      c.beginPath(); for (var m = 1; m < 4; m++) { c.moveTo(gx + m * 55, gy + 70); c.lineTo(gx + m * 55, gy - 40 + Math.abs(m - 2) * 22); } c.stroke();
    }
    // fence
    c.fillStyle = '#E8C48F';
    for (var f = 0; f < 18; f++) { var fx = ((f * 90 - s * 0.7) % 1620 + 1620) % 1620 - 90; Dr.rr(c, fx, GROUND - 92, 16, 92, 6); c.fill(); }
    c.fillRect(0, GROUND - 74, 1280, 10); c.fillRect(0, GROUND - 40, 1280, 10);
    // ground
    var gr = c.createLinearGradient(0, GROUND, 0, 720); gr.addColorStop(0, '#7CCC55'); gr.addColorStop(1, '#4C9C37');
    c.fillStyle = gr; c.fillRect(0, GROUND, 1280, 720 - GROUND);
    c.fillStyle = '#D9B47A'; c.fillRect(0, GROUND, 1280, 26);
    c.fillStyle = 'rgba(120,80,30,.25)';
    for (var p = 0; p < 22; p++) { var px = ((p * 64 - s) % 1408 + 1408) % 1408 - 64; c.fillRect(px, GROUND + 10, 26, 5); }
  }
  function drawBear(g, c) {
    var d = g.data, x = BX, y = d.by, run = d.onGround ? Math.sin(g.t * 16) : 0.6;
    var tilt = d.stumble > 0 ? -0.35 : (d.onGround ? 0.04 : -0.08);
    c.fillStyle = 'rgba(30,60,20,.22)'; c.beginPath(); c.ellipse(x, GROUND + 4, 60 - (GROUND - y) * 0.15, 12, 0, 0, Math.PI * 2); c.fill();
    c.save(); c.translate(x, y); c.rotate(tilt);
    c.fillStyle = '#8B5631';
    Dr.rr(c, -34 + run * 12, -44, 28, 46, 12); c.fill(); Dr.rr(c, 6 - run * 12, -44, 28, 46, 12); c.fill();
    c.fillStyle = '#A8683B'; c.beginPath(); c.ellipse(0, -88, 50, 56, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#E9C49B'; c.beginPath(); c.ellipse(4, -78, 30, 36, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#8B5631'; Dr.rr(c, -60, -110 - run * 10, 26, 50, 12); c.fill(); Dr.rr(c, 36, -110 + run * 10, 26, 50, 12); c.fill();
    var hy = -160;
    c.fillStyle = '#A8683B'; Dr.circle(c, -34, hy - 34, 17); Dr.circle(c, 34, hy - 34, 17);
    c.fillStyle = '#E9A98B'; Dr.circle(c, -34, hy - 34, 8); Dr.circle(c, 34, hy - 34, 8);
    c.fillStyle = '#B4733F'; Dr.circle(c, 0, hy, 48);
    c.fillStyle = '#F0D2AD'; c.beginPath(); c.ellipse(10, hy + 14, 22, 17, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#3A2416'; c.beginPath(); c.ellipse(14, hy + 6, 8, 6, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#2A1A10'; Dr.circle(c, -10, hy - 10, 6.5); Dr.circle(c, 22, hy - 10, 6.5);
    c.fillStyle = '#FFF'; Dr.circle(c, -8, hy - 12, 2.3); Dr.circle(c, 24, hy - 12, 2.3);
    c.strokeStyle = '#3A2416'; c.lineWidth = 3; c.lineCap = 'round'; c.beginPath();
    if (d.stumble > 0) { c.arc(12, hy + 30, 7, Math.PI * 1.1, Math.PI * 1.9); } else { c.moveTo(4, hy + 22); c.quadraticCurveTo(12, hy + 29, 20, hy + 22); }
    c.stroke();
    c.fillStyle = 'rgba(255,120,120,.35)'; Dr.circle(c, -24, hy + 12, 8); Dr.circle(c, 36, hy + 12, 8);
    c.restore();
  }
  function drawShelf(g, c) {
    var d = g.data;
    c.fillStyle = 'rgba(255,253,246,.95)'; Dr.rr(c, 22, 18, 540, 206, 24); c.fill();
    c.lineWidth = 4; c.strokeStyle = '#C98A47'; c.stroke();
    Dr.text(c, '花架', 70, 46, 30, '#8A5A24');
    for (var i = 0; i < 10; i++) {
      var p = cell(i);
      c.fillStyle = i < d.shown ? '#FFE7C2' : '#F3E6CF'; Dr.rr(c, p.x - 32, p.y - 32, 64, 64, 12); c.fill();
      c.lineWidth = 2.5; c.strokeStyle = '#D8C3A0'; c.stroke();
      if (i < d.shown) pot(c, p.x, p.y + 2, 58);
    }
    c.fillStyle = '#58B45C'; Dr.rr(c, 428, 40, 116, 166, 20); c.fill();
    Dr.text(c, String(d.shown), 486, 112, 96, '#FFF', { weight: 900 });
    Dr.text(c, '盆', 486, 180, 28, '#FFF');
    if (g.state === 'between' && d.shown >= 10) {
      var a = Math.min(1, (g.t - d.fullAt) / 0.6);
      c.fillStyle = '#E4572E'; Dr.rr(c, 30, 135, 392 * a, 16, 8); c.fill();
      if (a >= 1) {
        c.fillStyle = '#FFFDF6'; Dr.rr(c, 300, 236, 150, 56, 14); c.fill(); c.lineWidth = 4; c.strokeStyle = '#E4572E'; c.stroke();
        c.beginPath(); c.moveTo(375, 151); c.lineTo(375, 236); c.stroke();
        Dr.text(c, '1 个十', 375, 264, 32, '#6B4423');
      }
    }
  }

  var game = K.game({
    levels: 2,
    winPause: 2.4,
    levelName: function (l) { return l ? '两盆两盆地数' : '一盆一盆地数'; },
    winText: function () { return '10 个一就是 1 个十。下一关两盆两盆地数！'; },
    doneTitle: '花架摆满啦！',
    doneText: '一盆一盆数、两盆两盆数，都数出 10 盆。',
    bubbleAt: function (g) { return { x: BX + 40, y: g.data.by - 250 }; },
    reset: function (g, level) {
      g.data = { level: level, speed: level ? 285 : 255, scroll: 0, by: GROUND, vy: 0, onGround: true, stumble: 0,
        items: [], fly: [], count: 0, shown: 0, nextT: 0.6, since: 0, fullAt: 0 };
    },
    autopilot: function (g) {
      var d = g.data, v = d.speed, next = null;
      if (!d.onGround || d.stumble > 0) return;
      d.items.forEach(function (e) {
        if (e.done) return;
        var dx = e.x - BX;
        if (dx < -30) return;
        if (!next || dx < next.dx) next = { e: e, dx: dx };
      });
      if (!next) return;
      if (next.e.k === 'puddle' && next.dx < 74) jump(g);
      else if (next.e.k !== 'puddle' && next.e.air && Math.abs(next.dx - v * 0.37) < v * 0.035 && d.count < 10) jump(g);
    },
    update: function (g, dt) {
      var d = g.data, v = d.speed * (d.stumble > 0 ? 0.35 : 1);
      if (g.taps.length || g.keys.up) jump(g);
      d.scroll += v * dt;
      if (d.stumble > 0) d.stumble -= dt;
      if (!d.onGround) { d.vy += GRAV * dt; d.by += d.vy * dt; if (d.by >= GROUND) { d.by = GROUND; d.vy = 0; d.onGround = true; } }
      d.nextT -= dt;
      if (d.nextT <= 0 && d.count < 10) {
        var puddle = d.since >= 2 && Math.random() < 0.4;
        if (puddle) { d.items.push({ k: 'puddle', x: 1400, w: 92 }); d.since = 0; }
        else {
          var air = Math.random() < 0.5;
          d.items.push({ k: d.level ? 'pair' : 'pot', n: d.level ? 2 : 1, x: 1400, air: air, y: air ? GROUND - 215 : GROUND - 34 });
          d.since++;
        }
        d.nextT = rnd(1.05, 1.45);
      }
      var top = d.by - 150, bottom = d.by;
      d.items.forEach(function (e) {
        e.x -= v * dt;
        if (e.done) return;
        if (e.k === 'puddle') {
          if (d.by >= GROUND - 4 && BX + 30 > e.x + 12 && BX - 30 < e.x + e.w - 12) {
            e.done = true; d.stumble = 0.7; g.miss(); K.sfx.splash(); g.shake(0.5);
            g.burst(BX, GROUND, { n: 14, color: '#6EC6F0', lift: 260 });
            g.say('哎呀，水坑！点一下就能跳过去', 'no');
          }
          return;
        }
        var half = e.k === 'pair' ? 64 : 30;
        if (BX + 42 > e.x - half && BX - 42 < e.x + half && bottom > e.y - 30 && top < e.y + 30 && d.count < 10) {
          e.done = true; K.sfx.coin();
          for (var j = 0; j < e.n; j++) {
            var idx = d.count + j, to = cell(idx);
            d.fly.push({ x0: e.x + (e.n > 1 ? (j ? 34 : -34) : 0), y0: e.y, x1: to.x, y1: to.y, t: -j * 0.12, idx: idx, last: j === e.n - 1 });
          }
          d.count += e.n;
          g.sparkle(e.x, e.y);
        }
      });
      d.items = d.items.filter(function (e) { return e.x > -160; });
      d.fly.forEach(function (f) {
        f.t += dt;
        if (f.t >= 0.55 && !f.landed) {
          f.landed = true; d.shown = Math.max(d.shown, f.idx + 1); K.sfx.tick(f.idx + 1);
          if (!d.level || f.last) g.float(d.shown, f.x1, f.y1 - 34);
          if (d.shown === 5 && !d.level) g.say('一层摆满了，5 盆！再摆一层', 'ok');
          if (d.shown >= 10) { d.fullAt = g.t; g.say(d.level ? '2、4、6、8、10！' : '10 盆，满啦！', 'ok', 2.4); g.win(); }
        }
      });
      d.fly = d.fly.filter(function (f) { return !f.landed; });
    },
    draw: function (g, c) {
      if (!g.data.items) g.data = { scroll: 0, by: GROUND, onGround: true, stumble: 0, items: [], fly: [], shown: 0 };
      var d = g.data;
      drawWorld(g, c);
      d.items.forEach(function (e) {
        if (e.k === 'puddle') {
          if (e.x > 1340) return;
          c.fillStyle = '#5DB7E8'; c.beginPath(); c.ellipse(e.x + e.w / 2, GROUND + 8, e.w / 2, 13, 0, 0, Math.PI * 2); c.fill();
          c.fillStyle = 'rgba(255,255,255,.6)'; c.beginPath(); c.ellipse(e.x + e.w / 2 - 14, GROUND + 4, 16, 4, 0, 0, Math.PI * 2); c.fill();
          return;
        }
        if (e.done) return;
        var bob = e.air ? Math.sin(g.t * 4 + e.x * 0.01) * 6 : 0;
        if (e.air) {
          c.strokeStyle = 'rgba(90,70,40,.6)'; c.lineWidth = 2;
          var bl = e.k === 'pair' ? [-34, 34] : [0];
          bl.forEach(function (o) { c.beginPath(); c.moveTo(e.x + o, e.y - 28 + bob); c.lineTo(e.x + o, e.y - 78 + bob); c.stroke(); c.fillStyle = o ? '#FFB3C7' : '#FFD166'; c.beginPath(); c.ellipse(e.x + o, e.y - 100 + bob, 22, 27, 0, 0, Math.PI * 2); c.fill(); });
        }
        if (e.k === 'pair') {
          c.fillStyle = '#C98A47'; Dr.rr(c, e.x - 70, e.y + 22 + bob, 140, 12, 6); c.fill();
          pot(c, e.x - 34, e.y + bob, 64); pot(c, e.x + 34, e.y + bob, 64);
        } else pot(c, e.x, e.y + bob, 66);
      });
      drawBear(g, c);
    },
    drawTop: function (g, c) {
      var d = g.data;
      drawShelf(g, c);
      (d.fly || []).forEach(function (f) {
        if (f.t < 0) return;
        var p = Math.min(1, f.t / 0.55), e = 1 - Math.pow(1 - p, 3);
        pot(c, f.x0 + (f.x1 - f.x0) * e, f.y0 + (f.y1 - f.y0) * e - Math.sin(p * Math.PI) * 140, 66 - 8 * p);
      });
    }
  });
  game.follow('#r10a-shelf', function () { return { x: 22, y: 18, w: 540, h: 206 }; });
  game.follow('#r10a-count', function () { return { x: 428, y: 40, w: 116, h: 166 }; });
  game.follow('#r10a-bear', function (g) { var d = g.data; return { x: BX - 70, y: (d.by || GROUND) - 215, w: 140, h: 220 }; });
  K.ready({ emoji: '🌱', title: '小熊跑酷收幼苗', sub: '点一下或按空格，小熊就跳起来' });
})();
