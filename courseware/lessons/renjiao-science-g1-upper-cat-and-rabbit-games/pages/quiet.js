K.ready({
  title: '轻脚步试验',
  sub: '跟着圆点踩步子，先对照两种声音，再让脚步安静走过去。',
  img: '__IMG:station__'
});

const LEFT = 72, WIDTH = 1136;
const BEAT = {x: 310, y: 34, w: 660, h: 102};
const STEP = {x: 858, y: 588, w: 330, h: 102};
const LANES = [
  {y: 250, image: '__IMG:table-bare__', soft: false},
  {y: 425, image: '__IMG:table-soft__', soft: true}
];
const MARKS = [450, 640, 830, 1020];
const colors = {ink: '#294444', sky: '#e8f4ef', line: '#a9cfc4',
  paper: '#fffdf5', green: '#217b65', pale: '#cdeedf', oak: '#c78b58',
  loud: '#ac562d', soft: '#217b65'};
const art = LANES.map(lane => {
  const image = new Image();
  image.src = lane.image;
  return image;
});
const pad = new Image();
pad.src = '__IMG:pad__';

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
    gain.gain.setValueAtTime(soft ? 0.035 : 0.14, at);
    gain.gain.exponentialRampToValueAtTime(0.001, at + 0.18);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start(at);
    oscillator.stop(at + 0.19);
  } catch {
    // The visible waves carry the same comparison when sound is unavailable.
  }
}

function beat(state) {
  const elapsed = state.clock / state.period;
  return {cycle: Math.floor(elapsed), phase: elapsed % 1};
}

function onBeat(phase) {
  return phase >= 0.28 && phase <= 0.72;
}

function inside(tap, box) {
  return !tap.key && tap.x >= box.x && tap.x <= box.x + box.w &&
    tap.y >= box.y && tap.y <= box.y + box.h;
}

function choose(state, index) {
  state.selected = index;
  state.steps = [0, 0];
  state.hit = null;
}

function feedback(g, text) {
  g.miss();
  g.say(text, 'no', 1.65);
}

function land(g, state, clock) {
  if (clock.cycle === state.lastCycle) return;
  if (!onBeat(clock.phase)) {
    feedback(g, '等圆点进入中间的宽色带，再踩一步。');
    return;
  }
  if (state.selected == null) {
    feedback(g, '先选一张刚才试过的做法图，再踩步子。');
    return;
  }
  const lane = state.selected;
  const soft = LANES[lane].soft;
  state.lastCycle = clock.cycle;
  const step = state.steps[lane]++;
  state.hit = {lane, step, until: state.clock + 0.62};
  knock(soft);
  g.burst(MARKS[step], LANES[lane].y + 95, {n: soft ? 4 : 9, size: 5, color: soft ? '#70bd9c' : '#efad71'});

  if (state.compare) {
    if (state.steps[lane] < 3) return;
    if (lane === 0) {
      state.switchAt = state.clock + 0.75;
      g.say('直接碰的三步听完了。保持节拍，再试另一边。', 'ok', 1.75);
      return;
    }
    state.finishAt = state.clock + 1.35;
    g.say('两边都是同样的三步。软垫这一边的波纹小。', 'ok', 1.45);
    return;
  }

  if (!soft) {
    state.rejectAt = state.clock + 0.7;
    feedback(g, '这次的波纹比较大，想想刚才哪一种脚步更轻。');
    return;
  }
  if (state.steps[lane] === 4) {
    state.finishAt = state.clock + 0.95;
    g.say('较轻的四步走过去了！', 'ok', 1.15);
  }
}

function rounded(c, x, y, w, h, color, stroke, radius = 24) {
  K.draw.rr(c, x, y, w, h, radius);
  c.fillStyle = color;
  c.fill();
  if (stroke) {
    c.lineWidth = 4;
    c.strokeStyle = stroke;
    c.stroke();
  }
}

function picture(c, image, x, y, w, h) {
  if (!image.complete || !image.naturalWidth) return false;
  const scale = Math.min(w / image.naturalWidth, h / image.naturalHeight);
  const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
  c.drawImage(image, x + (w - width) / 2, y + (h - height) / 2, width, height);
  return true;
}

function paw(c, x, y, color, size) {
  c.fillStyle = color;
  for (const [dx, dy] of [[-.7,-.3],[-.24,-.69],[.24,-.69],[.7,-.3]]) {
    K.draw.circle(c, x + dx * size, y + dy * size, size * .2);
  }
  K.draw.circle(c, x, y + size * .16, size * .45);
}

function surface(c, soft, x, y, w) {
  rounded(c, x, y + 25, w, 16, colors.oak, null, 5);
  if (soft) rounded(c, x + w * 0.2, y + 8, w * 0.6, 20, '#e9bf68', '#ac7c45', 5);
  paw(c, x + w / 2, y - 8, colors.ink, 17);
}

function wave(c, x, y, soft, active = true) {
  const count = soft ? 1 : 3;
  c.strokeStyle = soft ? colors.soft : colors.loud;
  c.lineWidth = 4;
  c.lineCap = 'round';
  c.globalAlpha = active ? 1 : 0.57;
  for (let i = 0; i < count; i++) {
    c.beginPath();
    c.arc(x, y, 15 + 10 * i, Math.PI * 1.19, Math.PI * 1.81);
    c.stroke();
  }
  c.globalAlpha = 1;
}

