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

  const supplies = [
    {key: 'book', asset: 'math-book', crop: [183, 123, 875, 1045], url: '__IMG:math-book__'},
    {key: 'case', asset: 'pencil-case', crop: [56, 211, 1144, 831], url: '__IMG:pencil-case__'},
    {key: 'notebook', asset: 'notebook', crop: [102, 71, 1050, 1123], url: '__IMG:notebook__'}
  ].map(supply => ({...supply, picture: loadPicture(supply.asset, supply.url)}));
  const table = {x: 246, y: 302, w: 940, h: 310};
  const chair = {x: 644, y: 620, w: 145, h: 83};
  const targets = {
    leftFar: {x: 424, y: 396}, rightNear: {x: 989, y: 523},
    centerFar: {x: 716, y: 388}, rightFar: {x: 991, y: 390},
    stack: {x: 424, y: 387}
  };
  const arrangements = [
    [['book', 'leftFar'], ['case', 'rightNear']],
    [['book', 'leftFar'], ['case', 'rightNear'], ['notebook', 'rightFar']],
    [['book', 'leftFar'], ['case', 'centerFar'], ['notebook', 'stack']],
    [['book', 'rightFar'], ['case', 'centerFar'], ['notebook', 'leftFar']]
  ];

  K.hud({icon: '', title: '桌面滑滑车', levels: 3});
  K.$('#stars .ic').textContent = '★';
  K.startPictureFallback = () => {
    const picture = K.el('img', 'pic');
    picture.src = fallbacks['desk-lesson'].src;
    picture.alt = '椅子前的课桌上摆着三样学具';
    return picture;
  };
  K.ready({title: '桌面滑滑车', sub: '从自己的椅子看，照小桌图滑好学具。'});

  function rect(ctx, x, y, w, h, radius, color, stroke) {
    K.draw.rr(ctx, x, y, w, h, radius);
    ctx.fillStyle = color;
    ctx.fill();
    if (stroke) {
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 3;
      ctx.stroke();
    }
  }

  function renderSupply(ctx, supply, cx, cy, size) {
    const [, , sw, sh] = supply.crop;
    const scale = Math.min(size / sw, size / sh);
    const w = sw * scale;
    const h = sh * scale;
    const x = cx - w / 2;
    const y = cy - h / 2;
    cropPicture(ctx, supply.picture, supply.crop, x, y, w, h);
  }

  function reset(g, level) {
    const index = g.autoLoop ? 0 : level + 1;
    g.data = {
      items: arrangements[index].map(([key, target], i) => ({
        supply: supplies.find(item => item.key === key), target,
        x: 120, y: 325 + i * 126, homeX: 120, homeY: 325 + i * 126, placed: false
      })),
      down: false, selected: null, virtual: null, settle: null, keyboard: null
    };
  }

  function release(g, item, x, y) {
    const d = g.data;
    const target = targets[item.target];
    const correct = Math.hypot(target.x - x, target.y - y) < 59;
    const supported = item.target !== 'stack' || d.items.some(other => other.supply.key === 'book' && other.placed);
    d.selected = null;
    d.settle = {item, x: correct && supported ? target.x : item.homeX,
      y: correct && supported ? target.y : item.homeY, correct: correct && supported};
    if (!d.settle.correct && Math.hypot(item.homeX - x, item.homeY - y) > 46) {
      g.miss();
      const hint = g.levelMisses === 1 ? '先找自己的椅子，再看看小桌图。'
        : !supported ? '先摆好数学书，再把练习本叠上去。' : '找小图里这件学具的位置，再试一次。';
      g.say(hint, 'no', 2.4);
    }
  }

  function advance(g, dt, p) {
    const d = g.data;
    if (d.settle) {
      const {item, x, y, correct} = d.settle;
      const easing = Math.min(1, dt * 15);
      item.x += (x - item.x) * easing;
      item.y += (y - item.y) * easing;
      if (Math.hypot(x - item.x, y - item.y) < 4) {
        Object.assign(item, {x, y, placed: correct});
        d.settle = null;
        if (correct) {
          K.sfx.coin();
          g.sparkle(x, y);
          g.say('这件摆好了！', 'ok', 1.2);
          if (!g.demoAction()) {
            g.awardPoint();
            if (d.items.every(other => other.placed)) g.win();
          }
        }
      }
      d.down = p.down;
      return;
    }

    if (p.down && !d.down) {
      d.selected = d.items.find(item => !item.placed && Math.hypot(item.x - p.x, item.y - p.y) < 59) || null;
      if (d.selected) K.sfx.pick();
    }
    if (d.selected) {
      if (p.down) {
        const easing = Math.min(1, dt * 18);
        const x = Math.max(60, Math.min(1200, p.x));
        const y = Math.max(285, Math.min(590, p.y));
        d.selected.x += (x - d.selected.x) * easing;
        d.selected.y += (y - d.selected.y) * easing;
      } else {
        release(g, d.selected, p.x, p.y);
      }
    }
    d.down = p.down;
  }

  function controls(g, dt) {
    const d = g.data;
    if (g.pointer.down && !d.keyboard) return g.pointer;
    if (g.taps?.some(tap => tap.key) && !d.settle) {
      if (d.keyboard) {
        const drop = {...d.keyboard, down: false};
        d.keyboard = null;
        return drop;
      }
      const next = d.items.find(item => !item.placed);
      if (next && !d.selected) d.keyboard = {x: next.x, y: next.y, down: true};
    }
    if (!d.keyboard) return g.pointer;
    const dx = Number(!!g.keys.right) - Number(!!g.keys.left);
    const dy = Number(!!g.keys.down) - Number(!!g.keys.up);
    d.keyboard.x = Math.max(60, Math.min(1200, d.keyboard.x + dx * 375 * dt));
    d.keyboard.y = Math.max(285, Math.min(590, d.keyboard.y + dy * 375 * dt));
    return d.keyboard;
  }

  function miniTable(ctx, items) {
    const board = {x: 445, y: 89, w: 390, h: 192};
    rect(ctx, board.x, board.y, board.w, board.h, 25, '#fffdf3', '#d4aa72');
    rect(ctx, 474, 116, 332, 124, 19, '#eac183', '#ae7049');
    rect(ctx, 616, 242, 48, 26, 9, '#6aa58c', '#347763');
    for (const item of items) {
      const target = targets[item.target];
      const px = 490 + (target.x - table.x) / table.w * 300;
      const py = 127 + (target.y - table.y) / table.h * 104;
      renderSupply(ctx, item.supply, px + (item.target === 'stack' ? 8 : 0),
        py - (item.target === 'stack' ? 4 : 0), item.target === 'stack' ? 36 : 45);
    }
  }

  K.game({
    levels: 3, demoOnce: true, score: true,
    narration: ['goal', 'goal', 'challenge'].map(goal => ({
      goal: 'prep-g04-' + goal, hint: 'prep-g04-hint',
      hint2: 'prep-g04-hint2', praise: 'prep-g04-praise'
    })), winPause: 1.25, bannerTime: 0.55, finishMark: reward,
    doneText: '从自己的座位看，三件学具都摆整齐。',
    levelName: level => ['三件摆好', '本子叠在书上', '挑战：学具换位置'][level],
    bubbleAt: () => ({x: 640, y: 281}),
    setup(g) {
      g.follow('#game-goal', () => ({x: 445, y: 89, w: 390, h: 192}));
      g.follow('#game-player', () => {
        const active = g.data.selected || g.data.items?.find(item => item.supply.key === 'book') || {x: 120, y: 325};
        return {x: active.x - 58, y: active.y - 58, w: 116, h: 116};
      });
      g.follow('#game-target', () => {
        const active = g.data.selected || g.data.items?.find(item => g.autoLoop || !item.placed);
        const target = targets[active?.target || 'leftFar'];
        return {x: target.x - 68, y: target.y - 64, w: 136, h: 128};
      });
    },
    reset,
    autopilot(g) {
      const d = g.data;
      if (d.settle) {
        d.virtual = {down: false, x: 120, y: 280};
        return;
      }
      const item = d.items.find(candidate => !candidate.placed);
      if (!item) return;
      if (d.selected !== item) {
        d.virtual = {down: !d.down, x: item.x, y: item.y};
        return;
      }
      const point = targets[item.target];
      d.virtual = {down: Math.hypot(item.x - point.x, item.y - point.y) > 16, ...point};
    },
    update(g, dt) {
      advance(g, dt, g.auto ? g.data.virtual : controls(g, dt));
    },
    draw(g, ctx) {
      ctx.fillStyle = '#f7ecd2';
      ctx.fillRect(0, 0, 1280, 720);
      const items = g.data.items || [];
      miniTable(ctx, items);
      rect(ctx, table.x, table.y + 11, table.w, table.h, 35, '#ad724b');
      rect(ctx, table.x, table.y, table.w, table.h, 35, '#efca8d', '#95613c');
      rect(ctx, chair.x, chair.y, chair.w, chair.h, 20, '#73a48c', '#3f7b65');
      rect(ctx, chair.x - 11, chair.y + 39, chair.w + 22, 44, 15, '#4d846f', '#3f7b65');
      for (const item of items) {
        if (item === g.data.selected) continue;
        const stacked = item.placed && item.target === 'stack';
        renderSupply(ctx, item.supply, item.x + (stacked ? 9 : 0), item.y,
          stacked ? 87 : 108);
      }
      const item = g.data.selected;
      if (item) {
        ctx.save();
        ctx.shadowColor = 'rgba(98,55,28,.3)';
        ctx.shadowBlur = 16;
        ctx.shadowOffsetY = 8;
        renderSupply(ctx, item.supply, item.x, item.y, 114);
        ctx.restore();
      }
    }
  });
})();
