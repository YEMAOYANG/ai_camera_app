(function () {
  // 碰碰车找朋友：开着自己的碰碰车，去碰车顶上的数和自己的数合起来正好是 10 的那辆车。
  // 老师只演示 3。孩子第一关用 1、2、4，第二关用 6～9，第三关用 0、10 和 5。
  var Dr = K.draw;
  var AX0 = 40, AY0 = 214, AX1 = 1240, AY1 = 690, R = 54, VMAX = 470;
  var COLS = ['#FF6B6B', '#FFC531', '#51CF66', '#CC5DE8', '#FF922B', '#20C997'];
  var PLAN = [[1, 2, 4], [6, 7, 8, 9], [0, 10, 5]], CARS = [4, 5, 6];
  var SPEED = [[70, 110], [110, 150], [140, 185]];
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function shuffle(a) { a = a.slice(); for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)), t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
  function clampX(x) { return Math.max(AX0 + R, Math.min(AX1 - R, x)); }
  function clampY(y) { return Math.max(AY0 + R, Math.min(AY1 - R, y)); }
  function place(spots) {
    for (var t = 0; t < 60; t++) {
      var x = rnd(AX0 + R + 10, AX1 - R - 10), y = rnd(AY0 + R + 10, AY1 - R - 10);
      if (spots.every(function (o) { return Math.hypot(o.x - x, o.y - y) > 2 * R + 70; })) return { x: x, y: y };
    }
    return { x: rnd(AX0 + R, AX1 - R), y: rnd(AY0 + R, AY1 - R) };
  }
  function startRound(g) {
    var d = g.data, n = d.order[d.round], m = 10 - n;
    d.n = n; d.m = m; d.roundMiss = 0; d.hint = 0; d.glow = false; d.win = null;
    var pool = [];
    for (var k = 0; k <= 10; k++) if (k !== m) pool.push(k);
    var pick = shuffle(pool.filter(function (k) { return Math.abs(k - m) <= 2; })).concat(shuffle(pool.filter(function (k) { return Math.abs(k - m) > 2; })));
    var nums = [m].concat(pick.slice(0, CARS[d.level] - 1));
    d.me = { x: 640, y: 470, vx: 0, vy: 0, h: -Math.PI / 2 };
    d.tx = 640; d.ty = 470;
    var spots = [d.me];
    d.cars = shuffle(nums).map(function (v, i) {
      var p = place(spots); spots.push(p);
      var a = rnd(0, Math.PI * 2), s = rnd(SPEED[d.level][0], SPEED[d.level][1]);
      return { x: p.x, y: p.y, vx: Math.cos(a) * s, vy: Math.sin(a) * s, h: a, v: v, col: COLS[i % COLS.length], cool: 0, wob: rnd(0, 6), spin: 0 };
    });
    g.banner('我的车是 ' + n, '去碰能和 ' + n + ' 凑成 10 的车', 2);
  }
  function partner(d) { for (var i = 0; i < d.cars.length; i++) if (d.cars[i].v === d.m) return d.cars[i]; return null; }

  function drawCar(c, x, y, h, col, num, glow, t, spin) {
    c.save(); c.translate(x, y);
    c.fillStyle = 'rgba(40,40,60,.22)'; c.beginPath(); c.ellipse(4, 10, 62, 50, 0, 0, Math.PI * 2); c.fill();
    if (glow) { c.fillStyle = 'rgba(255,214,90,' + (0.35 + 0.25 * Math.sin(t * 8)) + ')'; Dr.circle(c, 0, 0, 86); }
    c.save(); c.rotate(h + Math.PI / 2 + spin);
    c.fillStyle = '#3B3B48'; Dr.rr(c, -50, -60, 100, 120, 34); c.fill();
    c.fillStyle = col; Dr.rr(c, -42, -52, 84, 104, 28); c.fill();
    c.fillStyle = 'rgba(255,255,255,.35)'; Dr.rr(c, -32, -44, 64, 22, 10); c.fill();
    c.fillStyle = '#2E3A59'; Dr.rr(c, -26, 8, 52, 30, 10); c.fill();
    c.strokeStyle = '#555'; c.lineWidth = 4; c.beginPath(); c.moveTo(0, 26); c.lineTo(0, 62); c.stroke();
    c.fillStyle = '#FF5A5A'; Dr.circle(c, 0, 64, 7);
    c.restore();
    c.fillStyle = '#FFFDF6'; Dr.circle(c, 0, -6, 31); c.lineWidth = 4; c.strokeStyle = '#4A2F1B'; c.beginPath(); c.arc(0, -6, 31, 0, Math.PI * 2); c.stroke();
    Dr.text(c, String(num), 0, -5, num >= 10 ? 34 : 42, '#4A2F1B', { weight: 900 });
    c.restore();
  }
  function cell(i) { return { x: 196 + (i % 5) * 62, y: 92 + Math.floor(i / 5) * 62 }; }

  var game = K.game({
    levels: 3,
    finishMark: '★★★',
    starsFor: function () { return 3; },
    winPause: 2,
    levelName: function (l) { return ['看十格，找好朋友', '大数找小数', '还有 0、10 和 5'][l]; },
    winText: function (l) { return ['两个数合起来是 10，就是好朋友！', '换一换位置，合起来还是 10！', '0 和 10 是好朋友，5 和 5 也是！'][l]; },
    doneTitle: '都找到好朋友啦！',
    doneText: '两个数合起来是 10，它们就是好朋友；换一换位置，合起来还是 10。',
    bubbleAt: function (g) { var me = g.data && g.data.me; return me ? { x: me.x, y: Math.max(80, me.y - 120) } : { x: 640, y: 160 }; },
    reset: function (g, level) {
      var order = g.autoLoop ? [3] : shuffle(PLAN[level]);
      g.data = { level: level, round: 0, rounds: order.length, order: order, cars: [], me: null };
      startRound(g);
    },
    autopilot: function (g) {
      var d = g.data, me = d.me, p = partner(d);
      if (!me || !p || d.win) return;
      var gx = p.x + p.vx * 0.25 - me.x, gy = p.y + p.vy * 0.25 - me.y, dist = Math.hypot(gx, gy) || 1;
      var ux = gx / dist, uy = gy / dist;
      d.cars.forEach(function (o) {
        if (o === p) return;
        var ox = o.x - me.x, oy = o.y - me.y, od = Math.hypot(ox, oy) || 1;
        if (od < 230) { var push = (230 - od) / 230 * 2.2; ux -= ox / od * push; uy -= oy / od * push; }
      });
      var ul = Math.hypot(ux, uy) || 1;
      d.tx = clampX(me.x + ux / ul * 160); d.ty = clampY(me.y + uy / ul * 160);
    },
    update: function (g, dt) {
      var d = g.data, me = d.me;
      d.cars.forEach(function (o) {
        o.cool = Math.max(0, o.cool - dt); o.spin *= Math.exp(-dt * 3);
        var a = Math.atan2(o.vy, o.vx) + Math.sin(g.t * 0.9 + o.wob) * 0.5 * dt, s = Math.hypot(o.vx, o.vy);
        var want = rnd(SPEED[d.level][0], SPEED[d.level][1]); s += (want - s) * dt * 0.6;
        o.vx = Math.cos(a) * s; o.vy = Math.sin(a) * s; o.x += o.vx * dt; o.y += o.vy * dt;
        if (o.x < AX0 + R) { o.x = AX0 + R; o.vx = Math.abs(o.vx); } if (o.x > AX1 - R) { o.x = AX1 - R; o.vx = -Math.abs(o.vx); }
        if (o.y < AY0 + R) { o.y = AY0 + R; o.vy = Math.abs(o.vy); } if (o.y > AY1 - R) { o.y = AY1 - R; o.vy = -Math.abs(o.vy); }
        o.h = Math.atan2(o.vy, o.vx);
      });
      for (var i = 0; i < d.cars.length; i++) for (var j = i + 1; j < d.cars.length; j++) {
        var a1 = d.cars[i], b1 = d.cars[j], dx = b1.x - a1.x, dy = b1.y - a1.y, dd = Math.hypot(dx, dy) || 1;
        if (dd < 2 * R) { var nx = dx / dd, ny = dy / dd, ov = (2 * R - dd) / 2; a1.x -= nx * ov; a1.y -= ny * ov; b1.x += nx * ov; b1.y += ny * ov;
          var t1 = a1.vx, t2 = a1.vy; a1.vx = b1.vx; a1.vy = b1.vy; b1.vx = t1; b1.vy = t2; }
      }
      if (d.win) {
        d.win.t += dt; d.win.car.spin += dt * 9; me.vx *= 0.9; me.vy *= 0.9;
        if (d.win.t > 2.7) { d.round++; if (d.round >= d.rounds) { d.win = null; g.win(); return; } startRound(g); }
        return;
      }
      if (!g.auto && g.pointer.active) { d.tx = clampX(g.pointer.x); d.ty = clampY(g.pointer.y); }
      if (g.keys.left) d.tx = clampX(me.x - 160); if (g.keys.right) d.tx = clampX(me.x + 160);
      if (g.keys.up) d.ty = clampY(me.y - 160); if (g.keys.down) d.ty = clampY(me.y + 160);
      var wx = (d.tx - me.x) * 4, wy = (d.ty - me.y) * 4, wl = Math.hypot(wx, wy);
      if (wl > VMAX) { wx = wx / wl * VMAX; wy = wy / wl * VMAX; }
      var k = Math.min(1, dt * 6); me.vx += (wx - me.vx) * k; me.vy += (wy - me.vy) * k;
      me.x = clampX(me.x + me.vx * dt); me.y = clampY(me.y + me.vy * dt);
      if (Math.hypot(me.vx, me.vy) > 25) me.h = Math.atan2(me.vy, me.vx);
      if (d.hint > 0) d.hint -= dt;
      for (var q = 0; q < d.cars.length; q++) {
        var o = d.cars[q], ox = o.x - me.x, oy = o.y - me.y, od = Math.hypot(ox, oy) || 1;
        if (od >= 2 * R) continue;
        var nx2 = ox / od, ny2 = oy / od;
        if (o.v === d.m) {
          d.win = { t: 0, car: o }; K.sfx.coin(); g.confetti(40); g.sparkle(o.x, o.y); K.log.push('pair:' + d.n + '+' + d.m);
          o.vx = nx2 * 60; o.vy = ny2 * 60; return;
        }
        o.x = me.x + nx2 * 2 * R; o.y = me.y + ny2 * 2 * R;
        var sp = Math.max(160, Math.hypot(o.vx, o.vy)); o.vx = nx2 * sp; o.vy = ny2 * sp; o.spin = 1.4;
        me.vx = -nx2 * 300; me.vy = -ny2 * 300;
        if (o.cool > 0) continue;
        o.cool = 1.2; g.miss(); d.roundMiss++; K.sfx.no(); g.shake(0.5); g.burst((o.x + me.x) / 2, (o.y + me.y) / 2, { n: 8, color: '#FFFFFF' });
        if (d.roundMiss === 1) g.say(d.n + ' 和 ' + o.v + ' 合起来不是 10', 'no');
        else if (d.roundMiss === 2) { d.hint = 4; g.say('看十格：还空着几格？', 'no'); }
        else { d.hint = 4; d.glow = true; g.say('去碰发光的那辆车', 'no'); }
      }
    },
    draw: function (g, c) {
      var d = g.data && g.data.cars ? g.data : { cars: [], me: null };
      c.fillStyle = '#FFF4DC'; c.fillRect(0, 0, 1280, 720);
      c.fillStyle = '#DCE7F2'; Dr.rr(c, AX0 - 14, AY0 - 14, AX1 - AX0 + 28, AY1 - AY0 + 28, 34); c.fill();
      c.save(); Dr.rr(c, AX0, AY0, AX1 - AX0, AY1 - AY0, 24); c.clip();
      for (var gx = AX0; gx < AX1; gx += 80) for (var gy = AY0; gy < AY1; gy += 80) { c.fillStyle = ((gx + gy) / 80) % 2 ? '#EEF3F8' : '#E3EBF4'; c.fillRect(gx, gy, 80, 80); }
      c.restore();
      c.lineWidth = 10; c.setLineDash([26, 18]); c.strokeStyle = '#FF6B6B'; Dr.rr(c, AX0 - 5, AY0 - 5, AX1 - AX0 + 10, AY1 - AY0 + 10, 28); c.stroke(); c.setLineDash([]);
      var p = d.m != null ? partner(d) : null;
      d.cars.forEach(function (o) { drawCar(c, o.x, o.y, o.h, o.col, o.v, d.glow && o === p, g.t, o.spin); });
      if (d.me) drawCar(c, d.me.x, d.me.y, d.me.h, '#4C8DDB', d.n, false, g.t, 0);
      if (d.me && g.state === 'play' && !d.win) { c.fillStyle = 'rgba(76,141,219,.18)'; Dr.circle(c, d.tx, d.ty, 16); }
    },
    drawTop: function (g, c) {
      var d = g.data && g.data.cars ? g.data : null;
      c.fillStyle = 'rgba(255,253,246,.96)'; Dr.rr(c, 22, 14, 500, 184, 24); c.fill(); c.lineWidth = 4; c.strokeStyle = '#4C8DDB'; c.stroke();
      Dr.text(c, '我的车', 92, 52, 30, '#2F66AE'); Dr.text(c, d ? String(d.n) : '', 92, 120, 78, '#2F66AE', { weight: 900 });
      for (var i = 0; i < 10; i++) {
        var q = cell(i), lit = d && i < d.n;
        c.fillStyle = lit ? '#4C8DDB' : '#F1E7D2'; Dr.rr(c, q.x - 26, q.y - 26, 52, 52, 12); c.fill();
        if (lit) { c.fillStyle = '#FFE680'; Dr.circle(c, q.x, q.y, 14); }
        else if (d && d.hint > 0) { c.fillStyle = 'rgba(255,138,42,' + (0.25 + 0.2 * Math.sin(g.t * 8)) + ')'; Dr.rr(c, q.x - 26, q.y - 26, 52, 52, 12); c.fill(); Dr.text(c, String(i - d.n + 1), q.x, q.y + 1, 30, '#C47A12', { weight: 900 }); }
      }
      if (d) {
        var eq = d.win ? d.n + ' + ' + d.m + ' = 10' : d.n + ' + ? = 10';
        Dr.text(c, eq, 344, 178, 30, d.win ? '#2F8A3A' : '#6B4423', { weight: 900 });
        for (var r = 0; r < d.rounds; r++) { c.fillStyle = r < d.round ? '#58B45C' : r === d.round ? '#FF8A2A' : 'rgba(255,253,246,.92)'; Dr.circle(c, 760 + (r - (d.rounds - 1) / 2) * 38, 44, 13); }
      }
      if (d && d.win) {
        var w = d.win, s = 0.6 + 0.4 * Math.min(1, w.t / 0.35);
        c.save(); c.translate(820, 120); c.scale(s, s);
        c.fillStyle = '#FF8A2A'; Dr.rr(c, -300, -74, 600, 148, 34); c.fill();
        Dr.text(c, d.n + ' + ' + d.m + ' = 10', 0, -24, 58, '#FFF', { weight: 900 });
        Dr.text(c, d.n === d.m ? '两个数一样多，合起来是 10' : '换一换：' + d.m + ' + ' + d.n + ' = 10', 0, 40, 34, '#FFF3E0');
        c.restore();
      }
    }
  });
  game.follow('#as10a-panel', function () { return { x: 22, y: 14, w: 500, h: 184 }; });
  game.follow('#as10a-me', function (g) { var me = g.data && g.data.me; return me ? { x: me.x - 70, y: me.y - 70, w: 140, h: 140 } : { x: 570, y: 400, w: 140, h: 140 }; });
  game.follow('#as10a-arena', function () { return { x: AX0, y: AY0, w: AX1 - AX0, h: AY1 - AY0 }; });
  K.ready({ emoji: '灯牌工坊', title: '碰碰车找朋友', sub: '开着你的车，去碰能和你的数凑成 10 的那辆车' });
})();
