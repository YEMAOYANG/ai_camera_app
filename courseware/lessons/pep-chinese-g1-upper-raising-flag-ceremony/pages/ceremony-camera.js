K.ready({title: '升旗小摄影', sub: '拖动取景框，看准以后再按快门'});

const WORLD = {x: 45, y: 129, w: 768, h: 432};
const FLAG = {x: 181, w: 162, h: 108, low: 342, high: 168};
const VIEW = {w: 384, h: 258};
const PEOPLE = {x: 580, y: 407};
const LEVELS = [
  {name: '先拍低处，再拍高处', shots: ['low', 'high']},
  {name: '拍到飘扬的两种样子', shots: ['curl', 'lift']},
  {name: '从旗面看到观礼的人', shots: ['high', 'lift', 'people']}
];
const SHOTS = {
  low: {title: '拍低处的旗', hint: '先让旗进取景框。', detail: '把框移到旗杆低处。', success: '拍到了低处的旗。'},
  high: {title: '拍升到高处的旗', hint: '再看旗的位置。', detail: '等旗到了高处再拍。', success: '旗从低处升高了。'},
  curl: {title: '拍旗尾下弯', hint: '等等，看看旗尾。', detail: '旗尾向下弯时再拍。', success: '拍到了旗尾下弯。'},
  lift: {title: '拍旗尾扬起', hint: '再看看旗尾在动。', detail: '旗尾向上扬时再拍。', success: '拍到了旗尾扬起。'},
  people: {title: '拍站直观礼的同学', hint: '看看同学在哪里。', detail: '把框移到同学身上。', success: '同学面朝旗站直。'}
};
const colors = {ink: '#244552', teal: '#17766E', muted: '#79A49D', paper: '#FCF9F0', sky: '#DDEEF0'};
const art = {};
for (const [name, src] of Object.entries({
  school: '__IMG:schoolyard-base__', schoolBackup: '__IMG:ceremony-school__', flag: '__IMG:flag-close__'
})) {
  const bitmap = new Image();
  bitmap.src = src;
  art[name] = bitmap;
}
const shutter = K.$('#camera-shutter');
const restart = K.$('#camera-restart');
const loaded = image => image.complete && image.naturalWidth > 0;
const clamp = (x, min, max) => Math.max(min, Math.min(max, x));
const viewBounds = {
  x: [WORLD.x + VIEW.w / 2, WORLD.x + WORLD.w - VIEW.w / 2],
  y: [WORLD.y + VIEW.h / 2, WORLD.y + WORLD.h - VIEW.h / 2]
};

function currentShot(g) {
  const sequence = LEVELS[g.level].shots;
  return sequence[Math.min(g.data.photos.length, sequence.length - 1)];
}

function flagMotion(g) {
  if (g.data.lastMotion) return g.data.lastMotion;
  const shot = currentShot(g);
  const height = shot === 'low' ? FLAG.low : shot === 'high'
    ? FLAG.low + (FLAG.high - FLAG.low) * clamp(g.data.age / 3.8, 0, 1) : FLAG.high;
  const wave = shot === 'curl' || shot === 'lift' || shot === 'people' ? Math.sin(g.data.age * 1.8) : 0;
  return {y: height, wave};
}

function focus(g, motion) {
  return currentShot(g) === 'people' ? PEOPLE : {x: FLAG.x + FLAG.w / 2, y: motion.y + FLAG.h / 2};
}

function isInFrame(g, shot, target) {
  const lens = g.data.lens;
  const margin = shot === 'people' ? {x: 23, y: 17} : {x: 55, y: 43};
  return Math.abs(lens.x - target.x) <= margin.x && Math.abs(lens.y - target.y) <= margin.y;
}

function canTakePhoto(g, motion, target) {
  const shot = currentShot(g);
  if (!isInFrame(g, shot, target)) return false;
  if (shot === 'low') return motion.y >= FLAG.low - 1;
  if (shot === 'high') return motion.y <= FLAG.high + 5;
  if (shot === 'curl') return motion.wave >= 0.52;
  if (shot === 'lift') return motion.wave <= -0.52;
  return loaded(art.school) || loaded(art.schoolBackup);
}

