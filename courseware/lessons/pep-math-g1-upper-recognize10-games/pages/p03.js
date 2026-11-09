(function () {
  // 小青蛙过河：青蛙站在荷叶上，过一会儿就会往前跳一格（头上的绿圈转完就跳）。
  // 前面一列有上下两片荷叶，孩子点上半屏或下半屏（或按上下键）瞄准写着“下一个数”的那片。
  var Dr = K.draw;
  var FX = 300, GAP = 260, LANES = [415, 565], MID = 490, RULER = { x: 220, y: 30, w: 840, h: 92 };
  var PLAN = [
    { name: '从 0 往前数到 10', seq: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], start: 0, hop: 2.4 },
    { name: '从 10 往后数到 0', seq: [9, 8, 7, 6, 5, 4, 3, 2, 1, 0], start: 10, hop: 2.2 },
    { name: '往前跳到 10，再掉头', seq: [5, 6, 7, 8, 9, 10, 9, 8, 7], start: 4, hop: 2.0 }
  ];
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function wrongFor(prev, n) {
    var opts = n > prev ? [n + 1, prev, n + 2] : [n - 1, prev, n - 2];
    return pick(opts.filter(function (v) { return v >= 0 && v <= 10 && v !== n; }));
  }
  function shuffleCol(d, i) {
    var col = d.cols[i], prev = i ? d.seq[i - 1] : d.start;
    col.wrong = wrongFor(prev, col.n); col.lane = Math.random() < 0.5 ? 0 : 1; col.sunk = -1;
  }
  function rulerX(n) { return RULER.x + 40 + n * ((RULER.w - 80) / 10); }
  function laneY(l) { return l === 0.5 ? MID : LANES[l]; }

  function drawFrog(c, x, y, s, look) {
    c.save(); c.translate(x, y); c.scale(s, s);
    c.fillStyle = '#3E9B4F'; c.beginPath(); c.ellipse(-34, 8, 22, 12, -0.4, 0, Math.PI * 2); c.fill(); c.beginPath(); c.ellipse(34, 8, 22, 12, 0.4, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#5CC46A'; c.beginPath(); c.ellipse(0, -10, 44, 34, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#D9F5C9'; c.beginPath(); c.ellipse(0, 0, 28, 20, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = '#5CC46A'; Dr.circle(c, -20, -40, 15); Dr.circle(c, 20, -40, 15);
    c.fillStyle = '#FFF'; Dr.circle(c, -20, -41, 10); Dr.circle(c, 20, -41, 10);
    c.fillStyle = '#1F2A1A'; Dr.circle(c, -18 + look * 3, -40, 5); Dr.circle(c, 22 + look * 3, -40, 5);
    c.strokeStyle = '#1F5A2A'; c.lineWidth = 3; c.lineCap = 'round'; c.beginPath(); c.moveTo(-14, -14); c.quadraticCurveTo(0, -4, 14, -14); c.stroke();
    c.fillStyle = 'rgba(255,130,130,.4)'; Dr.circle(c, -26, -18, 6); Dr.circle(c, 26, -18, 6);
    c.restore();
  }
  function drawPad(c, x, y, n, sink, aimed, hint, t) {
    var a = sink >= 0 ? Math.max(0, 1 - sink / 0.7) : 1;
    c.save(); c.globalAlpha = a; c.translate(x, y + (sink >= 0 ? sink * 60 : 0));
    c.fillStyle = 'rgba(20,70,90,.25)'; c.beginPath(); c.ellipse(0, 10, 92, 30, 0, 0, Math.PI * 2); c.fill();
    if (aimed) { c.strokeStyle = 'rgba(255,255,255,.95)'; c.lineWidth = 7; c.beginPath(); c.ellipse(0, 0, 102, 44, 0, 0, Math.PI * 2); c.stroke(); }
    if (hint) { c.strokeStyle = 'rgba(255,209,102,' + (0.6 + 0.4 * Math.sin(t * 8)) + ')'; c.lineWidth = 9; c.beginPath(); c.ellipse(0, 0, 112, 50, 0, 0, Math.PI * 2); c.stroke(); }
    c.fillStyle = '#47A84F'; c.beginPath(); c.ellipse(0, 0, 90, 34, 0, 0.25, Math.PI * 2 - 0.25); c.lineTo(0, 0); c.closePath(); c.fill();
    c.strokeStyle = '#2F7F3A'; c.lineWidth = 3; c.stroke();
    c.fillStyle = '#FFFDF6'; Dr.circle(c, 0, -6, 31);
    Dr.text(c, String(n), 0, -5, 40, '#1F5A2A', { weight: 900 });
    c.restore();
  }
  function drawRuler(g, c, d) {
    c.fillStyle = '#F2C27B'; Dr.rr(c, RULER.x, RULER.y, RULER.w, RULER.h, 16); c.fill();
    c.lineWidth = 4; c.strokeStyle = '#B9803C'; c.stroke();
    for (var n = 0; n <= 10; n++) {
      var x = rulerX(n);
      c.strokeStyle = '#7A4A1C'; c.lineWidth = 3; c.beginPath(); c.moveTo(x, RULER.y + 6); c.lineTo(x, RULER.y + 24); c.stroke();
      if (d.hint === n) { c.fillStyle = 'rgba(255,209,102,' + (0.55 + 0.45 * Math.sin(g.t * 8)) + ')'; Dr.circle(c, x, RULER.y + 56, 29); }
      if (n === d.cur) { c.fillStyle = '#5CC46A'; Dr.circle(c, x, RULER.y + 56, 26); }
      Dr.text(c, String(n), x, RULER.y + 57, 32, n === d.cur ? '#FFF' : '#5B3A1E', { weight: 900 });
    }
    Dr.text(c, d.dir > 0 ? '往前数 →' : '← 往后数', RULER.x + RULER.w / 2, RULER.y + RULER.h + 30, 28, '#FFFDF6', { stroke: 'rgba(30,70,90,.55)', strokeWidth: 7 });
  }

  var game = K.game({
    levels: 3,
    winPause: 2,
    levelName: function (l) { return PLAN[l].name; },
    winText: function (l) { return l === 0 ? '9 后面紧挨着的是 10。下一关倒着跳！' : '倒着数也会啦！下一关跳得更快。'; },
    doneTitle: '小青蛙过河啦！',
    doneText: '正着数、倒着数，9 和 10 紧挨着。',
    bubbleAt: function (g) { var d = g.data; return { x: FX + 40, y: (d.fy || MID) - 160 }; },
    reset: function (g, level) {
      var p = PLAN[level];
      var d = g.data = { level: level, seq: p.seq, start: p.start, hop: p.hop, cur: p.start, i: 0, cols: [],
        lane: 0.5, aim: Math.random() < 0.5 ? 0 : 1, hopT: p.hop + 1.4, jump: null, cam: 0, fy: MID,
        swim: 0, colMiss: 0, hint: null, dir: p.seq[0] > p.start ? 1 : -1 };
      for (var i = 0; i < p.seq.length; i++) { d.cols.push({ n: p.seq[i] }); shuffleCol(d, i); }
    },
    autopilot: function (g) { var d = g.data; if (!d.jump && d.i < d.cols.length) d.aim = d.cols[d.i].lane; },
    update: function (g, dt) {
      var d = g.data;
      d.cols.forEach(function (col) { if (col.sunk >= 0) col.sunk += dt; });
      if (!d.jump) {
        g.taps.forEach(function (t) { d.aim = t.y < MID ? 0 : 1; K.sfx.pick(); });
        if (g.keys.up) d.aim = 0;
        if (g.keys.down) d.aim = 1;
      }
      if (d.swim > 0) {
        d.swim -= dt;
        if (d.swim <= 0) d.jump = { t: 0, from: d.cam, to: d.cam - GAP, y0: d.fy, y1: laneY(d.lane), back: true };
        return;
      }
      if (d.jump) {
        var j = d.jump; j.t += dt;
        var p = Math.min(1, j.t / 0.5);
        d.cam = j.from + (j.to - j.from) * p;
        d.fy = j.y0 + (j.y1 - j.y0) * p - Math.sin(p * Math.PI) * (j.back ? 40 : 110);
        if (p < 1) return;
        d.jump = null; d.fy = j.y1;
        if (j.back) { shuffleCol(d, d.i); d.hopT = d.hop + 0.8; return; }
        if (d.i >= d.cols.length) { K.sfx.ok(); g.say('到岸啦！', 'ok', 2.2); g.win(); return; }
        var col = d.cols[d.i];
        if (j.lane === col.lane) {
          d.lane = j.lane; d.cur = col.n; d.i++; d.colMiss = 0; d.hint = null;
          K.sfx.tick(Math.min(10, col.n + 1)); g.float(col.n, FX, d.fy - 110);
          if (d.i < d.seq.length && d.seq[d.i] < col.n && d.dir > 0) { d.dir = -1; g.say('掉头！往后数', 'ok'); }
          else if (col.n === 10) g.say('9 后面是 10！', 'ok');
          d.hopT = d.hop;
        } else {
          col.sunk = 0; g.miss(); d.colMiss++; K.sfx.splash(); g.shake(0.4);
          g.burst(FX, d.fy, { n: 16, color: '#7CCBF2', lift: 280 });
          if (d.colMiss === 1) g.say('扑通！刚才在 ' + d.cur + ' 上，下一个是几？', 'no', 2.4);
          else { d.hint = col.n; g.say('看数尺上发亮的那个数', 'no', 2.4); }
          d.swim = 1.1;
        }
        return;
      }
      d.hopT -= dt;
      if (d.hopT <= 0) {
        var landing = d.i >= d.cols.length ? MID : LANES[d.aim];
        d.jump = { t: 0, from: d.cam, to: d.cam + GAP, y0: d.fy, y1: landing, lane: d.aim };
        K.sfx.jump();
      }
    },
    draw: function (g, c) {
      var d = g.data && g.data.cols ? g.data : { cols: [], cam: 0, fy: MID, cur: 0, i: 0, dir: 1, start: 0, seq: [10], aim: 0 };
      var w = c.createLinearGradient(0, 0, 0, 720); w.addColorStop(0, '#9ADBF5'); w.addColorStop(0.3, '#5FB8E3'); w.addColorStop(1, '#2F86BF');
      c.fillStyle = w; c.fillRect(0, 0, 1280, 720);
      c.strokeStyle = 'rgba(255,255,255,.35)'; c.lineWidth = 3;
      for (var r = 0; r < 14; r++) {
        var ry = 230 + r * 36, off = ((r * 137 - d.cam * 0.6 + g.t * 30) % 300 + 300) % 300;
        for (var k = -1; k < 6; k++) { var rx = k * 300 + off; c.beginPath(); c.moveTo(rx, ry); c.quadraticCurveTo(rx + 25, ry - 8, rx + 50, ry); c.stroke(); }
      }
      var bankR = FX + 80 - d.cam, farL = FX + (d.cols.length + 1) * GAP - d.cam - 90;
      c.fillStyle = '#7CCC55';
      if (bankR > -50) {
        Dr.rr(c, bankR - 900, 330, 900, 420, 60); c.fill();
        c.fillStyle = '#8A5A24'; c.fillRect(bankR - 150, 235, 8, 110);
        c.fillStyle = '#FFFDF6'; Dr.rr(c, bankR - 196, 200, 100, 60, 12); c.fill();
        Dr.text(c, String(d.start), bankR - 146, 231, 36, '#5B3A1E', { weight: 900 });
      }
      if (farL < 1400) {
        c.fillStyle = '#7CCC55'; Dr.rr(c, farL, 330, 900, 420, 60); c.fill();
        c.fillStyle = '#8A5A24'; c.fillRect(farL + 120, 230, 8, 130);
        c.fillStyle = '#E4572E'; c.beginPath(); c.moveTo(farL + 128, 232); c.lineTo(farL + 230, 262); c.lineTo(farL + 128, 292); c.closePath(); c.fill();
        Dr.text(c, String(d.seq[d.seq.length - 1]), farL + 166, 262, 30, '#FFF', { weight: 900 });
      }
      d.cols.forEach(function (col, i) {
        var x = FX + (i + 1) * GAP - d.cam;
        if (x < -130 || x > 1410) return;
        var passed = i < d.i, next = i === d.i && !passed;
        [0, 1].forEach(function (lane) {
          var right = lane === col.lane;
          if (passed && !right) return;
          drawPad(c, x, LANES[lane], right ? col.n : col.wrong, !right && col.sunk >= 0 ? col.sunk : -1,
            next && !d.jump && d.swim <= 0 && d.aim === lane, next && right && d.hint === col.n, g.t);
        });
      });
      if (g.state === 'play' && !d.jump && d.swim <= 0 && d.i < d.cols.length) {
        var ty = LANES[d.aim];
        c.strokeStyle = 'rgba(255,255,255,.85)'; c.lineWidth = 5; c.setLineDash([10, 12]);
        c.beginPath(); c.moveTo(FX + 30, d.fy - 40); c.quadraticCurveTo(FX + GAP / 2, Math.min(d.fy, ty) - 130, FX + GAP - 20, ty - 40); c.stroke(); c.setLineDash([]);
        var frac = Math.max(0, d.hopT) / d.hop;
        c.strokeStyle = 'rgba(255,255,255,.5)'; c.lineWidth = 8; c.beginPath(); c.arc(FX, d.fy - 60, 70, 0, Math.PI * 2); c.stroke();
        c.strokeStyle = '#7CE07F'; c.beginPath(); c.arc(FX, d.fy - 60, 70, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * frac); c.stroke();
      }
      if (d.swim > 0) {
        c.fillStyle = 'rgba(255,255,255,.55)'; c.beginPath(); c.ellipse(FX, d.fy + 6, 64, 14, 0, 0, Math.PI * 2); c.fill();
        drawFrog(c, FX, d.fy + 14, 0.95, -0.5);
      } else drawFrog(c, FX, d.fy - 30, 1, d.jump ? 1 : 0.4);
    },
    drawTop: function (g, c) { if (g.data && g.data.cols) drawRuler(g, c, g.data); }
  });
  game.follow('#r10b-ruler', function () { return { x: RULER.x, y: RULER.y, w: RULER.w, h: RULER.h }; });
  game.follow('#r10b-frog', function (g) { var d = g.data; return { x: FX - 70, y: (d.fy || MID) - 110, w: 140, h: 130 }; });
  game.follow('#r10b-next', function () { return { x: FX + GAP - 115, y: LANES[0] - 62, w: 230, h: LANES[1] - LANES[0] + 112 }; });
  K.ready({ emoji: '🐸', title: '小青蛙过河', sub: '点上面或下面，瞄准写着下一个数的荷叶' });
})();
