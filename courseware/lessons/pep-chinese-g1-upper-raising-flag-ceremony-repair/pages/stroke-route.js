K.ready({title: '田字格笔画小车', sub: '① 走直线　→　② 学转弯　→　③ 连笔挑战'});

// Original routes checked against the grid on printed page 79.
const traceConfig = {
  "levels": [
    {
      "name": "先写外框，再走中线",
      "rounds": [
        {
          "goal": "中",
          "gridBox": [
            640,
            450,
            396
          ],
          "strokes": [
            [
              [
                542,
                379
              ],
              [
                548,
                502
              ]
            ],
            [
              [
                542,
                379
              ],
              [
                733,
                365
              ],
              [
                724,
                498
              ]
            ],
            [
              [
                548,
                502
              ],
              [
                724,
                498
              ]
            ],
            [
              [
                640,
                322
              ],
              [
                640,
                570
              ]
            ]
          ],
          "hint": "先找左边的起点。",
          "hint2": "最后一竖走过竖中线。",
          "success": "四笔写好，长竖在中间。"
        }
      ]
    },
    {
      "name": "留心底下的长横",
      "rounds": [
        {
          "goal": "五",
          "gridBox": [
            640,
            450,
            396
          ],
          "strokes": [
            [
              [
                550,
                344
              ],
              [
                723,
                337
              ]
            ],
            [
              [
                622,
                344
              ],
              [
                607,
                445
              ],
              [
                588,
                548
              ]
            ],
            [
              [
                550,
                432
              ],
              [
                706,
                422
              ],
              [
                683,
                550
              ]
            ],
            [
              [
                510,
                554
              ],
              [
                771,
                547
              ]
            ]
          ],
          "hint": "找一找小车停下的地方。",
          "hint2": "折下来以后，还要写底下的长横。",
          "success": "短横在上，长横在下。"
        },
        {
          "goal": "正",
          "gridBox": [
            640,
            450,
            396
          ],
          "strokes": [
            [
              [
                534,
                349
              ],
              [
                734,
                340
              ]
            ],
            [
              [
                641,
                345
              ],
              [
                641,
                548
              ]
            ],
            [
              [
                640,
                446
              ],
              [
                738,
                438
              ]
            ],
            [
              [
                550,
                445
              ],
              [
                554,
                548
              ]
            ],
            [
              [
                502,
                556
              ],
              [
                776,
                546
              ]
            ]
          ],
          "hint": "从这笔的起点慢一点走。",
          "hint2": "先看中间竖，再看左竖。",
          "success": "两竖落到最后的长横上。"
        }
      ]
    },
    {
      "name": "点撇横，试一笔横斜钩",
      "rounds": [
        {
          "goal": "立",
          "gridBox": [
            640,
            450,
            396
          ],
          "strokes": [
            [
              [
                632,
                319
              ],
              [
                654,
                357
              ]
            ],
            [
              [
                536,
                391
              ],
              [
                738,
                383
              ]
            ],
            [
              [
                574,
                428
              ],
              [
                601,
                482
              ]
            ],
            [
              [
                699,
                423
              ],
              [
                681,
                472
              ],
              [
                652,
                504
              ]
            ],
            [
              [
                509,
                548
              ],
              [
                774,
                540
              ]
            ]
          ],
          "hint": "先看车在哪儿，再接着走。",
          "hint2": "先写上面的点，最后写长横。",
          "success": "点、横、点、撇，长横收尾。"
        },
        {
          "goal": "风",
          "gridBox": [
            640,
            450,
            396
          ],
          "strokes": [
            [
              [
                559,
                357
              ],
              [
                557,
                426
              ],
              [
                545,
                479
              ],
              [
                526,
                522
              ],
              [
                496,
                554
              ]
            ],
            [
              [
                560,
                355
              ],
              [
                707,
                336
              ],
              [
                697,
                394
              ],
              [
                703,
                454
              ],
              [
                728,
                508
              ],
              [
                765,
                549
              ],
              [
                779,
                558
              ],
              [
                788,
                526
              ]
            ],
            [
              [
                658,
                389
              ],
              [
                638,
                443
              ],
              [
                610,
                492
              ],
              [
                576,
                525
              ]
            ],
            [
              [
                586,
                420
              ],
              [
                625,
                453
              ],
              [
                655,
                499
              ]
            ]
          ],
          "hint": "转弯处慢一点，小车等你。",
          "hint2": "第二笔一路连着走，右下再向上钩。",
          "success": "横、斜、钩，连成第二笔。"
        }
      ]
    }
  ],
  "doneText": "顺着笔顺，写好五个字。"
};
const firstTrace = traceConfig.levels[0].rounds[0];
traceConfig.levels[0].demoRounds = [{
  ...firstTrace, strokes: firstTrace.strokes.slice(0, 1), success: '第一笔从上往下。'
}];
const trace = K.gameTemplates.trace(traceConfig);