function roundBox(c, x, y, w, h, color, radius = 18) {
  K.draw.rr(c, x, y, w, h, radius);
  c.fillStyle = color;
  c.fill();
}

function drawFlag(c, x, y, w, wave) {
  const h = w * 2 / 3;
  if (loaded(art.flag) && Math.abs(wave) < 0.001) {
    c.drawImage(art.flag, x, y, w, h);
    return;
  }
  const warp = fraction => Math.sin(fraction * Math.PI / 2) * wave * w * 0.085;
  if (loaded(art.flag)) {
    const count = 48;
    const col = art.flag.naturalWidth / count;
    for (let i = 0; i < count; i++) {
      c.drawImage(art.flag, i * col, 0, col, art.flag.naturalHeight,
        x + i * w / count, y + warp(i / count), w / count + 0.35, h);
    }
    return;
  }
  const point = (a, b) => [x + a * w / 30, y + b * w / 30 + warp(a / 30)];
  const outline = Array.from({length: 31}, (_, i) => point(i, 0))
    .concat(Array.from({length: 31}, (_, i) => point(30 - i, 20)));
  const fill = (vertices, color) => {
    c.beginPath();
    for (const [px, py] of vertices) c.lineTo(px, py);
    c.closePath();
    c.fillStyle = color;
    c.fill();
  };
  fill(outline, '#EE1C25');
  for (const [cx, cy, r] of [[5,5,3],[10,2,1],[12,4,1],[12,7,1],[10,9,1]]) {
    const angle = r === 3 ? -Math.PI / 2 : Math.atan2(5 - cy, 5 - cx);
    const radius = i => i % 2 ? r * Math.sin(Math.PI / 10) / Math.sin(3 * Math.PI / 10) : r;
    fill(Array.from({length: 10}, (_, i) =>
      point(cx + radius(i) * Math.cos(angle + i * Math.PI / 5), cy + radius(i) * Math.sin(angle + i * Math.PI / 5))), '#FFFF00');
  }
}

function cover(c, image, x, y, w, h) {
  const srcRatio = image.naturalWidth / image.naturalHeight;
  const ratio = w / h;
  const sw = Math.min(image.naturalWidth, image.naturalHeight * ratio);
  const sh = Math.min(image.naturalHeight, image.naturalWidth / ratio);
  c.drawImage(image, srcRatio > ratio ? (image.naturalWidth - sw) / 2 : 0,
    srcRatio < ratio ? (image.naturalHeight - sh) / 2 : 0, sw, sh, x, y, w, h);
}

function drawWorld(c, motion) {
  const {x, y, w, h} = WORLD;
  c.save();
  K.draw.rr(c, x, y, w, h, 20);
  c.clip();
  c.fillStyle = colors.sky;
  c.fillRect(x, y, w, h);
  if (loaded(art.school)) {
    cover(c, art.school, x, y, w, h);
  } else if (loaded(art.schoolBackup)) {
    // The right half of the backup retains the children and excludes its flag.
    const img = art.schoolBackup;
    c.drawImage(img, img.naturalWidth * 0.48, 0, img.naturalWidth * 0.52,
      img.naturalHeight, x + w * 0.48, y, w * 0.52, h);
  }
  if (!loaded(art.school)) {
    c.fillStyle = '#E8E5CF';
    c.fillRect(x, y + h - 52, w * (loaded(art.schoolBackup) ? 0.48 : 1), 52);
  }
  if (!loaded(art.school)) {
    c.fillStyle = '#53717A';
    c.fillRect(FLAG.x - 8, 155, 8, 379);
    roundBox(c, FLAG.x - 29, 529, 54, 18, '#87948D', 4);
    c.fillStyle = '#9AB0AE';
    K.draw.circle(c, FLAG.x - 4, 155, 8);
  }
  drawFlag(c, FLAG.x, motion.y, FLAG.w, motion.wave);
  c.restore();
}

function takePhoto(g, motion) {
  const picture = document.createElement('canvas');
  picture.width = VIEW.w;
  picture.height = VIEW.h;
  const c = picture.getContext('2d');
  c.translate(VIEW.w / 2 - g.data.lens.x, VIEW.h / 2 - g.data.lens.y);
  drawWorld(c, motion);
  return picture;
}

function queueShutter(g) {
  g.taps.push({photo: true});
}

