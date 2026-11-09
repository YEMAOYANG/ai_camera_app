(function () {
  // 钓鱼配算式：上方的图里有蓝灯和绿灯两部分，合起来是 10。开着小船放鱼钩，
  // 只钓和这幅图对得上的算式鱼。第1关 1 和 9（两道加法、两道减法），第2关 5 和 5（只有一道加法、一道减法），第3关 4 和 6。
  var Dr = K.draw;
  var HX = 54, SURF = 300, LANES = [410, 520, 630], DROP = 620, RISE = 760, FW = 112, FH = 42;
  var PICS = [[1, 9], [5, 5], [4, 6]], SPEED = [[70, 92], [85, 108], [105, 132]];
  var MINUS = '−';
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function needed(a, b) {
    var list = [a + '+' + b + '=10', b + '+' + a + '=10', '10' + MINUS + a + '=' + b, '10' + MINUS + b + '=' + a];
    return list.filter(function (s, i) { return list.indexOf(s) === i; });
  }
  function decoys(a, b) {
    var out = [];
    for (var c = 1; c <= 9; c++) if (c !== a && c !== b && Math.abs(c - a) <= 2) { out.push(c + '+' + (10 - c) + '=10'); out.push('10' + MINUS + c + '=' + (10 - c)); }
    if (b > 1) out.push(a + '+' + (b - 1) + '=' + (a + b - 1));
    if (a > 1) out.push((a - 1) + '+' + b + '=' + (a + b - 1));
    out.push(b + MINUS + '1=' + (b - 1));
    return out.filter(function (s, i) { return out.indexOf(s) === i && needed(a, b).indexOf(s) < 0; });
  }
  function eqText(s) { return s.replace(/\+/g, ' + ').replace(new RegExp(MINUS, 'g'), ' ' + MINUS + ' ').replace('=', ' = '); }
  function assign(d, f) {
    var open = d.need.filter(function (s) { return d.got.indexOf(s) < 0; });
    var present = d.fish.filter(function (o) { return o !== f && o.st === 'swim'; }).map(function (o) { return o.eq; });
    var missing = open.filter(function (s) { return present.indexOf(s) < 0; });
    if (missing.length && Math.random() < 0.7) f.eq = pick(missing);
    else if (d.level === 1 && Math.random() < 0.3) f.eq = pick(d.need);
    else f.eq = Math.random() < 0.35 && open.length ? pick(open) : pick(d.decoy);
  }
  function makeFish(d, lane, k) {
    var dir = lane % 2 ? -1 : 1, f = { lane: lane, y: LANES[lane], x: dir > 0 ? 160 + k * 560 : 1120 - k * 560, vx: dir * rnd(SPEED[d.level][0], SPEED[d.level][1]), st: 'swim', ph: rnd(0, 6), col: pick(['#FF9F43', '#FF6B81', '#7BED9F', '#70A1FF', '#ECCC68']) };
    assign(d, f); return f;
  }
  function setup(g, level) {
    var p = PICS[level];
    g.data = { level: level, a: p[0], b: p[1], need: needed(p[0], p[1]), decoy: decoys(p[0], p[1]), got: [], fish: [], bx: 640, tx: 640,
      hook: { st: 'idle', y: SURF, fish: null }, roundMiss: 0, hint: 0, glow: false, done: null };
    var d = g.data;
    for (var lane = 0; lane < 3; lane++) for (var k = 0; k < 2; k++) d.fish.push(makeFish(d, lane, k));
    g.banner('图上有 ' + p[0] + ' 盏蓝灯、' + p[1] + ' 盏绿灯', '钓出和这幅图对得上的算式', 2.2);
  }
  function drop(d) { if (d.hook.st === 'idle') { d.hook.st = 'down'; K.sfx.whoosh(); } }
  function evaluate(g, f) {
    var d = g.data;
    if (d.need.indexOf(f.eq) >= 0 && d.got.indexOf(f.eq) < 0) {
      d.got.push(f.eq); f.st = 'gone'; K.sfx.coin(); g.sparkle(d.bx + HX, SURF - 40); g.float('钓到啦', d.bx + HX, SURF - 90, { size: 44, color: '#2F8A3A' });
      K.log.push('eq:' + f.eq);
      if (d.got.length >= d.need.length) d.done = { t: 0 };
      return;
    }
    f.st = 'flee'; f.vx = (f.vx > 0 ? 1 : -1) * 420; f.y = LANES[f.lane];
    if (d.got.indexOf(f.eq) >= 0) { g.say('这道已经钓到了，只记一次', 'ok'); return; }
    g.miss(); d.roundMiss++; K.sfx.no();
    if (d.roundMiss === 1) g.say('这道算式和图对不上', 'no');
    else if (d.roundMiss === 2) { d.hint = 4; g.say('看图：蓝灯几盏？绿灯几盏？', 'no'); }
    else { d.hint = 4; d.glow = true; g.say('钓会发光的鱼', 'no'); }
  }
  function drawFish(c, f, t, glow) {
    var dir = f.vx > 0 ? 1 : -1, y = f.y + Math.sin(t * 2 + f.ph) * 6;
    c.save(); c.translate(f.x, y);
    if (glow) { c.fillStyle = 'rgba(255,230,100,' + (0.35 + 0.25 * Math.sin(t * 8)) + ')'; c.beginPath(); c.ellipse(0, 0, FW + 26, FH + 22, 0, 0, Math.PI * 2); c.fill(); }
    c.fillStyle = f.col; c.beginPath(); c.moveTo(-dir * (FW - 6), 0); c.lineTo(-dir * (FW + 40), -34 + Math.sin(t * 9 + f.ph) * 8); c.lineTo(-dir * (FW + 40), 34 + Math.sin(t * 9 + f.ph) * 8); c.closePath(); c.fill();
    c.beginPath(); c.ellipse(0, 0, FW, FH, 0, 0, Math.PI * 2); c.fill();
    c.fillStyle = 'rgba(255,255,255,.92)'; Dr.rr(c, -86, -26, 172, 52, 18); c.fill();
    c.fillStyle = '#FFF'; Dr.circle(c, dir * (FW - 22), -14, 9); c.fillStyle = '#222'; Dr.circle(c, dir * (FW - 19), -14, 4.5);
    Dr.text(c, eqText(f.eq), 0, 2, 30, '#3A2A1A', { weight: 900 });
    c.restore();
  }
  function lampCell(i) { return { x: 70 + (i % 5) * 58, y: 76 + Math.floor(i / 5) * 58 }; }

  var game = K.game({
    levels: 3,
    winPause: 2,
    levelName: function (l) { return ['1 盏蓝灯和 9 盏绿灯', '5 盏蓝灯和 5 盏绿灯', '4 盏蓝灯和 6 盏绿灯'][l]; },
    winText: function (l) { return ['一幅图：两道加法，两道减法！', '两边都是 5：只有一道加法、一道减法。', '看清两部分，算式就钓对了！'][l]; },
    doneTitle: '算式鱼都钓到啦！',
    doneText: '一幅图里的两部分，能写加法，也能写减法；两部分一样多时，只写一道加法和一道减法。',
    bubbleAt: function (g) { return { x: g.data && g.data.bx ? g.data.bx : 640, y: 236 }; },
    reset: function (g, level) { setup(g, level); },
    autopilot: function (g) {
      var d = g.data, h = d.hook;
      if (d.done) return;
      var best = null, bestScore = 1e9;
      d.fish.forEach(function (f) {
        if (f.st !== 'swim' || d.need.indexOf(f.eq) < 0 || d.got.indexOf(f.eq) >= 0) return;
        var t = (f.y - h.y) / DROP, px = f.x + f.vx * Math.max(0, t), score = Math.abs(px - d.bx - HX) + f.lane * 60;
        if (px > 120 && px < 1160 && score < bestScore) { bestScore = score; best = { f: f, px: px }; }
      });
      if (!best) { d.tx = 640; return; }
      d.tx = (h.st === 'down' ? best.f.x : best.px) - HX;
      if (h.st === 'idle' && Math.abs(d.bx + HX - best.px) < 14) {
        var blocked = d.fish.some(function (o) { return o !== best.f && o.st === 'swim' && o.lane < best.f.lane && Math.abs(o.x + o.vx * (o.y - SURF) / DROP - d.bx - HX) < FW + 30; });
        if (!blocked) drop(d);
      }
    },
    update: function (g, dt) {
      var d = g.data, h = d.hook;
      if (d.done) { d.done.t += dt; if (d.done.t > 1.2 && g.state === 'play') { d.done = null; g.win(); } }
      if (!g.auto && g.pointer.active) d.tx = Math.max(110, Math.min(1170, g.pointer.x));
      if (g.keys.left) d.tx = Math.max(110, d.bx - 140); if (g.keys.right) d.tx = Math.min(1170, d.bx + 140);
      if (!g.auto) for (var i = 0; i < g.taps.length; i++) { if (g.taps[i].key || g.taps[i].y > 200) drop(d); }
      if (!g.auto && g.keys.down) drop(d);
      var dx = (d.tx - d.bx) * (1 - Math.exp(-dt * 7)); dx = Math.max(-900 * dt, Math.min(900 * dt, dx)); d.bx += dx;
      if (d.hint > 0) d.hint -= dt;
      d.fish.forEach(function (f) {
        if (f.st === 'swim' || f.st === 'flee') {
          f.x += f.vx * dt;
          if (f.x < -FW - 60 || f.x > 1280 + FW + 60) {
            f.x = f.vx > 0 ? -FW - 50 : 1280 + FW + 50;
            if (f.st === 'flee') { f.st = 'swim'; f.vx = (f.vx > 0 ? 1 : -1) * rnd(SPEED[d.level][0], SPEED[d.level][1]); }
            assign(d, f);
          }
        }
      });
      d.fish = d.fish.filter(function (f) { return f.st !== 'gone'; });
      while (d.fish.length < 6) { var lane = [0, 1, 2].sort(function (a, b) { return d.fish.filter(function (f) { return f.lane === a; }).length - d.fish.filter(function (f) { return f.lane === b; }).length; })[0]; var nf = makeFish(d, lane, 0); nf.x = nf.vx > 0 ? -FW - 50 : 1280 + FW + 50; d.fish.push(nf); }
      if (h.st === 'down') {
        h.y += DROP * dt;
        for (var j = 0; j < d.fish.length; j++) {
          var f = d.fish[j];
          if (f.st === 'swim' && Math.abs(f.x - d.bx - HX) < FW - 6 && Math.abs(f.y - h.y) < FH) { h.fish = f; f.st = 'hooked'; h.st = 'up'; K.sfx.pop(); break; }
        }
        if (h.st === 'down' && h.y >= 690) h.st = 'up';
      } else if (h.st === 'up') {
        h.y -= RISE * dt;
        if (h.fish) { h.fish.x = d.bx + HX; h.fish.y = h.y + FH; }
        if (h.y <= SURF) { h.y = SURF; h.st = 'idle'; var got = h.fish; h.fish = null; if (got) evaluate(g, got); }
      }
    },
    draw: function (g, c) {
      var d = g.data && g.data.fish ? g.data : { fish: [], bx: 640, hook: { y: SURF, st: 'idle' } };
      var sky = c.createLinearGradient(0, 200, 0, SURF); sky.addColorStop(0, '#BFE7FB'); sky.addColorStop(1, '#E8F7FF');
      c.fillStyle = '#FFF4DC'; c.fillRect(0, 0, 1280, 200); c.fillStyle = sky; c.fillRect(0, 200, 1280, SURF - 200);
      var sea = c.createLinearGradient(0, SURF, 0, 720); sea.addColorStop(0, '#5BC0EB'); sea.addColorStop(1, '#1F6FA8');
      c.fillStyle = sea; c.fillRect(0, SURF, 1280, 720 - SURF);
      c.strokeStyle = 'rgba(255,255,255,.5)'; c.lineWidth = 3;
      for (var w = 0; w < 1280; w += 64) { c.beginPath(); c.arc(w + (g.t * 30) % 64, SURF + 4, 26, Math.PI * 1.1, Math.PI * 1.9); c.stroke(); }
      c.fillStyle = 'rgba(255,255,255,.12)'; LANES.forEach(function (y) { c.fillRect(0, y - 2, 1280, 4); });
      d.fish.forEach(function (f) { if (f.st !== 'hooked') drawFish(c, f, g.t, d.glow && d.need.indexOf(f.eq) >= 0 && d.got.indexOf(f.eq) < 0 && f.st === 'swim'); });
      var bx = d.bx, hy = d.hook.y;
      c.strokeStyle = '#3B2A1A'; c.lineWidth = 3; c.beginPath(); c.moveTo(bx + 54, 222); c.lineTo(bx + 54, hy); c.stroke();
      c.strokeStyle = '#9AA4AE'; c.lineWidth = 6; c.beginPath(); c.arc(bx + 54, hy + 12, 12, 0, Math.PI); c.stroke();
      if (d.hook.fish) drawFish(c, d.hook.fish, g.t, false);
      c.fillStyle = '#C8743F'; c.beginPath(); c.moveTo(bx - 96, 262); c.lineTo(bx + 96, 262); c.lineTo(bx + 70, 304); c.lineTo(bx - 70, 304); c.closePath(); c.fill();
      c.fillStyle = '#E39B5B'; c.fillRect(bx - 96, 254, 192, 12);
      c.strokeStyle = '#6B3E1F'; c.lineWidth = 6; c.beginPath(); c.moveTo(bx + 10, 254); c.lineTo(bx + 54, 222); c.stroke();
      c.fillStyle = '#FFD6A5'; Dr.circle(c, bx - 20, 222, 22); c.fillStyle = '#4C8DDB'; Dr.rr(c, bx - 40, 238, 40, 22, 8); c.fill();
      c.fillStyle = '#FF6B6B'; c.beginPath(); c.arc(bx - 20, 214, 22, Math.PI, 0); c.fill();
    },
    drawTop: function (g, c) {
      var d = g.data && g.data.need ? g.data : null;
      c.fillStyle = 'rgba(255,253,246,.97)'; Dr.rr(c, 22, 14, 448, 176, 24); c.fill(); c.lineWidth = 4; c.strokeStyle = '#4C8DDB'; c.stroke();
      if (d) {
        for (var i = 0; i < 10; i++) {
          var q = lampCell(i), blue = i < d.a;
          c.fillStyle = blue ? '#4C8DDB' : '#40A845'; Dr.circle(c, q.x, q.y, 22);
          c.fillStyle = 'rgba(255,255,255,.75)'; Dr.circle(c, q.x - 6, q.y - 7, 7);
        }
        var blink = d.hint > 0 ? 0.5 + 0.5 * Math.sin(g.t * 9) : 1;
        c.save(); c.globalAlpha = blink;
        Dr.text(c, '蓝 ' + d.a + ' 盏', 392, 76, 30, '#2F66AE', { weight: 900 }); Dr.text(c, '绿 ' + d.b + ' 盏', 392, 134, 30, '#2F8A3A', { weight: 900 });
        c.restore();
        Dr.text(c, '合起来 10 盏', 160, 168, 24, '#6B4423');
        c.fillStyle = 'rgba(255,253,246,.97)'; Dr.rr(c, 492, 14, 766, 176, 24); c.fill(); c.lineWidth = 4; c.strokeStyle = '#C98A47'; c.stroke();
        var cols = d.need.length > 2 ? 2 : 1;
        d.need.forEach(function (s, k) {
          var col = k % cols, row = Math.floor(k / cols), w = cols === 2 ? 340 : 700, x = 512 + col * 360, y = 30 + row * 76 + (cols === 1 ? 6 : 0);
          var has = d.got.indexOf(s) >= 0;
          c.fillStyle = has ? '#E9F8E5' : '#F3E6CF'; Dr.rr(c, x, y, w, 64, 16); c.fill(); c.lineWidth = 3; c.strokeStyle = has ? '#7CC77F' : '#D8C3A0'; c.stroke();
          Dr.text(c, has ? eqText(s) : (s.indexOf('+') > 0 ? '加法 ？' : '减法 ？'), x + w / 2, y + 33, 34, has ? '#2F7A36' : '#B49A74', { weight: 900 });
        });
      }
    }
  });
  game.follow('#as10c-card', function () { return { x: 22, y: 14, w: 448, h: 176 }; });
  game.follow('#as10c-slots', function () { return { x: 492, y: 14, w: 766, h: 176 }; });
  game.follow('#as10c-boat', function (g) { var x = g.data && g.data.bx ? g.data.bx : 640; return { x: x - 100, y: 206, w: 200, h: 100 }; });
  K.ready({ emoji: '🎣', title: '钓鱼配算式', sub: '移动小船，只钓和上面这幅图对得上的算式鱼' });
})();
