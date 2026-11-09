(function () {
  // 吊车装幼苗：吊车在上面来回走，点一下（或按空格）放下幼苗。
  // 第1关车头在左，只装“从车头数第10节”；第2关车头换到右边；第3关10节车厢每节装一盆，一共10盆。
  var Dr = K.draw;
  var RAIL = 560, CAR_W = 96, STEP = 104, CLAW_Y = 170, CAR_TOP = RAIL - 92;
  var PLAN = [
    { name: '从车头数，装第 10 节', engine: 'left', fill: false, speed: 250 },
    { name: '车头换边了，再装第 10 节', engine: 'right', fill: false, speed: 280 },
    { name: '10 节车厢，每节装一盆', engine: 'left', fill: true, speed: 300 }
  ];
  var img = new Image(), imgOk = false;
  img.onload = function () { imgOk = true; };
  img.src = '__IMG:seedling__';
  function pot(c, x, y, s) {
    if (imgOk) { c.drawImage(img, x - s / 2, y - s / 2, s, s); return; }
    c.fillStyle = '#C8743F'; c.beginPath(); c.moveTo(x - s * 0.3, y); c.lineTo(x + s * 0.3, y); c.lineTo(x + s * 0.22, y + s * 0.4); c.lineTo(x - s * 0.22, y + s * 0.4); c.closePath(); c.fill();
    c.fillStyle = '#5BB655'; Dr.circle(c, x - s * 0.13, y - s * 0.12, s * 0.14); Dr.circle(c, x + s * 0.13, y - s * 0.15, s * 0.14);
  }
  // carriage centre for the k-th carriage counted from the engine (k = 1..10)
  function carX(d, k) { return d.engine === 'left' ? 200 + (k - 1) * STEP + CAR_W / 2 : 1080 - (k - 1) * STEP - CAR_W / 2; }
  function engineX(d) { return d.engine === 'left' ? 30 : 1100; }
  function carAt(d, x) { for (var k = 1; k <= 10; k++) if (Math.abs(x - carX(d, k)) <= CAR_W / 2 - 4) return k; return 0; }

  function drawEngine(c, d, t) {
    // drawn facing +x (front, lamp and chimney at +x, cab at the back); the front always points away from the carriages
    var x = engineX(d), flip = d.engine === 'left', side = flip ? -1 : 1;
    c.save(); c.translate(x + 75, RAIL); if (flip) c.scale(-1, 1);
    c.fillStyle = '#E4572E'; Dr.rr(c, -75, -110, 150, 92, 14); c.fill();
    c.fillStyle = '#B23A17'; Dr.rr(c, -75, -150, 70, 56, 10); c.fill();
    c.fillStyle = '#BFE7FB'; Dr.rr(c, -64, -142, 48, 34, 8); c.fill();
    c.fillStyle = '#4A2F1B'; c.fillRect(20, -150, 24, 44);
    c.fillStyle = '#FFD166'; Dr.circle(c, 70, -60, 12);
    c.fillStyle = '#3D3D3D'; [-48, 0, 46].forEach(function (wx) { Dr.circle(c, wx, -14, 20); });
    c.fillStyle = '#9C9C9C'; [-48, 0, 46].forEach(function (wx) { Dr.circle(c, wx, -14, 8); });
    c.restore();
    for (var i = 0; i < 3; i++) { var p = (t * 0.6 + i / 3) % 1, sx = x + 75 + side * 32; c.fillStyle = 'rgba(255,255,255,' + (0.7 - p * 0.7) + ')'; Dr.circle(c, sx - side * p * 40, RAIL - 160 - p * 90, 16 + p * 18); }
  }
  function drawCar(c, d, k, glow, label, t) {
    var x = carX(d, k), colors = ['#4C8DDB', '#58B45C', '#F6A935', '#8B5CF6', '#E4572E'];
    if (glow) { c.fillStyle = 'rgba(255,209,102,' + (0.5 + 0.4 * Math.sin(t * 8)) + ')'; Dr.rr(c, x - CAR_W / 2 - 10, CAR_TOP - 14, CAR_W + 20, 112, 18); c.fill(); }
    c.fillStyle = colors[(k - 1) % 5]; Dr.rr(c, x - CAR_W / 2, CAR_TOP, CAR_W, 70, 10); c.fill();
    c.fillStyle = 'rgba(255,255,255,.25)'; c.fillRect(x - CAR_W / 2 + 6, CAR_TOP + 10, CAR_W - 12, 8);
    c.fillStyle = '#3D3D3D'; Dr.circle(c, x - 26, RAIL - 14, 15); Dr.circle(c, x + 26, RAIL - 14, 15);
    c.fillStyle = '#9C9C9C'; Dr.circle(c, x - 26, RAIL - 14, 6); Dr.circle(c, x + 26, RAIL - 14, 6);
    if (d.load[k]) pot(c, x, CAR_TOP - 16, 70);
    if (label) {
      c.fillStyle = '#FFFDF6'; Dr.circle(c, x, CAR_TOP + 36, 22);
      Dr.text(c, String(k), x, CAR_TOP + 37, 28, '#6B4423', { weight: 900 });
    }
  }

  var game = K.game({
    levels: 3,
    winPause: 2.4,
    levelName: function (l) { return PLAN[l].name; },
    winText: function (l) { return l === 0 ? '第 10 节只有 1 节。车头换边，第 10 节也换地方！' : '从车头数，第 10 节跟着车头变。下一关：一共 10 节都装上！'; },
    doneTitle: '小火车出发啦！',
    doneText: '第 10 节是 1 节；10 节是全部车厢。',
    bubbleAt: function () { return { x: 640, y: 300 }; },
    reset: function (g, level) {
      var p = PLAN[level];
      g.data = { level: level, engine: p.engine, fill: p.fill, speed: p.speed, cx: 640, dir: 1, drop: null, load: {}, loaded: 0,
        roundMiss: 0, labels: false, countT: -1, counted: 0, cool: 0 };
    },
    autopilot: function (g) {
      var d = g.data;
      if (d.drop || d.countT >= 0 || g.t < d.cool) return;
      var targets = d.fill ? [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].filter(function (k) { return !d.load[k]; }) : [10];
      var lead = d.dir * d.speed * 0.04;
      if (targets.some(function (k) { return Math.abs(d.cx + lead - carX(d, k)) < 9; })) g.taps.push({ x: d.cx, y: 300, auto: true });
    },
    update: function (g, dt) {
      var d = g.data;
      if (d.countT >= 0) {
        d.countT += dt;
        if (d.countT > 0.28 * (d.counted + 1) && d.counted < 10) { d.counted++; K.sfx.tick(d.counted); }
        return;
      }
      d.cx += d.dir * d.speed * dt;
      if (d.cx > 1210) { d.cx = 1210; d.dir = -1; }
      if (d.cx < 70) { d.cx = 70; d.dir = 1; }
      if (!d.drop && g.taps.length && g.t >= d.cool) { d.drop = { x: d.cx, y: CLAW_Y + 40, vy: 0 }; K.sfx.whoosh(); d.cool = g.t + 0.3; }
      if (d.drop) {
        var p = d.drop; p.vy += 1600 * dt; p.y += p.vy * dt;
        if (p.y >= CAR_TOP - 16) {
          var k = carAt(d, p.x); d.drop = null;
          if (d.fill) {
            if (k && !d.load[k]) {
              d.load[k] = true; d.loaded++; K.sfx.coin(); g.sparkle(carX(d, k), CAR_TOP - 20); g.float(d.loaded, carX(d, k), CAR_TOP - 90, { size: 46 });
              if (d.loaded === 10) { g.say('10 节都装上了，一共 10 盆', 'ok', 2.4); d.labels = true; g.win(); }
            } else if (k) { g.miss(); K.sfx.no(); g.say('这节已经有一盆啦，找空车厢', 'no'); }
            else { g.miss(); K.sfx.splash(); g.burst(p.x, RAIL - 30, { n: 10, color: '#C8743F' }); g.say('掉到两节车厢中间啦', 'no'); }
            return;
          }
          if (k === 10) {
            d.load[10] = true; K.sfx.ok(); g.sparkle(carX(d, 10), CAR_TOP - 20);
            d.labels = true; d.countT = 0; d.counted = 0;
            g.say('从车头数：1、2、3……10！就是这节', 'ok', 3.2);
            g.after(3.4, function () { g.win(); });
          } else {
            g.miss(); d.roundMiss++; K.sfx.no(); g.shake(0.4);
            if (k) { d.load[k] = true; g.after(0.8, function () { d.load[k] = false; }); }
            if (d.roundMiss === 1) g.say('从车头开始数一数，第 10 节在哪？', 'no', 2.6);
            else { d.labels = true; g.say('跟着数字从车头数到 10', 'no', 2.6); }
          }
        }
      }
    },
    draw: function (g, c) {
      var d = g.data && g.data.load ? g.data : { engine: 'left', load: {}, cx: 640, labels: false, counted: 0, countT: -1 };
      var sky = c.createLinearGradient(0, 0, 0, 720); sky.addColorStop(0, '#9AD7F6'); sky.addColorStop(0.7, '#E6F6FF'); sky.addColorStop(1, '#FFF3D2');
      c.fillStyle = sky; c.fillRect(0, 0, 1280, 720);
      c.fillStyle = '#B5DDB0'; c.beginPath(); c.moveTo(0, 470); for (var x = 0; x <= 1280; x += 40) c.lineTo(x, 430 - 26 * Math.sin(x * 0.008 + 1)); c.lineTo(1280, 720); c.lineTo(0, 720); c.closePath(); c.fill();
      c.fillStyle = '#8FCB7A'; c.fillRect(0, RAIL, 1280, 160);
      c.fillStyle = '#8A5A24'; for (var s = 0; s < 32; s++) c.fillRect(s * 42, RAIL + 4, 26, 14);
      c.fillStyle = '#6E6E6E'; c.fillRect(0, RAIL - 2, 1280, 7); c.fillRect(0, RAIL + 14, 1280, 5);
      // crane rail and claw
      c.fillStyle = '#7A6A58'; Dr.rr(c, 40, 92, 1200, 22, 10); c.fill();
      var cx = d.cx;
      c.fillStyle = '#F6A935'; Dr.rr(c, cx - 46, 82, 92, 44, 12); c.fill();
      c.strokeStyle = '#5B4A3A'; c.lineWidth = 5; c.beginPath(); c.moveTo(cx, 126); c.lineTo(cx, CLAW_Y); c.stroke();
      c.lineWidth = 7; c.beginPath(); c.moveTo(cx - 34, CLAW_Y + 30); c.lineTo(cx - 20, CLAW_Y); c.lineTo(cx + 20, CLAW_Y); c.lineTo(cx + 34, CLAW_Y + 30); c.stroke();
      if (!d.drop && d.countT < 0 && g.state === 'play') pot(c, cx, CLAW_Y + 40, 66);
      if (d.drop) pot(c, d.drop.x, d.drop.y, 66);
      if (g.state === 'play' && !d.drop) { c.strokeStyle = 'rgba(91,74,58,.35)'; c.lineWidth = 3; c.setLineDash([8, 10]); c.beginPath(); c.moveTo(cx, CLAW_Y + 80); c.lineTo(cx, CAR_TOP - 30); c.stroke(); c.setLineDash([]); }
      drawEngine(c, d, g.t);
      for (var k = 1; k <= 10; k++) {
        var showLabel = d.labels && (d.countT < 0 || k <= d.counted);
        drawCar(c, d, k, d.countT >= 0 && k === 10 && d.counted >= 10, showLabel, g.t);
      }
      c.fillStyle = '#5B4A3A'; for (var j = 1; j < 10; j++) { var a = carX(d, j), b = carX(d, j + 1); c.fillRect(Math.min(a, b) + CAR_W / 2, RAIL - 40, STEP - CAR_W, 8); }
      var ex = engineX(d), first = carX(d, 1);
      c.fillStyle = '#5B4A3A'; c.fillRect(Math.min(ex + 150, first - CAR_W / 2), RAIL - 40, Math.abs(first - CAR_W / 2 - (d.engine === 'left' ? ex + 150 : ex)), 8);
      if (g.state === 'play' && !d.fill) {
        var arrow = d.engine === 'left' ? '车头 → 1、2、3 …… 第 10 节' : '第 10 节 …… 3、2、1 ← 车头';
        c.fillStyle = 'rgba(255,253,246,.92)'; Dr.rr(c, 330, 196, 620, 60, 24); c.fill();
        Dr.text(c, arrow, 640, 227, 32, '#6B4423');
      }
    }
  });
  game.follow('#r10d-train', function () { return { x: 20, y: CAR_TOP - 90, w: 1240, h: 200 }; });
  game.follow('#r10d-engine', function (g) { var d = g.data && g.data.engine ? g.data : { engine: 'left' }; return { x: engineX(d) - 6, y: RAIL - 170, w: 162, h: 170 }; });
  game.follow('#r10d-claw', function (g) { var x = g.data && g.data.cx ? g.data.cx : 640; return { x: x - 60, y: 76, w: 120, h: 150 }; });
  K.ready({ emoji: '🚂', title: '吊车装幼苗', sub: '吊车走到车厢上面时，点一下放下幼苗' });
})();