function update(g, dt) {
  const d = g.data;
  shutter.hidden = restart.hidden = false;
  if (d.complete) return;
  d.age += dt;
  if (d.cooldown > 0) d.cooldown -= dt;
  if (g.taps.some(t => !t.photo && !t.key && t.x > WORLD.x && t.x < WORLD.x + WORLD.w
     && t.y > WORLD.y && t.y < WORLD.y + WORLD.h)) d.dragging = true;
  if (!g.pointer.down) d.dragging = false;
  const pointer = g.pointer;
  const move = (axis, candidate, minimum, maximum) => {
    const target = clamp(candidate, minimum, maximum);
    const maxStep = 490 * dt;
    d.lens[axis] += clamp(target - d.lens[axis], -maxStep, maxStep);
  };
  const keyX = Number(g.keys.right || false) - Number(g.keys.left || false);
  const keyY = Number(g.keys.down || false) - Number(g.keys.up || false);
  if (d.dragging || keyX || keyY) {
    move('x', d.dragging ? pointer.x : d.lens.x + keyX * 90, ...viewBounds.x);
    move('y', d.dragging ? pointer.y : d.lens.y + keyY * 90, ...viewBounds.y);
  }
  if (!g.taps.some(t => t.photo || t.key) || d.cooldown > 0) return;
  d.cooldown = 0.35;
  const mode = currentShot(g);
  const shot = SHOTS[mode];
  const motion = flagMotion(g);
  if (!canTakePhoto(g, motion, focus(g, motion))) {
    g.say(d.hinted.has(mode) ? shot.detail : shot.hint, 'no');
    d.hinted.add(mode);
    return;
  }
  d.photos.push(takePhoto(g, motion));
  d.flash = 0.24;
  g.say(shot.success, 'ok');
  K.sfx.ok();
  if (d.photos.length === LEVELS[g.level].shots.length) {
    d.complete = true;
    d.lastMotion = motion;
    g.after(0.95, () => g.win());
  } else {
    d.age = 0;
  }
}

function autopilot(g) {
  const d = g.data;
  if (d.complete) return;
  const motion = flagMotion(g);
  const target = focus(g, motion);
  const x = clamp(target.x, ...viewBounds.x);
  const y = clamp(target.y, ...viewBounds.y);
  const close = Math.abs(d.lens.x - x) < 12 && Math.abs(d.lens.y - y) < 12;
  const take = close && canTakePhoto(g, motion, target) && d.cooldown <= 0;
  if (take) {
    g.pointer.down = false;
    queueShutter(g);
    return;
  }
  if (!g.pointer.down) g.taps.push({x, y});
  g.pointer.x = x;
  g.pointer.y = y;
  g.pointer.down = true;
}

function drawTarget(c, shot) {
  const {x, y} = {x: 365, y: 29};
  roundBox(c, x, y, 126, 64, colors.sky, 9);
  if (shot === 'people') {
    const img = loaded(art.school) ? art.school : art.schoolBackup;
    if (loaded(img)) {
      const sw = img.naturalWidth * 0.47, sh = img.naturalHeight * 0.57;
      const scale = Math.min(118 / sw, 58 / sh);
      c.drawImage(img, img.naturalWidth * 0.47, img.naturalHeight * 0.35, sw, sh,
        x + (126 - sw * scale) / 2, y + (64 - sh * scale) / 2, sw * scale, sh * scale);
    }
    return;
  }
  c.fillStyle = colors.muted;
  c.fillRect(x + 26, y + 4, 3, 53);
  const low = shot === 'low';
  const wave = shot === 'lift' ? -1 : shot === 'curl' ? 1 : 0;
  drawFlag(c, x + 29, y + (low ? 28 : 6), wave ? 68 : 42, wave);
}

function drawLens(c, lens, ready) {
  const {x, y} = lens;
  const l = x - VIEW.w / 2, t = y - VIEW.h / 2, r = x + VIEW.w / 2, b = y + VIEW.h / 2;
  c.strokeStyle = ready ? '#8CF1AB' : '#FFEEBA';
  c.lineWidth = 8;
  c.lineJoin = 'round';
  c.shadowColor = '#183C4C';
  c.shadowBlur = 5;
  c.beginPath();
  for (const [cornerX, cornerY, dx, dy] of [[l,t,1,1],[r,t,-1,1],[l,b,1,-1],[r,b,-1,-1]]) {
    c.moveTo(cornerX + dx * 43, cornerY);
    c.lineTo(cornerX, cornerY);
    c.lineTo(cornerX, cornerY + dy * 43);
  }
  c.stroke();
  c.shadowBlur = 0;
  c.fillStyle = '#FFFDF0';
  K.draw.circle(c, x, y, 5);
}

