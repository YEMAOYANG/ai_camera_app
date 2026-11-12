K.ready({
  title: '同高落脚实验',
  sub: '按住圆柄，脚抬到横线就松手。看看两边留下的波纹。',
  img: '__IMG:table-soft__'
});

const colors = {background: '#e7f2ec', paper: '#fffdf6', line: '#a6c4b8', ink: '#24463f', muted: '#597970',
  blue: '#167c9c', bluePale: '#d1e7eb', light: '#b9dbd8', green: '#28775d', warm: '#bd6539',
  gold: '#eec16e', brown: '#b68154'};
const lanes = [
  {x: 47, picture: '__IMG:table-bare__', text: '裸桌', shade: '#f5e4ca', tone: colors.warm},
  {x: 723, picture: '__IMG:table-soft__', text: '加海绵', shade: '#f4e9c6', tone: colors.green}
];
const handle = {x: 559, y: 511, w: 162, h: 134};
const laneWidth = 510, floor = 437, modelBase = floor - 35, range = 199;
const targetY = height => modelBase - range * height;
const geometry = [{line: 0.50, window: 0.216, rate: 0.39}, {line: 0.58, window: 0.155, rate: 0.48}];
const art = lanes.map(lane => {
  const image = new Image();
  image.src = lane.picture;
  return image;
});
let context;

function knock(soft) {
  try {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) return;
    context ||= new Audio();
    if (context.state === 'suspended') context.resume().catch(() => {});
    const at = context.currentTime;
    const oscillator = context.createOscillator(), gain = context.createGain();
    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(166, at);
    oscillator.frequency.exponentialRampToValueAtTime(82, at + 0.16);
    gain.gain.setValueAtTime(soft ? 0.036 : 0.145, at);
    gain.gain.exponentialRampToValueAtTime(0.001, at + 0.18);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(at);
    oscillator.stop(at + 0.19);
  } catch {
    // The graph remains visible when sound is unavailable.
  }
}

function rounded(c, x, y, w, h, color, stroke, radius = 20) {
  K.draw.rr(c, x, y, w, h, radius);
  if (color) { c.fillStyle = color; c.fill(); }
  if (stroke) { c.lineWidth = 4; c.strokeStyle = stroke; c.stroke(); }
}

function inHandle(tap) {
  return !tap.key && tap.x >= handle.x && tap.x <= handle.x + handle.w &&
    tap.y >= handle.y && tap.y <= handle.y + handle.h;
}

function heightLine(state) {
  return state.level === 1 && state.results[0] ? state.results[0].height : state.config.line;
}

function active(state, i) {
  return state.level === 0 || i === state.results.filter(Boolean).length;
}

function beginDrop(state) {
  const height = heightLine(state);
  state.drop = {height, clock: 0, lanes: state.level === 0 ? [0, 1] : [state.results[0] ? 1 : 0]};
}

function release(g, state) {
  if (Math.abs(state.height - heightLine(state)) <= state.config.window) {
    beginDrop(state);
  } else {
    g.miss();
    state.misses++;
    state.hintUntil = state.clock + 1.6;
    g.say(state.misses === 1 ? '两次要从同一条线放脚。' : '看圆柄亮起来，再松开。', 'no', 1.8);
  }
  state.height = 0;
  state.charge = null;
}

function stepDrop(g, state, dt) {
  const drop = state.drop;
  drop.clock += dt;
  for (const [index, i] of drop.lanes.entries()) {
    if (state.results[i] || drop.clock < 0.36 + index * 0.26) continue;
    state.results[i] = {height: drop.height, amplitude: i === 0 ? 1 : 0.31};
    knock(i === 1);
    g.burst(lanes[i].x + 373, floor, {n: i === 0 ? 9 : 4, color: lanes[i].tone, size: 5});
  }
  if (drop.lanes.every(i => state.results[i])) {
    state.drop = null;
    if (state.results.every(Boolean)) {
      state.winAt = state.clock + 1.3;
      g.say('落得一样高，海绵这边的波纹更小。', 'ok', 2.1);
    } else {
      g.say('第一条线留下了。照着它再试另一边。', 'ok', 1.9);
    }
  }
}

function drawChevron(c, x, y, color) {
  c.beginPath(); c.strokeStyle = color; c.lineWidth = 5; c.lineCap = 'round'; c.lineJoin = 'round';
  c.moveTo(x - 14, y + 6); c.lineTo(x, y - 6); c.lineTo(x + 14, y + 6); c.stroke();
}

function drawPicture(c, i, x, y, size) {
  const image = art[i];
  if (!image.naturalWidth) {
    rounded(c, x, y, size, size, lanes[i].shade, colors.line, 14);
    rounded(c, x + 24, y + 88, size - 48, 28, colors.brown, null, 6);
    if (i) rounded(c, x + 45, y + 70, size - 90, 24, colors.gold, null, 6);
    return;
  }
  c.save(); K.draw.rr(c, x, y, size, size, 13); c.clip();
  const scale = Math.min(size / image.naturalWidth, size / image.naturalHeight);
  const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
  c.drawImage(image, x + (size - width) / 2, y + (size - height) / 2, width, height);
  c.restore();
}