const updateTrace = trace.update;
const resetTrace = trace.reset;
const setupTrace = trace.setup;
const traceHeld = new Map();
const traceScoreByRound = new Map();
let traceSteering = false;
let traceScore;
let traceAudio;
let traceMusic;
let traceCueBusy = false;
let traceVisible = true;
let traceMuted = false;
let traceNextNote = 0;
let traceBeat = 0;

function startTraceMusic() {
  if (!traceAudio) {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    traceAudio = new Context();
  }
  if (traceAudio.state === 'suspended') traceAudio.resume().catch(() => {});
}

function playTraceNote(now) {
  const scale = [293.66, 369.99, 440, 369.99, 329.63, 392, 493.88, 392];
  const oscillator = traceAudio.createOscillator();
  const envelope = traceAudio.createGain();
  oscillator.type = 'triangle';
  oscillator.frequency.value = scale[traceBeat++ % scale.length];
  envelope.gain.setValueAtTime(0.001, now);
  envelope.gain.linearRampToValueAtTime(0.022, now + 0.03);
  envelope.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
  oscillator.connect(envelope).connect(traceAudio.destination);
  oscillator.start(now);
  oscillator.stop(now + 0.34);
}

function traceCue(g, name) {
  if (!g.auto && traceVisible) window.miraNarrate?.('trace-' + name);
}

trace.setup = (g) => {
  setupTrace(g);
  traceScore = K.$('#trace-score');
  traceMusic = K.$('#trace-music');
  traceMusic.addEventListener('click', () => {
    startTraceMusic();
    traceMuted = !traceMuted;
    traceMusic.textContent = traceMuted ? '♪' : '♫';
    traceMusic.setAttribute('aria-label', traceMuted ? '开启音乐' : '关闭音乐');
  });
  K.$('#trace-replay').addEventListener('click', () => traceCue(g, 'goal'));
  for (const button of K.$$('[data-trace-direction]')) {
    button.addEventListener('pointerdown', (event) => {
      if (g.state !== 'play' || g.auto || event.button !== 0) return;
      event.preventDefault();
      button.setPointerCapture(event.pointerId);
      traceHeld.set(event.pointerId, button.dataset.traceDirection);
      startTraceMusic();
    });
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      button.addEventListener(name, event => traceHeld.delete(event.pointerId));
    }
  }
  window.addEventListener('keydown', (event) => {
    if (g.state === 'play' && !g.auto && event.code.startsWith('Arrow')) startTraceMusic();
  });
  window.addEventListener('blur', () => {
    traceHeld.clear();
    for (const key of ['left', 'right', 'up', 'down']) g.keys[key] = false;
  });
  window.addEventListener('mira-narration-state', (event) => {
    traceCueBusy = event.detail?.status === 'playing';
  });
  window.addEventListener('message', (event) => {
    if (event.source !== window.parent || event.data?.type !== 'mira:checkpoint-visibility') return;
    traceVisible = event.data.active === true;
    if (!traceVisible) {
      traceHeld.clear();
      for (const key of ['left', 'right', 'up', 'down']) g.keys[key] = false;
      traceAudio?.suspend().catch(() => {});
    }
  });
  g.canvas.addEventListener('pointerdown', startTraceMusic);
  const say = g.say;
  g.say = (line, kind, duration) => {
    say(line, kind, duration);
    if (kind === 'no') traceCue(g, g.data.wrong > 1 ? 'hint2' : 'hint');
    else if (kind === 'ok') traceCue(g, 'praise');
  };
};

