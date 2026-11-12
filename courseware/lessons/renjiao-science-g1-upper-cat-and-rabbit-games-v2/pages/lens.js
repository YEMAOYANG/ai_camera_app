K.ready({
  title: '双窗找证据',
  sub: '左右滑动两个蓝框，把猫和兔的同一个部位放在一起看。',
  img: '__IMG:station__'
});

const sheets = [
  {goal: '__IMG:rabbit-brown__', goalCrop: [250, 2, 264, 192], pictures: ['__IMG:cat-gray__', '__IMG:rabbit-white__'],
    flip: [false, false], targets: [246, 418], start: [520, 687], height: 120,
    prompt: '两扇窗都找耳朵', result: '这两张图里，猫耳短尖，兔耳较长。'},
  {goal: '__IMG:rabbit-white__', goalCrop: [665, 318, 208, 151], pictures: ['__IMG:cat-orange__', '__IMG:rabbit-brown__'],
    flip: [false, true], targets: [818, 226], start: [525, 536], height: 355,
    prompt: '先看朝向，再找两条尾巴', result: '这两张图里，猫尾弯长，兔尾像小团。'}
];
const photos = [{x: 46, y: 109, w: 564, h: 317}, {x: 670, y: 109, w: 564, h: 317}];
const colors = {bg: '#e4f1eb', paper: '#fffdf7', ink: '#234740', muted: '#5a7971',
  blue: '#087894', pale: '#b9dce3', gold: '#f6c86f', green: '#28785e', line: '#b5cdc0'};
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const width = 352, height = 224, tolerance = 91;
const art = new Map();
function load(url) {
  if (!art.has(url)) {
    const image = new Image();
    image.onerror = () => { image.unavailable = true; };
    image.src = url;
    art.set(url, image);
  }
  return art.get(url);
}
for (const sheet of sheets) for (const url of [sheet.goal, ...sheet.pictures]) load(url);
function sheetPicture(sheet, index) {
  const url = sheet.pictures[index];
  return load(url).unavailable ? sheets.find(other => other !== sheet).pictures[index] : url;
}

function box(c, x, y, w, h, fill, stroke, radius = 20) {
  K.draw.rr(c, x, y, w, h, radius);
  if (fill) { c.fillStyle = fill; c.fill(); }
  if (stroke) { c.strokeStyle = stroke; c.lineWidth = 4; c.stroke(); }
}

function paint(c, url, flip, source, dest) {
  const image = load(url);
  if (!image.naturalWidth) {
    box(c, dest.x, dest.y, dest.w, dest.h, '#f5eddd', colors.line, 12);
    K.draw.text(c, '图片加载中', dest.x + dest.w / 2, dest.y + dest.h / 2, 24, colors.muted);
    return;
  }
  const [x, y, w, h] = source;
  const scaleX = image.naturalWidth / 1024, scaleY = image.naturalHeight / 576;
  const sx = (flip ? 1024 - x - w : x) * scaleX;
  c.save();
  K.draw.rr(c, dest.x, dest.y, dest.w, dest.h, 12);
  c.clip();
  if (flip) { c.translate(2 * dest.x + dest.w, 0); c.scale(-1, 1); }
  c.drawImage(image, sx, y * scaleY, w * scaleX, h * scaleY, dest.x, dest.y, dest.w, dest.h);
  c.restore();
}

function windowX(photo, pos) { return photo.x + photo.w * pos / 1024; }
function windowY(photo, sheet) { return photo.y + photo.h * sheet.height / 576; }
function handle(photo, sheet, pos) {
  const x = windowX(photo, pos), y = windowY(photo, sheet) + photo.h * height / 1152 - 5;
  return {x: x - 60, y: y - 49, w: 120, h: 98};
}
function grabArea(photo, sheet, pos) {
  const x = windowX(photo, pos), y = windowY(photo, sheet);
  const span = photo.w * width / 1024, deep = photo.h * height / 576;
  return {x: x - span / 2, y: y - deep / 2, w: span, h: deep + 43};
}
function inside(tap, r) {
  return !tap.key && tap.x >= r.x && tap.x <= r.x + r.w && tap.y >= r.y && tap.y <= r.y + r.h;
}
function inRange(sheet, index, pos) { return Math.abs(pos - sheet.targets[index]) <= tolerance; }

function crop(c, sheet, index, pos, dest) {
  paint(c, sheetPicture(sheet, index), sheet.flip[index], [pos - width / 2, sheet.height - height / 2, width, height], dest);
}

