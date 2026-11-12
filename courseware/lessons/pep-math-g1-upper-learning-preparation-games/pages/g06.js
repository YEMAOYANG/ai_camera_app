(function () {
  const fallbacks = JSON.parse(K.$('#prep-picture-fallbacks').textContent);

  // The in-page backup is a smaller encode of the same registered artwork.
  function loadPicture(key, url) {
    const {width, height, src} = fallbacks[key];
    const primary = new Image();
    const backup = new Image();
    primary.src = url;
    backup.src = src;
    return {width, height, get image() {return primary.naturalWidth ? primary : backup;}};
  }

  function cropPicture(ctx, picture, crop, x, y, w, h) {
    const image = picture.image;
    if (!image.naturalWidth) return;
    const [sx, sy, sw, sh] = crop;
    const dx = image.naturalWidth / picture.width;
    const dy = image.naturalHeight / picture.height;
    ctx.drawImage(image, sx * dx, sy * dy, sw * dx, sh * dy, x, y, w, h);
  }

  const reward = '<img class="prep-reward" alt="上课准备小奖章" src="' + fallbacks['class-ready'].src + '">';

  const images = {
    listen: loadPicture('listen', '__IMG:listen__'),
    ready: loadPicture('class-ready', '__IMG:class-ready__'),
    raise: loadPicture('raise-hand', '__IMG:raise-hand__'),
    teacher: loadPicture('speak-turn', '__IMG:speak-turn__'),
  };
  const children = [{x: 274, y: 494}, {x: 1006, y: 494}];
  const player = {x: 640, y: 494};
  const layouts = [[0], [1], [0, 1], [1, 0, 1]];

  K.hud({icon: '', title: '轮到我来传话', levels: 3});
  K.$('#stars .ic').textContent = '★';
  K.startPictureFallback = () => {
    const picture = K.el('img', 'pic');
    picture.src = fallbacks['raise-hand'].src;
    picture.alt = '一名同学举手等候发言';
    return picture;
  };
  K.ready({title: '轮到我来传话', sub: '听同学讲完，举手等到，再把话泡送给伙伴。'});

  function rect(ctx, x, y, w, h, r, fill, edge, lineWidth = 4) {
    K.draw.rr(ctx, x, y, w, h, r);
    ctx.fillStyle = fill;
    ctx.fill();
    if (edge) {
      ctx.strokeStyle = edge;
      ctx.lineWidth = lineWidth;
      ctx.stroke();
    }
  }

  function art(ctx, picture, x, y, w, h, crop = [0, 0, picture.width, picture.height]) {
    const [, , sw, sh] = crop;
    const scale = Math.min(w / sw, h / sh);
    const iw = sw * scale;
    const ih = sh * scale;
    const left = x + (w - iw) / 2;
    const top = y + (h - ih) / 2;
    ctx.save();
    K.draw.rr(ctx, left, top, iw, ih, 21);
    ctx.clip();
    cropPicture(ctx, picture, crop, left, top, iw, ih);
    ctx.restore();
  }

  function bubble(ctx, x, y, radius, time) {
    const color = '#276951';
    rect(ctx, x - radius, y - radius * 0.65, radius * 2, radius * 1.3, radius / 2,
      '#fcffed', '#53967a', 4);
    ctx.fillStyle = color;
    for (let i = -1; i <= 1; i++) {
      const pulse = 5 + Math.sin(time * 8 - i) * 1.6;
      K.draw.circle(ctx, x + i * radius / 2.3, y, pulse);
    }
  }

  function direction(ctx, x, y, dx, dy) {
    const heading = Math.atan2(dy, dx);
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(heading);
    ctx.strokeStyle = '#b97535';
    ctx.lineWidth = 8;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(-20, 0);
    ctx.lineTo(25, 0);
    ctx.lineTo(9, -15);
    ctx.moveTo(25, 0);
    ctx.lineTo(9, 15);
    ctx.stroke();
    ctx.restore();
  }

  function reset(g, level) {
    const sequence = layouts[g.autoLoop ? 0 : level + 1];
    g.data = {sequence, peer: 0, phase: 'listen', elapsed: 0, down: false,
      gesture: null, keys: {}, orb: null, virtual: {down: false, ...player}, stroke: null,
      listener: sequence.at(-1)};
  }

  function moveTo(d, phase) {
    d.phase = phase;
    d.elapsed = 0;
  }

  function miss(g, first, next) {
    g.miss();
    g.say(g.levelMisses === 1 ? first : next, 'no', 2.3);
  }

  function gesture(g, dx, dy) {
    const d = g.data;
    if (Math.hypot(dx, dy) < 49) return;
    if (dy < -43 && Math.abs(dx) < 0.8 * -dy) {
      if (d.phase === 'ready') {
        moveTo(d, 'waiting');
        K.sfx.pick();
        if (!g.demoAction()) g.awardPoint();
      } else if (d.phase === 'listen') {
        miss(g, '先看看，话泡还在谁头顶？', '等同学说完，再举手。');
      }
      return;
    }
    if (Math.abs(dx) < 43 || d.phase === 'flight') return;
    if (d.phase !== 'speak') {
      miss(g, '看看话泡现在在哪儿。', '同学说完后先举手，再等老师递来话泡。');
      return;
    }
    const distance = Math.hypot(dx, dy);
    d.orb = {x: player.x, y: player.y, vx: 610 * dx / distance, vy: 610 * dy / distance};
    moveTo(d, 'flight');
    K.sfx.whoosh();
  }

  function advance(g, dt, input, keys) {
    const d = g.data;
    d.elapsed += dt;
    if (d.phase === 'listen' && d.elapsed >= 2.4) {
      d.peer++;
      moveTo(d, d.peer < d.sequence.length ? 'listen' : 'ready');
    } else if (d.phase === 'waiting' && d.elapsed >= 1.5) {
      moveTo(d, 'speak');
      K.sfx.tick(5);
    }

    if (input.down && !d.down && Math.abs(input.x - player.x) <= 84 && Math.abs(input.y - player.y) <= 81) {
      d.gesture = {x: input.x, y: input.y};
    }
    if (!input.down && d.down && d.gesture) {
      const {x, y} = d.gesture;
      d.gesture = null;
      gesture(g, input.x - x, input.y - y);
    }
    d.down = input.down;

    if (keys.up && !d.keys.up) gesture(g, 0, -90);
    if (keys.left && !d.keys.left) gesture(g, -95, 0);
    if (keys.right && !d.keys.right) gesture(g, 95, 0);
    d.keys = {...keys};

    if (d.phase !== 'flight') return;
    const orb = d.orb;
    orb.x += orb.vx * dt;
    orb.y += orb.vy * dt;
    const target = children[d.listener];
    if (Math.hypot(orb.x - target.x, orb.y - target.y) < 88) {
      moveTo(d, 'heard');
      g.say('伙伴听见了！一个讲完，一个再接。', 'ok', 1.5);
      g.sparkle(target.x, target.y - 36);
      g.awardPoint();
      g.win();
    } else if (d.elapsed > 0.91 || orb.y < 260 || orb.y > 638) {
      miss(g, '看看哪位伙伴面前亮着。', '从你的位置，沿桌边把话泡划向亮着的伙伴。');
      moveTo(d, 'speak');
      d.orb = null;
    }
  }

  K.game({
    levels: 3, demoOnce: true, score: true,
    narration: ['goal', 'goal', 'challenge'].map(goal => ({
      goal: 'prep-g06-' + goal, hint: 'prep-g06-hint',
      hint2: 'prep-g06-hint2', praise: 'prep-g06-praise'
    })), bannerTime: 0.55, winPause: 1.2, finishMark: reward,
    doneText: '听完再举手，轮到自己再开口。', levelName: level => ['听完再接话', '两位同学先说', '挑战：听完三轮'][level],
    bubbleAt: () => ({x: 640, y: 661}),
    setup(g) {
      g.follow('#game-goal', () => ({x: 481, y: 92, w: 318, h: 215}));
      g.follow('#game-player', () => ({x: player.x - 83, y: player.y - 81, w: 166, h: 162}));
      g.follow('#game-target', () => {
        const target = children[g.data.listener ?? 1];
        return {x: target.x - 83, y: target.y - 81, w: 166, h: 162};
      });
    },
    reset,
    autopilot(g, dt) {
      const d = g.data;
      const target = children[d.listener];
      if (!d.stroke && ['ready', 'speak'].includes(d.phase) && d.elapsed >= 0.43) {
        d.stroke = {t: 0, dx: d.phase === 'ready' ? 0 : Math.sign(target.x - player.x) * 122,
          dy: d.phase === 'ready' ? -105 : 0};
      }
      if (d.stroke) {
        const stroke = d.stroke;
        stroke.t += dt;
        const fraction = Math.max(0, Math.min(1, (stroke.t - 0.10) / 0.21));
        d.virtual = {down: stroke.t < 0.37, x: player.x + stroke.dx * fraction,
          y: player.y + stroke.dy * fraction};
        if (!d.virtual.down) d.stroke = null;
      } else {
        d.virtual = {down: false, ...player};
      }
    },
    update(g, dt) {
      advance(g, dt, g.auto ? g.data.virtual : g.pointer, g.auto ? {} : g.keys);
    },
    draw(g, ctx) {
      const d = g.data;
      ctx.fillStyle = '#f8ead2';
      ctx.fillRect(0, 0, 1280, 720);
      rect(ctx, 481, 92, 318, 215, 25, '#fff8e9', '#d6aa74');
      art(ctx, images.teacher, 494, 103, 292, 192);
      rect(ctx, 93, 400, 1094, 199, 34, '#edc588', '#af754b', 5);
      rect(ctx, 105, 414, 1070, 160, 27, '#f6d69a');
      for (const [i, spot] of children.entries()) {
        const active = d.phase === 'listen' && d.sequence[d.peer] === i;
        const next = ['speak', 'flight', 'heard'].includes(d.phase) && d.listener === i;
        rect(ctx, spot.x - 83, spot.y - 81, 166, 162, 23, '#fff7df',
          active || next ? '#469274' : '#cc9b67', active || next ? 7 : 4);
        const crop = i === 0 ? [30, 90, 650, 675] : [818, 87, 610, 680];
        art(ctx, images.listen, spot.x - 75, spot.y - 74, 150, 147, crop);
        if (active || (next && d.phase === 'heard')) bubble(ctx, spot.x, 368, 45, g.t);
      }
      const isWaiting = d.phase === 'waiting';
      const hasTurn = ['speak', 'flight', 'heard'].includes(d.phase);
      rect(ctx, player.x - 83, player.y - 81, 166, 162, 23, '#ffefc7',
        hasTurn ? '#4d9974' : '#c18b4f', hasTurn ? 7 : 4);
      if (isWaiting || hasTurn) art(ctx, images.raise, player.x - 75, player.y - 74, 150, 147,
        [295, 48, 820, 824]);
      else art(ctx, images.ready, player.x - 75, player.y - 74, 150, 147,
        [880, 277, 310, 310]);
      K.draw.text(ctx, '你', 640, 585, 22);

      if (d.phase === 'ready') direction(ctx, player.x, 371, 0, -1);
      if (isWaiting) {
        const fraction = Math.max(0, Math.min(1, (d.elapsed - 0.56) / 0.94));
        bubble(ctx, 640, 315 + fraction * 53, 38, g.t);
      }
      if (d.phase === 'speak') {
        const sign = d.listener === 0 ? -1 : 1;
        direction(ctx, player.x + sign * 169, 494, sign, 0);
        bubble(ctx, 640, 368, 43, g.t);
      }
      if (d.phase === 'flight') bubble(ctx, d.orb.x, d.orb.y, 38, g.t);
    }
  });
})();