trace.reset = (g, level) => {
  resetTrace(g, level);
  traceHeld.clear();
  traceSteering = false;
  if (level === 0) traceScoreByRound.clear();
  else for (const key of traceScoreByRound.keys()) {
    if (key.startsWith(level + ':')) traceScoreByRound.delete(key);
  }
  window.miraCancelNarration?.();
  traceCue(g, 'goal');
};

function tracePosition(route, distance) {
  const next = route.lengths.findIndex(length => length > distance);
  if (next < 0) return route.points.at(-1);
  const a = route.points[next - 1];
  const b = route.points[next];
  const t = (distance - route.lengths[next - 1]) / (route.lengths[next] - route.lengths[next - 1]);
  return {x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y)};
}

trace.update = (g, dt) => {
  const {next, round, wrong, world} = g.data;
  const pointer = g.pointer;
  if (!g.auto && !pointer.down) {
    const held = direction => g.keys[direction] || [...traceHeld.values()].includes(direction);
    const dx = Number(held('right')) - Number(held('left'));
    const dy = Number(held('down')) - Number(held('up'));
    const distance = Math.hypot(dx, dy);
    if (!next && distance > 0) {
      if (!traceSteering && !world.release) world.grip = null;
      traceSteering = true;
      const route = world.paths[world.stroke];
      const position = tracePosition(route, world.s);
      const corner = route.lengths.find(length => length - world.s > 1e-7) ?? route.length;
      const look = tracePosition(route, Math.min(corner, world.s + 24));
      const heading = Math.atan2(look.y - position.y, look.x - position.x);
      const difference = heading - Math.atan2(dy, dx);
      // Move a virtual pointer in the requested direction. The same stroke
      // geometry, projection and corner checks apply as for a real drag.
      const lead = world.grip ? (Math.cos(difference) < 0.2 ? 68 : 42) / distance : 0;
      g.pointer = {x: position.x + dx * lead, y: position.y + dy * lead, down: true, active: true};
    } else {
      traceSteering = false;
    }
  } else {
    if (traceSteering && !world.release) world.grip = null;
    traceSteering = false;
  }
  try {
    updateTrace(g, dt);
  } finally {
    g.pointer = pointer;
  }
  if (!next && g.data.next > 0) {
    traceScoreByRound.set(g.level + ':' + round, 100 + (!wrong ? 25 * round : 0));
  }
};

trace.starsFor = g => Math.max(1, 3 - Math.floor(g.levelMisses / 2));
trace.drawTop = (g) => {
  const enabled = g.state === 'play' && !g.auto;
  K.$('#trace-controls').hidden = !enabled;
  const total = [...traceScoreByRound.values()].reduce((sum, score) => sum + score, 0);
  const label = '得分 ' + total;
  if (traceScore.textContent !== label) traceScore.textContent = label;
  const finish = g.state === 'done' ? K.$('#finish .card p') : null;
  if (finish && !finish.textContent.includes(label)) finish.textContent += '　' + label;
  if (enabled && traceVisible && !traceMuted && !traceCueBusy && traceAudio?.state === 'running' && !document.hidden &&
      traceAudio.currentTime >= traceNextNote) {
    playTraceNote(traceAudio.currentTime);
    traceNextNote = traceAudio.currentTime + 0.47;
  }
};

K.game(trace);