function arrows(c, x, y, color, stretch = 1) {
  c.strokeStyle = color; c.lineWidth = 5; c.lineJoin = 'round'; c.lineCap = 'round';
  c.beginPath();
  c.moveTo(x - 36 * stretch, y); c.lineTo(x + 36 * stretch, y);
  c.moveTo(x - 24 * stretch, y - 9); c.lineTo(x - 36 * stretch, y); c.lineTo(x - 24 * stretch, y + 9);
  c.moveTo(x + 24 * stretch, y - 9); c.lineTo(x + 36 * stretch, y); c.lineTo(x + 24 * stretch, y + 9);
  c.stroke();
}

function drawSheet(c, state, i) {
  const {sheet, positions, locked, time} = state;
  const photo = photos[i];
  box(c, photo.x - 5, photo.y - 5, photo.w + 10, photo.h + 10, colors.paper, colors.line);
  paint(c, sheetPicture(sheet, i), sheet.flip[i], [0, 0, 1024, 576], photo);
  const pos = positions[i];
  const x = windowX(photo, pos), y = windowY(photo, sheet);
  const span = photo.w * width / 1024, deep = photo.h * height / 576;
  const tint = locked ? colors.green : colors.blue;
  box(c, x - span / 2, y - deep / 2, span, deep, locked ? '#45ac7417' : '#7ee1f41d', tint, 14);
  const r = handle(photo, sheet, pos);
  const drift = state.grab === null && !locked && !state.moved[i] ? 1 + 0.09 * Math.sin(time * 6.5) : 1;
  box(c, r.x + 3, r.y + 25, r.w - 6, r.h - 50, tint, '#fffdf7', 25);
  arrows(c, x, r.y + 49, '#fff', drift);
}

function drawRecords(c, state) {
  const {sheet, locked, positions, earlier} = state;
  box(c, 43, 460, 1194, 224, colors.paper, locked ? colors.green : colors.line, 25);
  K.draw.text(c, locked ? '观察记录' : '两个放大窗', 126, 503, 25, colors.ink);
  K.draw.text(c, locked ? '同一部位' : '同样放大', 126, 539, 21, colors.muted);
  for (let i = 0; i < 2; i++) {
    const dest = {x: 225 + i * 466, y: 477, w: 301, h: 191};
    crop(c, sheet, i, positions[i], dest);
    const border = locked ? colors.green : (state.time < state.hintUntil ? colors.gold : colors.pale);
    box(c, dest.x, dest.y, dest.w, dest.h, null, border, 12);
  }
  c.strokeStyle = colors.line; c.lineWidth = 4; c.setLineDash([8, 8]);
  c.beginPath(); c.moveTo(546, 569); c.lineTo(672, 569); c.stroke(); c.setLineDash([]);
  if (earlier) {
    box(c, 1014, 483, 199, 181, '#ecf6ed', colors.line, 14);
    K.draw.text(c, '上次的耳朵', 1112, 514, 22, colors.ink);
    for (let i = 0; i < 2; i++) crop(c, sheets[0], i, earlier[i], {x: 1024 + i * 92, y: 547, w: 84, h: 54});
  }
}

function hint(g, state) {
  g.miss();
  state.misses++;
  state.hintUntil = state.time + 1.9;
  const text = state.misses === 1 ? '两个窗要看同一个部位。' :
    (g.level === 0 ? '先找头朝哪边，再往头顶看。' : '先找头，再看身体的另一端。');
  g.say(text, 'no', 2.15);
}

