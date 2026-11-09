(function () {
  // 小赛车描 10：田字格里铺着“1”和“0”形状的跑道。按住小车沿跑道往前开，车轮压过的地方就写出了数字。
  // 第1关写 1（从上往下），第2关写 0（从上面出发往左绕一圈），第3关在同一格里写 10：1 在左，0 在右。
  var Dr = K.draw;
  var GX = 410, GY = 190, GS = 460;
  var LEVELS = [
    { name: '写 1：从上往下开', strokes: ['one'] },
    { name: '写 0：从上面出发，往左绕一圈', strokes: ['zero'] },
    { name: '写 10：1 在左，0 在右', strokes: ['one', 'zero'] }
  ];
  function gp(u, v) { return { x: GX + u * GS, y: GY + v * GS }; }
  function build(kind) {
    var pts = [], i;
    if (kind === 'one') { for (i = 0; i <= 60; i++) { var t = i / 60; pts.push(gp(0.319 + (0.171 - 0.319) * t, 0.171 + (0.814 - 0.171) * t)); } }
    else {
      var cx = 0.733, cy = 0.495, rx = 0.126, ry = 0.357, ph = 0.28;
      for (i = 0; i <= 160; i++) {
        var th = -Math.PI / 2 - (i / 160) * Math.PI * 2, x = rx * Math.cos(th), y = ry * Math.sin(th);
        pts.push(gp(cx + x * Math.cos(ph) - y * Math.sin(ph), cy + x * Math.sin(ph) + y * Math.cos(ph)));
      }
    }
    var len = [0];
    for (i = 1; i < pts.length; i++) len.push(len[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y));
    return { kind: kind, pts: pts, len: len, total: len[len.length - 1] };
  }
  var PATHS = { one: build('one'), zero: build('zero') };
  function at(p, s) {
    s = Math.max(0, Math.min(p.total, s));
    for (var i = 1; i < p.pts.length; i++) {
      if (p.len[i] >= s) {
        var a = p.pts[i - 1], b = p.pts[i], f = (s - p.len[i - 1]) / Math.max(1e-6, p.len[i] - p.len[i - 1]);
        return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, ang: Math.atan2(b.y - a.y, b.x - a.x) };
      }
    }
    var n = p.pts.length; return { x: p.pts[n - 1].x, y: p.pts[n - 1].y, ang: Math.atan2(p.pts[n - 1].y - p.pts[n - 2].y, p.pts[n - 1].x - p.pts[n - 2].x) };
  }
  function road(c, p, upto, width, color, dash) {
    c.save(); c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = color; c.lineWidth = width; if (dash) c.setLineDash(dash);
    c.beginPath(); c.moveTo(p.pts[0].x, p.pts[0].y);
    for (var i = 1; i < p.pts.length && p.len[i] <= upto; i++) c.lineTo(p.pts[i].x, p.pts[i].y);
    if (upto < p.total) { var e = at(p, upto); c.lineTo(e.x, e.y); }
    c.stroke(); c.restore();
  }
  function car(c, x, y, ang, t) {
    c.save(); c.translate(x, y); c.rotate(ang);
    c.fillStyle = 'rgba(0,0,0,.2)'; c.beginPath(); c.ellipse(2, 6, 34, 20, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#2B2B2B'; Dr.rr(c, -26, -24, 16, 10, 4); c.fill(); Dr.rr(c, 12, -24, 16, 10, 4); c.fill(); Dr.rr(c, -26, 14, 16, 10, 4); c.fill(); Dr.rr(c, 12, 14, 16, 10, 4); c.fill();
    c.fillStyle = '#E4572E'; Dr.rr(c, -32, -17, 66, 34, 14); c.fill();
    c.fillStyle = '#FFFFFF'; c.fillRect(-32, -4, 66, 8);
    c.fillStyle = '#BFE7FB'; Dr.rr(c, 2, -12, 18, 24, 6); c.fill();
    c.fillStyle = '#FFD166'; Dr.circle(c, 32, -10, 4); Dr.circle(c, 32, 10, 4);
    c.restore();
  }
  function flag(c, x, y, finish) {
    c.fillStyle = '#6B4423'; c.fillRect(x - 3, y - 70, 6, 72);
    if (finish) { for (var r = 0; r < 3; r++) for (var q = 0; q < 4; q++) { c.fillStyle = (r + q) % 2 ? '#222' : '#FFF'; c.fillRect(x + 3 + q * 11, y - 70 + r * 11, 11, 11); } }
    else { c.fillStyle = '#58B45C'; c.beginPath(); c.moveTo(x + 3, y - 70); c.lineTo(x + 48, y - 56); c.lineTo(x + 3, y - 42); c.closePath(); c.fill(); }
  }

  var game = K.game({
    levels: 3,
    winPause: 2.4,
    levelName: function (l) { return LEVELS[l].name; },
    winText: function (l) { return l === 0 ? '1 写在左半格，从上往下。下一关写 0！' : '0 从上面出发，往左绕一圈，回到起点。下一关写 10！'; },
    doneTitle: '10 写好啦！',
    doneText: '1 在左，0 在右，挨在同一个田字格里。',
    bubbleAt: function () { return { x: 640, y: 140 }; },
    reset: function (g, level) {
      g.data = { level: level, list: LEVELS[level].strokes.slice(), k: 0, s: 0, done: [], grab: false, off: 0, warnAt: -9, roadT: 0 };
    },
    autopilot: function (g) { var d = g.data; if (d.k < d.list.length) d.s = Math.min(PATHS[d.list[d.k]].total, d.s + 170 * g.dt); },
    update: function (g, dt) {
      var d = g.data;
      if (d.k >= d.list.length) return;
      var p = PATHS[d.list[d.k]], here = at(p, d.s);
      if (!g.auto) {
        if (g.pointer.down) {
          var dist = Math.hypot(g.pointer.x - here.x, g.pointer.y - here.y);
          if (!d.grab && dist < 95) d.grab = true;
          if (d.grab) {
            var best = -1, bd = 1e9;
            for (var i = 0; i < p.pts.length; i++) {
              if (p.len[i] < d.s - 2 || p.len[i] > d.s + 70) continue;
              var dd = Math.hypot(g.pointer.x - p.pts[i].x, g.pointer.y - p.pts[i].y);
              if (dd < bd) { bd = dd; best = i; }
            }
            if (best >= 0 && bd < 72) { if (p.len[best] > d.s) d.s = p.len[best]; }
            else if (dist > 110 && g.t - d.warnAt > 1.6) {
              d.warnAt = g.t; g.miss(); K.sfx.no(); g.shake(0.3);
              var back = d.s < 30 && p.kind === 'zero' && g.pointer.x > here.x;
              g.say(back ? '方向反了：从上面往左边开' : '开出跑道啦，按住小车慢慢开', 'no');
              d.grab = false;
            }
          }
        } else d.grab = false;
        if (g.keys.right || g.keys.down || g.keys.jump) d.s = Math.min(p.total, d.s + 200 * dt);
      }
      d.roadT += dt;
      if (Math.floor(d.roadT * 8) !== Math.floor((d.roadT - dt) * 8) && d.s > 0 && d.s < p.total && (g.pointer.down || g.auto)) K.sfx.tick(1 + Math.floor(d.s / p.total * 8));
      if (d.s >= p.total - 0.5) {
        d.done.push(d.list[d.k]); d.k++; d.s = 0; d.grab = false; K.sfx.coin(); g.sparkle(here.x, here.y);
        if (d.k >= d.list.length) { g.say(d.list.length > 1 ? '10 写好了！' : (p.kind === 'one' ? '1 写好了！' : '0 写好了！'), 'ok', 2.2); g.win(); }
        else g.say('1 写好了，再写 0：从上面出发往左绕', 'ok', 2.6);
      }
    },
    draw: function (g, c) {
      var d = g.data && g.data.list ? g.data : { list: ['one'], k: 0, s: 0, done: [], level: 0 };
      var bg = c.createLinearGradient(0, 0, 0, 720); bg.addColorStop(0, '#FFF7E3'); bg.addColorStop(1, '#FBE3B8');
      c.fillStyle = bg; c.fillRect(0, 0, 1280, 720);
      for (var i = 0; i < 9; i++) { c.fillStyle = i % 2 ? 'rgba(88,180,92,.10)' : 'rgba(246,169,53,.10)'; Dr.circle(c, 100 + i * 140, 120 + (i % 3) * 230, 60 + (i % 4) * 14); }
      c.fillStyle = '#FFFDF6'; Dr.rr(c, GX - 14, GY - 14, GS + 28, GS + 28, 26); c.fill();
      c.lineWidth = 6; c.strokeStyle = '#7A9A84'; Dr.rr(c, GX, GY, GS, GS, 18); c.stroke();
      c.save(); c.strokeStyle = 'rgba(122,154,132,.6)'; c.lineWidth = 3; c.setLineDash([14, 12]);
      c.beginPath(); c.moveTo(GX + GS / 2, GY); c.lineTo(GX + GS / 2, GY + GS); c.moveTo(GX, GY + GS / 2); c.lineTo(GX + GS, GY + GS / 2); c.stroke(); c.restore();
      ['one', 'zero'].forEach(function (kind) {
        var p = PATHS[kind], inPlan = d.list.indexOf(kind) >= 0, isDone = d.done.indexOf(kind) >= 0, active = d.list[d.k] === kind;
        if (!inPlan) { road(c, p, p.total, 10, 'rgba(122,154,132,.25)'); return; }
        road(c, p, p.total, 60, active ? '#8C8C8C' : '#B5B5B5');
        road(c, p, p.total, 4, 'rgba(255,255,255,.85)', [14, 14]);
        if (isDone) road(c, p, p.total, 20, '#2F6B4F');
        else if (active) {
          road(c, p, d.s, 20, '#2F6B4F');
          var st = p.pts[0], en = p.pts[p.pts.length - 1];
          flag(c, st.x + 34, st.y - 4, false);
          if (kind === 'one') flag(c, en.x - 30, en.y + 64, true);
          if (kind === 'zero') {
            c.save(); c.strokeStyle = 'rgba(228,87,46,.85)'; c.lineWidth = 6; c.lineCap = 'round';
            var a1 = at(p, 18), a2 = at(p, 62);
            c.beginPath(); c.moveTo(a1.x - 46, a1.y + 4); c.quadraticCurveTo(a1.x - 70, (a1.y + a2.y) / 2, a2.x - 52, a2.y + 10); c.stroke();
            c.beginPath(); c.moveTo(a2.x - 52, a2.y + 10); c.lineTo(a2.x - 66, a2.y - 6); c.moveTo(a2.x - 52, a2.y + 10); c.lineTo(a2.x - 36, a2.y - 2); c.stroke(); c.restore();
          }
        }
      });
      if (d.k < d.list.length) { var p = PATHS[d.list[d.k]], h = at(p, d.s); car(c, h.x, h.y, h.ang, g.t); }
      Dr.text(c, '1 在左半格', GX - 150, GY + 120, 30, d.list.indexOf('one') >= 0 ? '#6B4423' : 'rgba(107,68,35,.35)');
      Dr.text(c, '0 在右半格', GX + GS + 150, GY + 120, 30, d.list.indexOf('zero') >= 0 ? '#6B4423' : 'rgba(107,68,35,.35)');
    }
  });
  game.follow('#r10f-grid', function () { return { x: GX, y: GY, w: GS, h: GS }; });
  game.follow('#r10f-car', function (g) { var d = g.data; if (!d.list || d.k >= d.list.length) return { x: GX, y: GY, w: 1, h: 1 }; var h = at(PATHS[d.list[d.k]], d.s); return { x: h.x - 50, y: h.y - 50, w: 100, h: 100 }; });
  game.follow('#r10f-start', function (g) { var d = g.data; var kind = d.list && d.k < d.list.length ? d.list[d.k] : 'one'; var s = PATHS[kind].pts[0]; return { x: s.x - 45, y: s.y - 45, w: 90, h: 90 }; });
  K.ready({ emoji: '🏎️', title: '小赛车描 10', sub: '按住小车，沿着跑道开，就把数字写出来了' });
})();