function draw(g, c) {
  c.fillStyle = '#E6F0E9';
  c.fillRect(0, 0, 1280, 720);
  if (!g.data.lens) return;
  const d = g.data;
  const shot = currentShot(g);
  const motion = flagMotion(g);
  roundBox(c, 26, 26, 166, 65, colors.paper, 30);
  LEVELS.forEach((_, i) => {
    c.fillStyle = i <= g.level ? colors.teal : '#BFD8D1';
    K.draw.circle(c, 63 + i * 46, 59, i === g.level ? 12 : 9);
  });
  roundBox(c, 310, 17, 660, 89, colors.paper);
  drawTarget(c, shot);
  K.draw.text(c, SHOTS[shot].title, 705, 63, 35, colors.ink);
  roundBox(c, 850, 135, 373, 426, colors.paper, 28);
  K.draw.text(c, '快门', 1037, 487, 30, colors.ink);
  drawWorld(c, motion);
  drawLens(c, d.lens, isInFrame(g, shot, focus(g, motion)));
  if (d.flash > 0) {
    c.fillStyle = 'rgba(255,255,255,0.28)';
    c.fillRect(d.lens.x - VIEW.w / 2, d.lens.y - VIEW.h / 2, VIEW.w, VIEW.h);
    d.flash -= g.dt;
  }
  K.draw.text(c, '我的照片', 915, 626, 31, colors.ink, {align: 'left'});
  LEVELS[g.level].shots.forEach((_, i) => {
    const x = 185 + i * 198;
    roundBox(c, x, 584, 174, 121, '#CFDFD9', 12);
    if (d.photos[i]) c.drawImage(d.photos[i], x + 8, 589, 111 * VIEW.w / VIEW.h, 111);
  });
}

K.game({
  levels: LEVELS.length,
  finishMark: '★★★',
  bannerTime: 0.55,
  winPause: 1.35,
  starsFor: () => 3,
  doneText: '看见旗的变化，也看见认真观礼。',
  levelName: i => LEVELS[i].name,
  winText: i => i === 0 ? '照片记录了先低后高。' : '两张照片记录了旗面的变化。',
  bubbleAt: () => ({x: 1037, y: 242}),
  setup(g) {
    shutter.addEventListener('click', () => queueShutter(g));
    restart.addEventListener('click', () => g.start(g.level));
    K.startPictureFallback = () => {
      const canvas = K.el('canvas', 'pic');
      canvas.width = 576;
      canvas.height = 324;
      const c = canvas.getContext('2d');
      c.scale(576 / WORLD.w, 324 / WORLD.h);
      c.translate(-WORLD.x, -WORLD.y);
      drawWorld(c, {y: FLAG.high, wave: 0});
      return canvas;
    };
    g.follow('#game-goal', () => ({x: 310, y: 17, w: 660, h: 89}));
    g.follow('#game-player', () => g.data.lens && ({x: g.data.lens.x - VIEW.w / 2,
      y: g.data.lens.y - VIEW.h / 2, w: VIEW.w, h: VIEW.h}));
    g.follow('#game-target', () => {
      if (!g.data.lens) return null;
      const target = focus(g, flagMotion(g));
      const people = currentShot(g) === 'people';
      return {x: target.x - (people ? 168 : FLAG.w / 2), y: target.y - (people ? 111 : FLAG.h / 2),
        w: people ? 336 : FLAG.w, h: people ? 222 : FLAG.h};
    });
  },
  reset(g) {
    g.pointer.down = false;
    g.data = {lens: {x: 390, y: 342}, age: 0, photos: [], hinted: new Set(),
      dragging: false, cooldown: 0, flash: 0, complete: false};
  },
  idle() { shutter.hidden = restart.hidden = true; },
  autopilot, update, draw
});