function drawFloor(c, i, x) {
  const boardY = floor + (i === 1 ? 12 : 0);
  rounded(c, x - 104, boardY, 208, 22, '#b78053', '#94633f', 7);
  if (i === 1) {
    rounded(c, x - 91, floor - 2, 182, 16, colors.gold, '#c29945', 6);
    c.fillStyle = '#bc964c';
    for (let j = 0; j < 9; j++) K.draw.circle(c, x - 73 + j * 18, floor + 5 + j % 2 * 2, 2);
  }
}

function drawProbe(c, x, center, on) {
  rounded(c, x - 8, center - 31, 16, 48, '#9db6ba', '#63868c', 5);
  rounded(c, x - 43, center + 7, 86, 26, on ? colors.blue : '#6b9291', '#345c62', 8);
  rounded(c, x - 23, center + 11, 46, 6, '#f5f9f0', null, 3);
}

function drawDropLine(c, state, i, x) {
  const aim = heightLine(state), y = targetY(aim), selected = active(state, i);
  const half = range * state.config.window;
  if (selected && !state.results[i]) {
    const band = state.clock < state.hintUntil ? '#f2c16b60' : '#a7d9d949';
    rounded(c, x - 115, y - half, 230, half * 2, band, null, 8);
  }
  c.beginPath(); c.moveTo(x - 121, y); c.lineTo(x + 121, y);
  c.setLineDash(state.results[i] ? [] : [11, 7]);
  c.lineWidth = 4; c.strokeStyle = state.results[i] ? colors.green : colors.blue; c.stroke(); c.setLineDash([]);
}

function probeY(state, i) {
  if (state.results[i]) return floor - 33;
  if (state.drop?.lanes.includes(i)) {
    const drop = state.drop;
    const t = Math.max(0, Math.min(1, (drop.clock - drop.lanes.indexOf(i) * 0.26) / 0.36));
    const start = targetY(drop.height);
    return start + (floor - 33 - start) * t ** 2;
  }
  return targetY(active(state, i) ? state.height : 0);
}

function drawWave(c, x, y, width, result, color) {
  c.beginPath(); c.moveTo(x, y); c.lineTo(x + width, y);
  c.strokeStyle = colors.line; c.lineWidth = 2.5; c.stroke();
  if (!result) return;
  c.beginPath();
  for (let t = 0; t <= 96; t++) {
    const phase = t / 96;
    const height = phase < 0.14 ? 0 : result.amplitude * 51 * Math.exp(-4.6 * (phase - 0.14)) * Math.sin((phase - 0.14) * 42);
    if (t === 0) c.moveTo(x, y); else c.lineTo(x + width * phase, y - height);
  }
  c.strokeStyle = color; c.lineWidth = 5; c.lineJoin = 'round'; c.lineCap = 'round'; c.stroke();
}

function drawLane(c, state, i) {
  const lane = lanes[i], x = lane.x;
  const recorded = state.results[i];
  const selected = active(state, i) && !recorded;
  rounded(c, x, 152, laneWidth, 329, colors.paper, selected ? colors.blue : colors.line, 22);
  rounded(c, x + 11, 167, 189, 292, lane.shade, null, 15);
  drawPicture(c, i, x + 21, 191, 169);
  K.draw.text(c, lane.text, x + 105, 404, 31, colors.ink);
  const probeX = x + 365;
  rounded(c, probeX - 7, 189, 14, 239, colors.light, null, 6);
  drawDropLine(c, state, i, probeX);
  drawFloor(c, i, probeX);
  drawProbe(c, probeX, probeY(state, i), selected || Boolean(state.drop?.lanes.includes(i)));

  rounded(c, x, 502, laneWidth, 166, recorded ? '#fcfcf1' : '#f4f7ef', recorded ? lane.tone : colors.line, 21);
  if (recorded) drawPicture(c, i, x + 17, 524, 120);
  const label = recorded ? (i === 0 ? '波纹较大' : '波纹较小') : '结果留在这里';
  K.draw.text(c, label, x + 316, 535, 25, recorded ? lane.tone : colors.muted);
  drawWave(c, x + 166, 614, 305, recorded, lane.tone);
}

