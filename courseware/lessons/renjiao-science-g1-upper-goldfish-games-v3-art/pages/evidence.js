/* A time window matters: hold through the action, release before the next shot. */
(function () {
  const D = K.draw;
  const viewport = {x: 33, y: 159, w: 847, h: 393};
  const shutter = {x: 98, y: 563, w: 715, h: 115};
  const proof = {x: 905, y: 159, w: 342, h: 519};
  const ink = '#163c4a';
  const sea = '#126661';
  const clipStyle = {
    swim: {name: '摆尾游动', what: '尾鳍摆动，鱼往前游', art: '__IMG:clue-tail__'},
    feed: {name: '张嘴吃食', what: '看见鱼食进了嘴', art: '__IMG:feeding__', crop: [.15, .23, .33, .46]},
    gill: {name: '鳃盖开合', what: '看见眼后的鳃盖开合', art: '__IMG:gill__'}
  };
  const levels = [
    {name: '先拍摆尾', targets: ['swim'], pattern: ['feed', 'swim'], seconds: 4.6},
    {name: '找鱼吃食的时刻', targets: ['feed'], pattern: ['gill', 'feed', 'swim'], seconds: 4.25},
    {name: '把两段证据接起来', targets: ['gill', 'swim'], pattern: ['feed', 'swim', 'gill'], seconds: 4}
  ];
  const finalLines = [
    '拍到了尾鳍摆动，鱼往前游。',
    '拍到了鱼食进嘴。',
    '鳃盖开合、摆尾游动，两段都拍到了。'
  ];
  const stillFractions = [.30, .57, .84];
  const lead = 1.04;
  const maxStart = .45;
  const minFinish = .85;
  const box = (c, x, y, w, h, r, color) => {
    D.rr(c, x, y, w, h, r);
    c.fillStyle = color;
    c.fill();
  };
  const text = (c, content, x, y, size, color = ink, align = 'left') =>
    D.text(c, content, x, y, size, color, {align});
  function img(src) {
    const result = new Image();
    result.src = src;
    return result;
  }
  function valid(source) { return source.complete && source.naturalWidth > 0; }
  const baseFish = img('__IMG:fish-orange__');
  const spareFish = img('__IMG:fish-white__');
  const water = img('__IMG:aquarium-water__');
  let swimSheet;
  for (const part of Object.values(clipStyle)) part.image = img(part.art);
  function within(p, area) {
    return p.x >= area.x && p.x <= area.x + area.w && p.y >= area.y && p.y <= area.y + area.h;
  }
  function frameAt(level, time) {
    const duration = level.seconds + lead;
    const order = Math.floor(time / duration);
    const age = time % duration - lead;
    return {
      kind: level.pattern[order % level.pattern.length],
      order,
      age,
      progress: Math.max(0, Math.min(1, age / level.seconds)),
      running: age >= 0
    };
  }
  function drawWater(c) {
    const g = c.createLinearGradient(0, 0, 0, 393);
    g.addColorStop(0, '#eefafa');
    g.addColorStop(1, '#bee5e5');
    c.fillStyle = g;
    c.fillRect(0, 0, 847, 393);
    if (!valid(water)) return;
    c.save();
    c.beginPath();
    c.rect(0, 0, 847, 393);
    c.clip();
    const size = Math.max(847 / water.naturalWidth, 393 / water.naturalHeight);
    const w = water.naturalWidth * size;
    const h = water.naturalHeight * size;
    c.drawImage(water, (847 - w) / 2, (393 - h) / 2, w, h);
    c.restore();
  }
  function bendTail(source, wag) {
    if (!swimSheet) {
      swimSheet = document.createElement('canvas');
      swimSheet.width = 512;
      swimSheet.height = 332;
    }
    const c = swimSheet.getContext('2d');
    const edge = 333;
    const baseY = 22;
    const xScale = source.naturalWidth / 512;
    const sh = source.naturalHeight;
    c.clearRect(0, 0, 512, 332);
    c.drawImage(source, 0, 0, edge * xScale, sh, 0, baseY, edge, 288);
    // The hinge follows the base of the illustrated tail. Adjacent strips
    // share a transparent canvas so the original scales and fins stay visible.
    for (let x = edge; x < 512; x += 6) {
      const width = Math.min(6, 512 - x);
      const strength = Math.pow((x + width / 2 - edge) / (512 - edge), 1.7);
      const shift = Math.round(wag * strength * 108);
      c.drawImage(source, x * xScale, 0, width * xScale, sh, x, baseY + shift, width, 288);
    }
    return swimSheet;
  }
  function drawFish(c, source, x, y, w, wag) {
    if (!valid(source)) return;
    const h = w * 9 / 16;
    if (Math.abs(wag) < .005) c.drawImage(source, x, y, w, h);
    else c.drawImage(bendTail(source, wag), x, y - h * 22 / 288, w, h * 332 / 288);
  }
  function videoFrame(c, kind, progress, r, overview = false) {
    const crop = overview && kind === 'gill' ? {x: 112, y: 55, w: 450, h: 250}
      : overview && kind === 'feed' ? {x: 18, y: 30, w: 437, h: 257}
      : {x: 0, y: 0, w: 847, h: 393};
    c.save();
    D.rr(c, r.x, r.y, r.w, r.h, overview ? 9 : 23);
    c.clip();
    c.fillStyle = '#d9efed';
    c.fillRect(r.x, r.y, r.w, r.h);
    const size = Math.min(r.w / crop.w, r.h / crop.h);
    c.translate(r.x + (r.w - crop.w * size) / 2 - crop.x * size,
      r.y + (r.h - crop.h * size) / 2 - crop.y * size);
    c.scale(size, size);
    drawWater(c);

    const source = valid(baseFish) ? baseFish : spareFish;
    const bodyWidth = kind === 'gill' ? 805 : kind === 'feed' ? 590 : 520;
    const bodyHeight = bodyWidth * 9 / 16;
    const left = kind === 'gill' ? 76 : kind === 'feed' ? 233 : 307 - 245 * progress;
    const top = (393 - bodyHeight) / 2;
    const bend = kind === 'swim' ? .19 * Math.sin(progress * 8 * Math.PI) : 0;
    drawFish(c, source, left, top, bodyWidth, bend);
    if (!valid(source)) {
      if (!overview) text(c, '观察画面加载中', 423, 193, 31, ink, 'center');
      c.restore();
      return;
    }
    if (kind === 'gill') {
      // The gill cover margin on the side of the head opens and closes.
      const x = left + bodyWidth * .205;
      const y = top + bodyHeight * .409;
      const endX = left + bodyWidth * .183;
      const endY = top + bodyHeight * .681;
      const open = (1 - Math.cos(6 * Math.PI * progress)) / 2;
      const seam = x + 64;
      const midY = y + (endY - y) * .46;
      c.fillStyle = 'rgba(131,55,34,' + (.46 * open) + ')';
      c.beginPath();
      c.moveTo(x, y);
      c.quadraticCurveTo(seam + 23 * open, midY, endX, endY);
      c.quadraticCurveTo(seam, midY, x, y);
      c.fill();
      c.strokeStyle = 'rgba(122,53,26,' + (.68 * open) + ')';
      c.lineWidth = 1 + 5 * open;
      c.lineCap = 'round';
      c.beginPath();
      c.moveTo(x, y);
      c.quadraticCurveTo(seam + 23 * open, midY, endX, endY);
      c.stroke();
    } else if (kind === 'feed') {
      const x = left + bodyWidth * .036;
      const y = top + bodyHeight * .55;
      const open = Math.sin(Math.PI * Math.max(0, Math.min(1, (progress - .21) / .75)));
      if (open > .03) {
        c.fillStyle = '#783329';
        c.strokeStyle = '#ffc291';
        c.lineWidth = 4;
        c.beginPath();
        c.ellipse(x, y, 2.5 + 3.5 * open, 1.5 + 11 * open, -.24, 0, 2 * Math.PI);
        c.fill();
        c.stroke();
      }
      if (progress > 0 && progress < .81) {
        const travel = Math.pow(progress / .81, .85);
        const foodX = x - 7 - 144 * (1 - travel);
        const foodY = y - 143 * (1 - travel);
        c.fillStyle = '#945328';
        D.circle(c, foodX, foodY, 10);
        c.fillStyle = '#f0bf7c';
        D.circle(c, foodX - 3, foodY - 4, 4);
      }
    }
    c.restore();
  }
  function camIcon(c, x, y, recording) {
    box(c, x, y, 66, 47, 11, recording ? '#fff3e7' : '#c3ede5');
    c.fillStyle = recording ? '#ef724e' : '#126661';
    D.circle(c, x + 30, y + 23, 11);
    c.fillRect(x + 58, y + 12, 18, 24);
  }
  function handIcon(c, x, y, pressing) {
    c.save();
    c.translate(x, y + (pressing ? 6 : 0));
    c.fillStyle = '#ffdbb2';
    c.strokeStyle = '#4e635c';
    c.lineWidth = 3.5;
    c.beginPath();
    c.moveTo(12, 51);
    c.lineTo(2, 35);
    c.quadraticCurveTo(-3, 25, 5, 23);
    c.quadraticCurveTo(10, 21, 17, 29);
    c.lineTo(17, 4);
    c.quadraticCurveTo(19, -8, 27, -3);
    c.lineTo(29, 20);
    c.quadraticCurveTo(50, 15, 49, 33);
    c.lineTo(41, 54);
    c.closePath();
    c.fill();
    c.stroke();
    c.restore();
  }
  function smallArt(c, image, r, crop = [0, 0, 1, 1]) {
    if (!valid(image)) return;
    c.save();
    D.rr(c, r.x, r.y, r.w, r.h, 13);
    c.clip();
    const [left, top, width, height] = crop;
    const srcW = image.naturalWidth * width;
    const srcH = image.naturalHeight * height;
    const size = Math.min(r.w / srcW, r.h / srcH);
    const w = srcW * size;
    const h = srcH * size;
    c.drawImage(image, image.naturalWidth * left, image.naturalHeight * top, srcW, srcH,
      r.x + (r.w - w) / 2, r.y + (r.h - h) / 2, w, h);
    c.restore();
  }
  function strip(c, shot, rect) {
    const gap = 6;
    const cell = (rect.w - 2 * gap) / 3;
    for (let i = 0; i < 3; i++) {
      videoFrame(c, shot.kind, shot.frames[i],
        {x: rect.x + i * (cell + gap), y: rect.y, w: cell, h: rect.h}, true);
    }
  }
  function evidenceRack(c, d, time) {
    const next = d.level.targets[d.clips.length];
    box(c, proof.x, proof.y, proof.w, proof.h, 25, '#fffcf3');
    text(c, '我的观察影片', 926, 192, 33);
    text(c, d.clips.length + ' / ' + d.level.targets.length, 1221, 192, 25, sea, 'right');
    if (next) {
      const task = clipStyle[next];
      box(c, 923, 218, 305, 137, 18, '#dcefeb');
      smallArt(c, task.image, {x: 932, y: 228, w: 110, h: 117}, task.crop);
      text(c, '这次拍', 1054, 260, 23, sea);
      text(c, task.name, 1054, 301, 31);
    } else {
      const segment = 2.9;
      const elapsed = time - d.completedAt;
      const clip = d.clips[Math.floor(elapsed / segment) % d.clips.length];
      const progress = clip.from + (clip.until - clip.from) * ((elapsed % segment) / segment);
      videoFrame(c, clip.kind, progress, {x: 923, y: 218, w: 305, h: 137}, true);
      box(c, 933, 226, 113, 34, 13, '#fffffff2');
      text(c, '影片回放', 942, 242, 21, sea);
    }
    for (let i = 0; i < d.level.targets.length; i++) {
      const top = 369 + i * 135;
      const shot = d.clips[i];
      box(c, 923, top, 305, 124, 17, shot ? '#d6efdf' : '#eeeadd');
      if (shot) {
        strip(c, shot, {x: 934, y: top + 11, w: 284, h: 61});
        text(c, clipStyle[shot.kind].what, 935, top + 95, 20);
      } else {
        for (let f = 0; f < 3; f++) box(c, 934 + f * 96, top + 12, 90, 59, 7, '#dad8cd');
        text(c, '等你把动作拍进来', 934, top + 96, 21, '#526863');
      }
    }
  }
  function draw(g, c) {
    const d = g.data.film;
    if (!d) return;
    const sample = d.complete || frameAt(d.level, d.time);
    c.fillStyle = '#e6f5f2';
    c.fillRect(0, 0, 1280, 720);
    box(c, 33, 28, 1214, 98, 25, '#153f53');
    text(c, '把观察接成小电影', 57, 64, 36, '#fff');
    text(c, '等动作出现 · 按住拍 · 拍够松手', 58, 104, 22, '#bce5df');
    text(c, '观察员  ' + (g.level + 1) + ' / 3', 1210, 77, 27, '#fff', 'right');
    videoFrame(c, sample.running ? sample.kind : null, sample.progress, viewport);
    box(c, 54, 177, 167, 41, 17, '#ffffffef');
    text(c, '动作示意', 71, 197, 23, sea);

    const active = d.attempt && !d.attempt.mixed;
    const canRelease = active && d.attempt.last >= minFinish && d.attempt.frames.length === 3;
    const progress = active ? d.attempt.frames.length / 3 : 0;
    box(c, shutter.x, shutter.y, shutter.w, shutter.h, 29, active ? '#076e68' : '#214b5b');
    camIcon(c, 133, 586, active);
    handIcon(c, 720, 595, Boolean(active));
    text(c, canRelease ? '现在松手' : active ? '继续按住' : '按住录像', 245, 600, 36, '#fff');
    for (let i = 0; i < 3; i++) {
      box(c, 246 + i * 126, 637, 113, 14, 7, progress >= (i + 1) / 3 ? '#a6e7b7' : '#9abeb9');
    }
    evidenceRack(c, d, g.t);
  }

  K.ready({title: '把观察接成小电影', sub: '看到要拍的动作，按住录像。拍够三格，再松手。'});
  K.game({
    levels: levels.length,
    winPause: 1.15,
    bannerTime: .85,
    starsFor: () => 3,
    levelName: index => levels[index].name,
    winText: index => finalLines[index],
    finishMark: '★★★',
    doneTitle: '观察影片剪好了',
    doneText: '拍到鳃盖开合，还拍到摆尾游动。',
    bubbleAt: () => ({x: 436, y: 491}),
    setup(g) {
      g.follow('#game-goal', () => ({x: 921, y: 217, w: 308, h: 140}));
      g.follow('#game-player', () => shutter);
      g.follow('#game-target', () => ({x: 921, y: 364, w: 308, h: 276}));
    },
    reset(g, index) {
      g.pointer.down = false;
      g.data.film = {
        level: levels[index], clips: [], time: 0, attempt: null, pressed: false, complete: null, completedAt: 0
      };
    },
    autopilot(g) {
      const d = g.data.film;
      const state = frameAt(d.level, d.time);
      const wanted = d.level.targets[d.clips.length];
      const shouldHold = state.running && state.kind === wanted && state.progress >= .12 && state.progress < .92;
      Object.assign(g.pointer, {x: 441, y: 614, down: shouldHold, active: true});
    },
    update(g, dt) {
      const d = g.data.film;
      d.time += dt;
      const sample = frameAt(d.level, d.time);
      const wanted = d.level.targets[d.clips.length];
      const pressed = Boolean(g.keys.jump || g.pointer.down && within(g.pointer, shutter));
      if (pressed && !d.pressed) {
        const matches = sample.running && sample.kind === wanted && sample.progress <= maxStart;
        if (!valid(baseFish) && !valid(spareFish)) return;
        d.attempt = {
          kind: sample.kind, order: sample.order, first: sample.progress, last: 0, frames: [], mixed: !matches
        };
        if (!matches) g.say('先看看鱼的哪里在动，等下一回。', 'no', 1.9);
      }
      if (pressed && d.attempt && !d.attempt.mixed) {
        if (sample.order !== d.attempt.order) {
          d.attempt.mixed = true;
          g.say('这段接进了另一个动作，再拍一次。', 'no', 2.0);
        } else {
          const previous = d.attempt.last;
          d.attempt.last = sample.progress;
          for (const marker of stillFractions) {
            if (previous < marker && sample.progress >= marker) d.attempt.frames.push(sample.progress);
          }
        }
      }
      if (!pressed && d.pressed && d.attempt) {
        const filmed = d.attempt;
        d.attempt = null;
        if (!filmed.mixed && filmed.last >= minFinish && filmed.frames.length === 3) {
          d.clips.push({kind: filmed.kind, frames: filmed.frames, from: filmed.first, until: filmed.last});
          g.sparkle(1078, 450 + (d.clips.length - 1) * 120, '#dca650');
          K.sfx.pick();
          if (d.clips.length === d.level.targets.length) {
            d.complete = sample;
            d.completedAt = g.t;
            g.win();
          } else {
            g.say('已经存进影片，再等下一个动作。', 'ok', 1.35);
          }
        } else if (!filmed.mixed) {
          g.say('刚才松得早了，把动作拍完整。', 'no', 2.0);
        }
      }
      d.pressed = pressed;
    },
    draw
  });
})();
