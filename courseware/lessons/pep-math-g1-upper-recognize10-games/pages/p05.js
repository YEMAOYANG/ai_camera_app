(function () {
  // 套圈比多少。第1关：十只小鸭在池塘里游，点哪里就把游泳圈扔到哪里，九个圈一只鸭套一个，
  // 最后多出一只鸭子：10 比 9 多 1。第2关：符号方块往下掉，点一下把开口翻向大的数，落下读出 10 > 9 或 9 < 10。
  var Dr = K.draw;
  var DUCK_Y = 400, THROW = { x: 640, y: 680 }, FLY = 0.55;
  var ROUNDS = [[10, 9], [9, 10], [10, 9], [9, 10]];

  function ring(c, x, y, s) {
    c.save(); c.translate(x, y); c.scale(s, s);
    c.lineWidth = 13; c.strokeStyle = '#FFFFFF'; c.beginPath(); c.ellipse(0, 0, 40, 15, 0, 0, Math.PI * 2); c.stroke();
    c.strokeStyle = '#F25C54'; c.setLineDash([16, 16]); c.beginPath(); c.ellipse(0, 0, 40, 15, 0, 0, Math.PI * 2); c.stroke(); c.setLineDash([]);
    c.restore();
  }
  function duck(c, x, y, t, ringed, glow, face) {
    c.save(); c.translate(x, y + Math.sin(t * 3 + x * 0.02) * 3); c.scale(face, 1);
    if (glow) { c.fillStyle = 'rgba(255,209,102,' + (0.35 + 0.25 * Math.sin(t * 8)) + ')'; Dr.circle(c, 0, -20, 64); }
    c.fillStyle = 'rgba(30,90,120,.25)'; c.beginPath(); c.ellipse(0, 22, 46, 10, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#FFD43B'; c.beginPath(); c.ellipse(0, 4, 42, 26, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.moveTo(-40, -4); c.lineTo(-56, -18); c.lineTo(-36, 10); c.closePath(); c.fill();
    c.fillStyle = '#FFC61A'; c.beginPath(); c.ellipse(-6, 4, 20, 12, -0.3, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#FFD43B'; Dr.circle(c, 22, -30, 22);
    c.fillStyle = '#FF8A2A'; c.beginPath(); c.ellipse(46, -26, 13, 6, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#1F1A10'; Dr.circle(c, 28, -36, 4.5); c.fillStyle = '#FFF'; Dr.circle(c, 29.5, -37.5, 1.6);
    c.restore();
    if (ringed) ring(c, x + 6 * face, y - 14, 0.9);
  }
  function sign(c, x, y, dir, s) {
    // dir 1: opening faces left (>), dir -1: opening faces right (<)
    c.save(); c.translate(x, y); c.scale(s, s);
    c.fillStyle = '#58B45C'; Dr.rr(c, -62, -62, 124, 124, 26); c.fill();
    c.lineWidth = 5; c.strokeStyle = '#2F8A3A'; c.stroke();
    c.strokeStyle = '#FFFFFF'; c.lineWidth = 16; c.lineCap = 'round'; c.lineJoin = 'round';
    c.beginPath(); c.moveTo(-28 * dir, -36); c.lineTo(30 * dir, 0); c.lineTo(-28 * dir, 36); c.stroke();
    c.restore();
  }
  function card(c, x, y, n, glow, t) {
    if (glow) { c.fillStyle = 'rgba(255,209,102,' + (0.45 + 0.35 * Math.sin(t * 8)) + ')'; Dr.rr(c, x - 108, y - 108, 216, 216, 36); c.fill(); }
    c.fillStyle = '#FFFDF6'; Dr.rr(c, x - 92, y - 92, 184, 184, 28); c.fill(); c.lineWidth = 5; c.strokeStyle = '#E8C48F'; c.stroke();
    Dr.text(c, String(n), x, y + 4, 120, '#6B4423', { weight: 900 });
    for (var i = 0; i < n; i++) { c.fillStyle = '#E4572E'; Dr.circle(c, x - 76 + (i % 5) * 38, y + 130 + Math.floor(i / 5) * 34, 12); }
  }

  function startDucks(d) {
    d.ducks = []; for (var i = 0; i < 10; i++) d.ducks.push({ off: i * 104, ringed: false });
    d.rowX = 120; d.vx = 95; d.left = 9; d.flying = []; d.matched = 0; d.showT = -1;
  }
  function duckX(d, i) { return d.rowX + d.ducks[i].off; }
  function startRound(g) {
    var d = g.data, r = ROUNDS[d.round];
    d.pair = r; d.dir = Math.random() < 0.5 ? 1 : -1; d.sy = 60; d.vy = 120 + d.round * 28; d.roundMiss = 0; d.landed = -1; d.glow = false;
  }

  var game = K.game({
    levels: 2,
    winPause: 2.6,
    levelName: function (l) { return l ? '翻符号：开口朝大数' : '套圈：一只鸭子一个圈'; },
    winText: function () { return '鸭子 10 只，圈 9 个：10 比 9 多 1。下一关翻符号！'; },
    doneTitle: '比大小真棒！',
    doneText: '10 比 9 多 1，10 > 9，9 < 10。',
    bubbleAt: function (g) { return g.data.level ? { x: 640, y: 120 } : { x: 640, y: 250 }; },
    reset: function (g, level) {
      var d = g.data = { level: level, round: 0 };
      if (level === 0) startDucks(d); else startRound(g);
    },
    autopilot: function (g) {
      var d = g.data;
      if (d.level === 0) {
        if (d.left <= 0 || d.flying.length || d.showT >= 0) return;
        if (!d.cool || g.t > d.cool) {
          var best = null;
          d.ducks.forEach(function (dk, i) {
            if (dk.ringed || d.flying.some(function (f) { return f.target === i; })) return;
            var fx = duckX(d, i) + d.vx * FLY;
            if (fx < 120 || fx > 1160) return;
            if (!best || Math.abs(fx - 640) < Math.abs(best.x - 640)) best = { x: fx, i: i };
          });
          if (best) { g.taps.push({ x: best.x, y: DUCK_Y, auto: true }); d.cool = g.t + 0.25; }
        }
      } else if (d.landed < 0) {
        var want = d.pair[0] > d.pair[1] ? 1 : -1;
        if (d.dir !== want && d.sy > 120) g.taps.push({ x: 640, y: 300, auto: true });
      }
    },
    update: function (g, dt) {
      var d = g.data;
      if (d.level === 0) {
        if (d.showT >= 0) {
          d.showT += dt;
          if (d.showT > 0.4 && d.matched < 9) { d.matchT = (d.matchT || 0) + dt; if (d.matchT > 0.22) { d.matchT = 0; d.matched++; K.sfx.tick(d.matched); } }
          if (d.matched >= 9 && !d.said) { d.said = true; g.say('多出 1 只鸭子：10 比 9 多 1', 'ok', 3); g.after(1.4, function () { g.win(); }); }
          return;
        }
        d.rowX += d.vx * dt;
        if (d.rowX + 9 * 104 > 1180 && d.vx > 0) d.vx = -Math.abs(d.vx);
        if (d.rowX < 100 && d.vx < 0) d.vx = Math.abs(d.vx);
        g.taps.forEach(function (t) {
          if (d.left - d.flying.length <= 0) return;
          var target = -1;
          d.flying.push({ x0: THROW.x, y0: THROW.y, x1: Math.max(90, Math.min(1190, t.x)), y1: DUCK_Y - 14, t: 0, target: target });
          K.sfx.whoosh();
        });
        d.flying.forEach(function (f) {
          f.t += dt;
          if (f.t >= FLY && !f.done) {
            f.done = true;
            var hit = -1, best = 999;
            d.ducks.forEach(function (dk, i) { var dx = Math.abs(duckX(d, i) - f.x1); if (!dk.ringed && dx < 50 && dx < best) { best = dx; hit = i; } });
            if (hit >= 0) {
              d.ducks[hit].ringed = true; d.left--; K.sfx.coin(); g.sparkle(duckX(d, hit), DUCK_Y - 20);
              g.float(9 - d.left, duckX(d, hit), DUCK_Y - 110, { size: 48 });
              if (d.left === 0) { d.showT = 0; d.vx = 0; K.sfx.ok(); }
            } else {
              g.miss(); K.sfx.splash(); g.burst(f.x1, DUCK_Y + 10, { n: 10, color: '#7CCBF2', lift: 200 });
              if (g.levelMisses === 1) g.say('没套上，圈飘回来了。看准鸭子再扔', 'no');
            }
          }
        });
        d.flying = d.flying.filter(function (f) { return !f.done; });
        return;
      }
      if (d.landed >= 0) { d.landed += dt; return; }
      if (g.taps.length) { d.dir = -d.dir; K.sfx.pick(); }
      d.sy += d.vy * dt;
      if (d.sy >= 330) {
        d.sy = 330;
        var want = d.pair[0] > d.pair[1] ? 1 : -1;
        if (d.dir === want) {
          d.landed = 0; K.sfx.ok(); g.burst(640, 330, { n: 14 });
          var big = Math.max(d.pair[0], d.pair[1]), small = Math.min(d.pair[0], d.pair[1]);
          g.say(d.pair[0] > d.pair[1] ? big + ' 大于 ' + small : small + ' 小于 ' + big, 'ok', 2.2);
          g.after(2.2, function () { d.round++; if (d.round >= ROUNDS.length) g.win(); else startRound(g); });
        } else {
          g.miss(); d.roundMiss++; K.sfx.no(); g.shake(0.4);
          d.sy = 60; d.vy = Math.max(90, d.vy * 0.8);
          if (d.roundMiss === 1) g.say('开口要对着大的数', 'no');
          else { d.glow = true; g.say('看哪边的点多', 'no'); }
        }
      }
    },
    draw: function (g, c) {
      var d = g.data || {};
      var w = c.createLinearGradient(0, 0, 0, 720); w.addColorStop(0, '#BFE8FB'); w.addColorStop(0.42, '#E8F7FF'); w.addColorStop(0.43, '#7CC7EA'); w.addColorStop(1, '#3E95C8');
      c.fillStyle = w; c.fillRect(0, 0, 1280, 720);
      c.fillStyle = '#9ED69A'; c.beginPath(); c.moveTo(0, 310); for (var x = 0; x <= 1280; x += 40) c.lineTo(x, 290 - 18 * Math.sin(x * 0.01)); c.lineTo(1280, 312); c.lineTo(0, 312); c.closePath(); c.fill();
      c.strokeStyle = 'rgba(255,255,255,.35)'; c.lineWidth = 3;
      for (var r = 0; r < 9; r++) { var ry = 360 + r * 40, off = ((r * 97 + g.t * 25) % 260 + 260) % 260; for (var k = -1; k < 6; k++) { var rx = k * 260 + off; c.beginPath(); c.moveTo(rx, ry); c.quadraticCurveTo(rx + 22, ry - 7, rx + 44, ry); c.stroke(); } }
      if (d.level === 1 && d.pair) {
        card(c, 330, 330, d.pair[0], d.glow && d.pair[0] > d.pair[1], g.t);
        card(c, 950, 330, d.pair[1], d.glow && d.pair[1] > d.pair[0], g.t);
        c.fillStyle = 'rgba(255,255,255,.55)'; Dr.rr(c, 560, 255, 160, 150, 24); c.fill();
        sign(c, 640, d.sy, d.dir, 1);
        if (d.landed >= 0) {
          var txt = d.pair[0] + (d.dir > 0 ? ' > ' : ' < ') + d.pair[1];
          c.fillStyle = 'rgba(255,253,246,.96)'; Dr.rr(c, 440, 520, 400, 110, 30); c.fill();
          Dr.text(c, txt, 640, 576, 76, '#2F7A36', { weight: 900 });
        }
        return;
      }
      if (!d.ducks) return;
      var face = d.vx >= 0 ? 1 : -1;
      d.ducks.forEach(function (dk, i) { duck(c, duckX(d, i), DUCK_Y, g.t, dk.ringed, d.showT >= 0 && !dk.ringed, face); });
      if (d.showT >= 0) {
        for (var i = 0, m = 0; i < 10; i++) {
          var x = duckX(d, i);
          if (d.ducks[i].ringed) {
            var rx = 160 + m * 108;
            if (m < d.matched) { c.strokeStyle = '#E4572E'; c.lineWidth = 4; c.setLineDash([8, 8]); c.beginPath(); c.moveTo(x, DUCK_Y + 30); c.lineTo(rx, 600); c.stroke(); c.setLineDash([]); }
            ring(c, rx, 610, 0.8); m++;
          }
        }
        Dr.text(c, '鸭子 10 只', 1170, 480, 38, '#6B4423', { stroke: '#FFF' });
        Dr.text(c, '圈 9 个', 1170, 612, 38, '#B23A17', { stroke: '#FFF' });
      }
      d.flying.forEach(function (f) {
        var p = Math.min(1, f.t / FLY);
        ring(c, f.x0 + (f.x1 - f.x0) * p, f.y0 + (f.y1 - f.y0) * p - Math.sin(p * Math.PI) * 220, 1.1 - 0.2 * p);
      });
      if (d.showT < 0) {
        for (var s = 0; s < d.left - d.flying.length; s++) ring(c, 560 + (s % 5) * 40, 690 - Math.floor(s / 5) * 16, 0.7);
        c.fillStyle = 'rgba(255,253,246,.9)'; Dr.rr(c, 820, 650, 210, 56, 20); c.fill();
        Dr.text(c, '还剩 ' + d.left + ' 个圈', 925, 679, 30, '#6B4423');
      }
    }
  });
  game.follow('#r10c-ducks', function (g) { var d = g.data; return d.level === 0 && d.ducks ? { x: duckX(d, 0) - 60, y: DUCK_Y - 80, w: 9 * 104 + 120, h: 130 } : { x: 230, y: 230, w: 820, h: 300 }; });
  game.follow('#r10c-rings', function () { return { x: 540, y: 640, w: 500, h: 76 }; });
  game.follow('#r10c-sign', function () { return { x: 560, y: 255, w: 160, h: 150 }; });
  K.ready({ emoji: '🦆', title: '套圈比多少', sub: '点池塘里的小鸭，把游泳圈扔过去' });
})();