function drawHandle(c, state) {
  const x = handle.x + handle.w / 2, y = handle.y + handle.h / 2;
  const near = state.charge && Math.abs(state.height - heightLine(state)) <= state.config.window;
  const idle = !state.drop && state.winAt === null;
  const glow = !state.charge && !state.drop && !state.results.some(Boolean) ? 2 + 2 * Math.sin(state.clock * 6) : 0;
  c.fillStyle = colors.bluePale; K.draw.circle(c, x, y, 65 + glow);
  c.fillStyle = near ? colors.green : (idle ? colors.blue : '#71928b'); K.draw.circle(c, x, y, 52);
  if (state.charge) {
    c.beginPath(); c.arc(x, y, 56, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * state.height);
    c.strokeStyle = near ? '#f6d476' : '#fff7d8'; c.lineWidth = 6; c.stroke();
  }
  if (near) {
    c.fillStyle = '#fff8dc'; K.draw.circle(c, x, y, 12);
  } else {
    drawChevron(c, x, y - 12, '#fff8dc');
    drawChevron(c, x, y + 10, '#fff8dc');
  }
  K.draw.text(c, near ? '松开' : '按住', x, 674, 26, colors.ink);
}

function drawReference(c, state) {
  const x = 640, y = targetY(heightLine(state));
  const done = state.results.every(Boolean);
  const recorded = Boolean(state.results[0]);
  rounded(c, x - 8, 186, 16, 233, colors.bluePale, null, 7);
  const position = targetY(state.drop?.height ?? state.height);
  if (!done && (state.charge || state.drop)) {
    c.fillStyle = colors.blue;
    K.draw.circle(c, x, position, 12);
  }
  c.beginPath();
  c.moveTo(x - 49, y); c.lineTo(x + 49, y);
  c.moveTo(x - 40, y - 8); c.lineTo(x - 49, y); c.lineTo(x - 40, y + 8);
  c.moveTo(x + 40, y - 8); c.lineTo(x + 49, y); c.lineTo(x + 40, y + 8);
  c.lineWidth = 4; c.lineJoin = 'round'; c.lineCap = 'round';
  c.strokeStyle = recorded ? colors.green : colors.blue; c.stroke();
}

K.game({
  levels: 2,
  winPause: 2.4,
  starsFor: () => 3,
  winText: () => '两种台面的波纹都留下了。',
  doneTitle: '两边从同一高度落脚',
  doneText: '试验记录就在两边。',
  finishMark: '★★★',
  setup(g) {
    g.follow('#trial-surfaces', () => ({x: 55, y: 164, w: 1170, h: 305}));
    g.follow('#trial-control', () => handle);
    g.follow('#trial-line', () => {
      if (!g.data.config) return null;
      const y = targetY(heightLine(g.data));
      return {x: 282, y: y - 13, w: 920, h: 26};
    });
    g.follow('#trial-results', () => ({x: 46, y: 503, w: 1188, h: 161}));
    K.startPictureFallback = () => {
      const image = document.createElement('img');
      image.className = 'pic';
      image.alt = '指尖碰桌面';
      image.src = '__IMG:table-bare__';
      return image;
    };
  },
  reset(g, level) {
    g.pointer.down = false;
    g.data = {level, config: geometry[level], clock: 0, results: [null, null], height: 0,
      charge: null, drop: null, winAt: null, misses: 0, hintUntil: 0, nextAuto: 2.0};
  },
  autopilot(g) {
    const s = g.data, {pointer} = g;
    if (s.drop || s.winAt !== null || s.clock < s.nextAuto) return;
    if (s.charge && s.height >= heightLine(s)) {
      pointer.down = false;
      s.nextAuto = s.clock + 1.6;
    } else if (!s.charge) {
      Object.assign(pointer, {x: handle.x + handle.w / 2, y: handle.y + handle.h / 2, down: true});
      g.taps.push({x: pointer.x, y: pointer.y});
    }
  },
  update(g, dt) {
    const s = g.data;
    s.clock += dt;
    if (s.winAt !== null) {
      if (s.clock >= s.winAt) g.win();
      return;
    }
    if (s.drop) { stepDrop(g, s, dt); return; }
    if (!s.charge) {
      if (g.pointer.down && g.taps.some(inHandle)) s.charge = 'pointer';
      else if (g.keys.jump && g.taps.some(tap => tap.key)) s.charge = 'keyboard';
    }
    if (s.charge) {
      const held = s.charge === 'pointer' ? g.pointer.down : g.keys.jump;
      if (held) s.height = Math.min(1, s.height + s.config.rate * dt);
      else release(g, s);
    }
  },
  draw(g, c) {
    const s = g.data;
    c.fillStyle = colors.background; c.fillRect(0, 0, 1280, 720);
    if (!s.config) return;
    rounded(c, 46, 13, 1188, 72, colors.paper, colors.line, 17);
    const prompt = g.level === 0 ? '两只脚一起试' : '用第一次的留线，再试另一边';
    K.draw.text(c, prompt, 88, 49, 34, colors.ink, {align: 'left'});
    for (let i = 0; i < 2; i++) {
      c.fillStyle = i <= g.level ? colors.green : colors.line;
      K.draw.circle(c, 1143 + i * 46, 49, 12);
    }
    for (let i = 0; i < 2; i++) drawLane(c, s, i);
    drawReference(c, s);
    drawHandle(c, s);
  },
  bubbleAt: () => ({x: 640, y: 110})
});