function drawLane(c, state, index) {
  const lane = LANES[index];
  const selected = state.selected === index;
  rounded(c, LEFT, lane.y, WIDTH, 142, selected ? '#e7f6ec' : colors.paper,
    selected ? colors.green : colors.line);
  if (!picture(c, art[index], LEFT + 18, lane.y + 10, 240, 122)) {
    surface(c, lane.soft, LEFT + 49, lane.y + 62, 160);
  }
  rounded(c, 349, lane.y + 91, 746, 15, colors.oak, null, 7);
  for (let i = 0; i < (state.compare ? 3 : 4); i++) {
    const x = MARKS[i], complete = i < state.steps[index];
    c.fillStyle = complete ? colors.green : '#d5c8ae';
    K.draw.circle(c, x, lane.y + 88, 13);
    if (complete) {
      const last = state.hit?.lane === index && state.hit.step === i && state.clock < state.hit.until;
      wave(c, x, lane.y + 67, lane.soft, last);
    }
  }
}

function drawBeat(c, state) {
  const {x, y, w, h} = BEAT;
  rounded(c, x, y, w, h, colors.paper, colors.line);
  const l = x + 65, span = w - 130, mid = y + h / 2;
  rounded(c, l, mid - 10, span, 20, '#ceddda', null, 9);
  rounded(c, l + span * 0.28, mid - 21, span * 0.44, 42, '#8bd3b6', null, 20);
  c.fillStyle = colors.green;
  K.draw.circle(c, l + span * beat(state).phase, mid, 17);
}

K.game({
  levels: 2,
  winPause: 0.75,
  starsFor: () => 3,
  finishMark: '★★★',
  doneText: '同样的脚步，换一层软垫，就能比较碰地的声音。',
  setup(g) {
    g.follow('#quiet-beat', () => BEAT);
    g.follow('#quiet-test', () => ({x: LEFT, y: LANES[0].y, w: WIDTH, h: 317}));
    K.startPictureFallback = () => {
      const canvas = document.createElement('canvas');
      canvas.className = 'pic';
      canvas.width = 560;
      canvas.height = 315;
      const c = canvas.getContext('2d');
      rounded(c, 0, 0, 560, 315, colors.sky, null);
      surface(c, false, 65, 154, 180);
      surface(c, true, 315, 154, 180);
      return canvas;
    };
  },
  reset(g, level) {
    g.data = {
      clock: 0, period: level === 0 ? 1.7 : 1.48, compare: level === 0,
      selected: level === 0 ? 0 : null, steps: [0, 0], lastCycle: -1, hit: null,
      switchAt: null, rejectAt: null, finishAt: null, priorDirection: null
    };
  },
  autopilot(g) {
    const state = g.data;
    if (state.finishAt || state.switchAt || state.rejectAt) return;
    if (state.selected == null) {
      g.taps.push({x: 180, y: LANES[1].y + 55});
      return;
    }
    const clock = beat(state);
    if (clock.cycle !== state.lastCycle && onBeat(clock.phase)) {
      g.taps.push({x: STEP.x + STEP.w / 2, y: STEP.y + STEP.h / 2});
    }
  },
  update(g, dt) {
    const state = g.data;
    state.clock += dt;
    if (state.finishAt != null) {
      if (state.clock >= state.finishAt) g.win();
      return;
    }
    if (state.switchAt != null) {
      if (state.clock >= state.switchAt) {
        state.selected = 1;
        state.switchAt = null;
      }
      return;
    }
    if (state.rejectAt != null) {
      if (state.clock >= state.rejectAt) {
        state.selected = null;
        state.rejectAt = null;
      }
      return;
    }
    if (!state.compare) {
      const direction = g.keys.up ? 0 : g.keys.down ? 1 : null;
      if (direction != null && direction !== state.priorDirection) choose(state, direction);
      state.priorDirection = direction;
      const index = LANES.findIndex(lane => g.taps.some(tap =>
        inside(tap, {x: LEFT, y: lane.y, w: 275, h: 142})));
      if (index >= 0 && index !== state.selected) choose(state, index);
    }
    if (g.taps.some(tap => tap.key || inside(tap, STEP))) land(g, state, beat(state));
  },
  draw(g, c) {
    const state = g.data;
    c.fillStyle = colors.sky;
    c.fillRect(0, 0, 1280, 720);
    if (!state.steps) return;
    drawBeat(c, state);
    for (const i of [0, 1]) drawLane(c, state, i);
    for (let i = 0; i < 2; i++) {
      c.fillStyle = i <= g.level ? colors.green : colors.line;
      K.draw.circle(c, 62 + i * 42, 76, 12);
    }
    rounded(c, STEP.x, STEP.y, STEP.w, STEP.h, colors.green, '#165748', 28);
    if (!picture(c, pad, STEP.x + 20, STEP.y + 10, 78, 82)) paw(c, STEP.x + 58, STEP.y + 54, colors.paper, 24);
    K.draw.text(c, '踏一步', STEP.x + 208, STEP.y + 53, 39, '#fff');
    const instruction = state.compare ? '同样的步子，听两次' : '选轻的一种，再踩步点';
    K.draw.text(c, instruction, 380, 637, 33, colors.ink);
  },
  bubbleAt: () => ({x: 640, y: 183})
});