K.game({
  levels: sheets.length,
  winPause: 2.4,
  starsFor: () => 3,
  doneTitle: '耳朵和尾巴都找齐了',
  doneText: '两份局部对照留在记录上。',
  winText: () => '两扇窗都找到耳朵。',
  finishMark: '★★★',
  setup(g) {
    g.follow('#compare-goal', () => ({x: 52, y: 14, w: 1176, h: 75}));
    g.follow('#compare-control', () => ({x: 44, y: 107, w: 1192, h: 320}));
    g.follow('#compare-record', () => ({x: 43, y: 460, w: 1194, h: 224}));
    K.startPictureFallback = () => {
      const image = document.createElement('img');
      image.className = 'pic';
      image.alt = '橘猫';
      image.src = '__IMG:cat-orange__';
      return image;
    };
  },
  reset(g, level) {
    const sheet = sheets[level];
    const earlier = level > 0 ? g.data.earlier || (g.data.locked ? g.data.positions.slice() : null) : null;
    g.pointer.down = false;
    g.data = {sheet, earlier, positions: sheet.start.slice(), moved: [false, false],
      grab: null, from: 0, offset: 0, time: 0, settled: 0, misses: 0, hintUntil: 0, locked: false,
      winAt: null, focus: 0, keyJump: false, autoIndex: 0, autoPhase: 'wait'};
  },
  autopilot(g, dt) {
    const s = g.data, index = s.autoIndex;
    if (index >= photos.length || s.locked || s.time < 1.15) return;
    const photo = photos[index], x = windowX(photo, s.positions[index]);
    const y = handle(photo, s.sheet, s.positions[index]).y + 49;
    if (s.autoPhase === 'wait') {
      Object.assign(g.pointer, {x, y, down: true});
      g.taps.push({x, y});
      s.autoPhase = 'slide';
      return;
    }
    const target = windowX(photo, s.sheet.targets[index]);
    const dx = target - g.pointer.x;
    if (Math.abs(dx) > 2) g.pointer.x += clamp(dx, -240 * dt, 240 * dt);
    else {
      g.pointer.down = false;
      s.autoIndex++;
      s.autoPhase = 'wait';
    }
  },
  update(g, dt) {
    const s = g.data;
    s.time += dt;
    if (s.locked) {
      if (s.time >= s.winAt) g.win();
      return;
    }
    if (!photos.every((_, i) => load(sheetPicture(s.sheet, i)).naturalWidth)) return;
    if (s.grab === null) {
      const index = photos.findIndex((photo, i) => g.taps.some(tap => inside(tap, grabArea(photo, s.sheet, s.positions[i]))));
      if (index !== -1 && g.pointer.down) {
        s.grab = index;
        s.focus = index;
        s.from = s.positions[index];
        s.offset = g.pointer.x - windowX(photos[index], s.from);
      }
    }
    if (s.grab !== null) {
      const index = s.grab, photo = photos[index];
      if (g.pointer.down) {
        s.positions[index] = clamp((g.pointer.x - s.offset - photo.x) / photo.w * 1024, width / 2, 1024 - width / 2);
        if (Math.abs(s.positions[index] - s.from) > 15) s.moved[index] = true;
      } else {
        if (s.moved[index] && !inRange(s.sheet, index, s.positions[index])) hint(g, s);
        s.grab = null;
      }
    } else {
      if (g.keys.jump && !s.keyJump) s.focus = 1 - s.focus;
      const direction = Number(Boolean(g.keys.right)) - Number(Boolean(g.keys.left));
      if (direction) {
        s.positions[s.focus] = clamp(s.positions[s.focus] + direction * dt * 290, width / 2, 1024 - width / 2);
        s.moved[s.focus] = true;
      }
    }
    s.keyJump = g.keys.jump;
    const still = s.grab === null && !g.keys.left && !g.keys.right;
    const aligned = s.positions.every((pos, i) => inRange(s.sheet, i, pos));
    s.settled = still && aligned ? s.settled + dt : 0;
    if (s.settled) {
      for (let i = 0; i < 2; i++) s.positions[i] += (s.sheet.targets[i] - s.positions[i]) * Math.min(1, dt * 9);
    }
    if (s.settled >= 0.55) {
      s.positions = s.sheet.targets.slice();
      s.locked = true;
      s.winAt = s.time + 0.85;
      g.say(s.sheet.result, 'ok', 2.05);
      K.sfx.ok();
      g.sparkle(555, 577, colors.gold);
      g.sparkle(666, 577, colors.gold);
    }
  },
  draw(g, c) {
    const s = g.data;
    c.fillStyle = colors.bg;
    c.fillRect(0, 0, 1280, 720);
    if (!s.sheet) return;
    box(c, 46, 12, 1188, 78, colors.paper, colors.line, 17);
    const goal = load(s.sheet.goal);
    const dest = {x: 62, y: 19, w: 88, h: 64};
    if (goal.naturalWidth) paint(c, s.sheet.goal, false, s.sheet.goalCrop, dest);
    else crop(c, s.sheet, 0, s.sheet.targets[0], dest);
    K.draw.text(c, s.sheet.prompt, 171, 51, 31, colors.ink, {align: 'left'});
    for (let i = 0; i < sheets.length; i++) {
      c.fillStyle = i <= g.level ? colors.green : colors.line;
      K.draw.circle(c, 1143 + i * 46, 51, 12);
    }
    for (let i = 0; i < 2; i++) drawSheet(c, s, i);
    drawRecords(c, s);
  },
  bubbleAt: () => ({x: 640, y: 443})
});
