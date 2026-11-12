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
    class: loadPicture('walk-class', '__IMG:walk-class__'),
    play: loadPicture('keep-play', '__IMG:keep-play__'),
    bell: loadPicture('school-bell', '__IMG:school-bell__'),
  };
  const places = [{x: 292, y: 292}, {x: 988, y: 292}];
  const start = {x: 640, y: 596};
  const stages = [
    {readyAt: 2.2, classSide: 1, speed: 355, doorRadius: 59},
    {readyAt: 3.5, classSide: 0, speed: 385, doorRadius: 53},
    {readyAt: 4.7, classSide: 1, speed: 400, doorRadius: 50}
  ];

  K.hud({icon: '', title: '铃响走回班', levels: 3});
  K.$('#stars .ic').textContent = '★';
  K.startPictureFallback = () => {
    const picture = K.el('img', 'pic');
    picture.src = fallbacks['class-ready'].src;
    picture.alt = '同学回教室后坐在自己的座位';
    return picture;
  };
  K.ready({title: '铃响走回班', sub: '听到上课铃，再按住走道走进教室。'});

  function panel(ctx, x, y, w, h, color, border) {
    K.draw.rr(ctx, x, y, w, h, 24);
    ctx.fillStyle = color;
    ctx.fill();
    if (border) {
      ctx.strokeStyle = border;
      ctx.lineWidth = 4;
      ctx.stroke();
    }
  }

  function picture(ctx, key, x, y, w, h) {
    const img = images[key].image;
    panel(ctx, x, y, w, h, '#fff9ec', '#dfbf86');
    if (!img.naturalWidth) return;
    ctx.save();
    K.draw.rr(ctx, x + 4, y + 4, w - 8, h - 8, 21);
    ctx.clip();
    const scale = Math.min((w - 8) / img.naturalWidth, (h - 8) / img.naturalHeight);
    const iw = img.naturalWidth * scale;
    const ih = img.naturalHeight * scale;
    ctx.drawImage(img, x + (w - iw) / 2, y + (h - ih) / 2, iw, ih);
    ctx.restore();
  }

  function bell(ctx, ringing, t) {
    panel(ctx, 524, 91, 232, 130, ringing ? '#fff1a7' : '#fffdf6', ringing ? '#d99935' : '#dfbf86');
    const image = images.bell.image;
    if (image.naturalWidth) {
      ctx.save();
      ctx.translate(640, 147);
      if (ringing) ctx.rotate(0.11 * Math.sin(t * 9));
      ctx.drawImage(image, -50, -50, 100, 100);
      ctx.restore();
    }
    if (ringing) {
      ctx.strokeStyle = '#a85825';
      ctx.lineWidth = 4;
      for (const r of [51, 64 + 4 * Math.sin(t * 9)]) {
        for (const a of [0, Math.PI]) {
          ctx.beginPath();
          ctx.arc(640, 153, r, a - 0.53, a + 0.53);
          ctx.stroke();
        }
      }
    }
    K.draw.text(ctx, ringing ? '上课铃响了' : '等一等', 640, 201, 21);
  }

  function reset(g, level) {
    const stage = stages[level];
    g.data = {...start, ...stage, age: 0, ringing: false,
      classSide: g.autoLoop ? 0 : stage.classSide, previousDown: false, releasedAfterBell: true,
      demoInput: null};
  }

  function steer(g, dt, input) {
    const d = g.data;
    d.age += dt;
    if (!d.ringing && d.age >= d.readyAt) {
      d.ringing = true;
      if (input.down) d.releasedAfterBell = false;
      K.sfx.tick(6);
      g.after(0.17, () => K.sfx.tick(9));
      g.after(0.36, () => K.sfx.tick(6));
    }
    if (!input.down) d.releasedAfterBell = true;
    if (!d.ringing && input.down && !d.previousDown) {
      g.miss();
      g.say(g.levelMisses === 1 ? '抬头看看，铃有什么变化？' : '等上课铃响，再按住走道。', 'no', 2.2);
    }
    d.previousDown = input.down;
    if (!d.ringing || !d.releasedAfterBell || !input.down) return;

    const dx = input.x - d.x;
    const dy = input.y - d.y;
    const distance = Math.hypot(dx, dy);
    if (distance > 3) {
      const step = Math.min(distance, d.speed * dt);
      d.x = Math.max(145, Math.min(1135, d.x + dx * step / distance));
      d.y = Math.max(276, Math.min(610, d.y + dy * step / distance));
    }
    const touched = places.findIndex(place => Math.hypot(d.x - place.x, d.y - place.y) <= d.doorRadius);
    if (touched === d.classSide) {
      g.say('到教室了，坐好准备上课！', 'ok', 1.6);
      g.sparkle(d.x, d.y);
      if (!g.demoAction()) {
        g.awardPoint();
        g.win();
      }
    } else if (touched !== -1) {
      g.miss('wrongDoor');
      g.say(g.levelMisses === 1 ? '看看两边的图，你要去做什么？' : '找有课桌的门，走进教室。', 'no', 2.2);
      d.x = start.x;
      d.y = start.y;
      d.releasedAfterBell = false;
    }
  }

  function controls(g) {
    const p = g.pointer;
    const dx = Number(!!g.keys.right) - Number(!!g.keys.left);
    const dy = Number(!!g.keys.down) - Number(!!g.keys.up);
    if (dx || dy) return {down: true, x: g.data.x + 105 * dx, y: g.data.y + 105 * dy};
    return p;
  }

  K.game({
    levels: 3, demoOnce: true, score: true,
    narration: ['goal', 'goal', 'challenge'].map(goal => ({
      goal: 'prep-g02-' + goal, hint: 'prep-g02-hint',
      hint2: 'prep-g02-hint2', praise: 'prep-g02-praise',
      missCues: {wrongDoor: ['prep-g02-door-hint', 'prep-g02-door-hint2']}
    })), bannerTime: 0.55, winPause: 1.25, finishMark: reward,
    doneText: '听见本班的上课铃，回到教室坐好。',
    levelName: level => ['先听上课铃', '教室换一边', '挑战：等晚一点的铃'][level],
    bubbleAt: () => ({x: 640, y: 668}),
    setup(g) {
      g.follow('#game-goal', () => ({x: 524, y: 91, w: 232, h: 130}));
      g.follow('#game-player', () => {
        const d = g.data.x == null ? start : g.data;
        return {x: d.x - 49, y: d.y - 49, w: 98, h: 98};
      });
      g.follow('#game-target', () => {
        const goal = places[g.data.classSide ?? 1];
        return {x: goal.x - 150, y: 240, w: 300, h: 171};
      });
    },
    reset,
    autopilot(g) {
      const d = g.data;
      d.demoInput = {down: d.ringing && d.age >= d.readyAt + 0.35, ...places[d.classSide]};
    },
    update(g, dt) {
      steer(g, dt, g.auto ? g.data.demoInput : controls(g));
    },
    draw(g, ctx) {
      const d = g.data.x == null ? {...start, classSide: 1, ringing: false} : g.data;
      const bg = ctx.createLinearGradient(0, 84, 0, 720);
      bg.addColorStop(0, '#f3edd4');
      bg.addColorStop(1, '#cae1bc');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, 1280, 720);

      for (const [i, place] of places.entries()) {
        const key = i === d.classSide ? 'class' : 'play';
        ctx.beginPath();
        ctx.moveTo(start.x, start.y);
        ctx.lineTo(place.x, place.y);
        ctx.lineCap = 'round';
        ctx.strokeStyle = '#b59563';
        ctx.lineWidth = 132;
        ctx.stroke();
        ctx.strokeStyle = '#fff3ce';
        ctx.lineWidth = 124;
        ctx.stroke();
        const bounce = g.level && key === 'play' && !d.ringing && !g.reduce
          ? 6 * Math.abs(Math.sin(d.age * 3)) : 0;
        picture(ctx, key, place.x - 151, 224 - bounce, 302, 196);
        panel(ctx, place.x - 47, 402, 94, 43, '#fffdf6', '#d4ae70');
        K.draw.text(ctx, key === 'class' ? '教室' : '操场', place.x, 423, 23);
      }
      bell(ctx, d.ringing, g.t);
      ctx.fillStyle = '#fff7db';
      K.draw.circle(ctx, d.x, d.y, 53);
      ctx.strokeStyle = '#a86a36';
      ctx.lineWidth = 4;
      ctx.stroke();
      ctx.save();
      ctx.clip();
      cropPicture(ctx, images.class, [397, 25, 390, 390], d.x - 52, d.y - 52, 104, 104);
      ctx.restore();
    }
  });
})();
