K.ready({title: '国字框运输站', sub: '① 找外框　→　② 换位置　→　③ 双车挑战'});

const frame = {
  goal: '囗', cargo: '囗',
  hint: '沿四边看，里面的部分有没有穿出来？',
  hint2: '小口在一侧，跟从四面围住不一样。'
};

const crane = K.gameTemplates.crane({
  levels: [
    {
      name: '看看四边里面',
      demoRounds: [{...frame, cars: ['国', '中'], drop: [0], success: '玉留在四边里面。'}],
      rounds: [{...frame, cars: ['叶', '国'], drop: [1], success: '叶的口只在左边。'}]
    },
    {
      name: '看准两个新位置',
      rounds: [
        {...frame, cars: ['中', '回', '向'], drop: [1], success: '回的里面有个小口。'},
        {...frame, cars: ['国', '叶', '问'], drop: [0], engine: 'right',
          success: '国的外面四边合起来。'}
      ]
    },
    {
      name: '这一趟送两辆',
      rounds: [
        {...frame, cars: ['中', '回', '叶', '国'], drop: [1, 3],
          success: '国和回的外面都是国字框。'},
        {...frame, cars: ['国', '问', '回', '向'], drop: [0, 2], engine: 'right',
          success: '换了位置，还是看四边围住什么。'}
      ]
    }
  ],
  doneText: '四边围住里面，找到国字框。'
});

const updateCrane = crane.update;
const resetCrane = crane.reset;
const setupCrane = crane.setup;
let craneDrop;
let craneAudio;
let craneMusic;
let craneScore;
let craneCueBusy = false;
let craneVisible = true;
let craneBeat = 0;
let craneNextNote = 0;
let craneMuted = false;
const craneRoundPoints = new Map();

function startCraneMusic() {
  if (!craneAudio) {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    craneAudio = new Context();
  }
  if (craneAudio.state === 'suspended') craneAudio.resume().catch(() => {});
}

function playCraneNote(now) {
  const scale = [261.63, 329.63, 392, 329.63, 293.66, 349.23, 440, 349.23];
  const oscillator = craneAudio.createOscillator();
  const envelope = craneAudio.createGain();
  oscillator.type = 'triangle';
  oscillator.frequency.value = scale[craneBeat++ % scale.length];
  envelope.gain.setValueAtTime(0.001, now);
  envelope.gain.linearRampToValueAtTime(0.022, now + 0.03);
  envelope.gain.exponentialRampToValueAtTime(0.001, now + 0.32);
  oscillator.connect(envelope).connect(craneAudio.destination);
  oscillator.start(now);
  oscillator.stop(now + 0.34);
}

function craneCue(g, name) {
  if (!g.auto && craneVisible) window.miraNarrate?.('crane-' + name);
}

crane.setup = (g) => {
  setupCrane(g);
  craneDrop = K.$('#crane-drop');
  craneMusic = K.$('#crane-music');
  craneScore = K.$('#crane-score');
  craneDrop.addEventListener('click', () => {
    startCraneMusic();
    if (g.state === 'play' && !g.auto) g.taps.push({key: true});
  });
  craneMusic.addEventListener('click', () => {
    startCraneMusic();
    craneMuted = !craneMuted;
    craneMusic.textContent = craneMuted ? '♪' : '♫';
    craneMusic.setAttribute('aria-label', craneMuted ? '开启音乐' : '关闭音乐');
  });
  K.$('#crane-replay').addEventListener('click', () => craneCue(g, 'goal'));
  window.addEventListener('mira-narration-state', (event) => {
    craneCueBusy = event.detail?.status === 'playing';
  });
  window.addEventListener('message', (event) => {
    if (event.source !== window.parent || event.data?.type !== 'mira:checkpoint-visibility') return;
    craneVisible = event.data.active === true;
    if (!craneVisible) craneAudio?.suspend().catch(() => {});
  });
  window.addEventListener('keydown', (event) => {
    if (event.code === 'Space' && g.state === 'play' && !g.auto) startCraneMusic();
  });
  g.canvas.addEventListener('pointerdown', startCraneMusic);
  const say = g.say;
  g.say = (line, kind, duration) => {
    say(line, kind, duration);
    if (kind === 'no') {
      craneCue(g, g.data.wrong > 1 ? 'hint2' : 'hint');
      if (g.data.wrong >= 2) g.data.world.speed = Math.max(145, g.data.world.speed * 0.82);
    } else if (kind === 'ok') {
      craneCue(g, 'praise');
    }
  };
};

crane.reset = (g, level) => {
  resetCrane(g, level);
  if (level === 0) craneRoundPoints.clear();
  else for (const key of craneRoundPoints.keys()) {
    if (key.startsWith(level + ':')) craneRoundPoints.delete(key);
  }
  window.miraCancelNarration?.();
  craneCue(g, 'goal');
};

crane.update = (g, dt) => {
  const {next, round, wrong} = g.data;
  updateCrane(g, dt);
  if (!next && g.data.next > 0) {
    craneRoundPoints.set(g.level + ':' + round, 100 + (!wrong ? 25 * round : 0));
  }
};

crane.starsFor = g => Math.max(1, 3 - Math.floor(g.levelMisses / 2));
crane.drawTop = (g) => {
  const enabled = g.state === 'play' && !g.auto;
  K.$('#crane-controls').hidden = !enabled;
  const total = [...craneRoundPoints.values()].reduce((sum, score) => sum + score, 0);
  const label = '得分 ' + total;
  if (craneScore.textContent !== label) craneScore.textContent = label;
  const finish = g.state === 'done' ? K.$('#finish .card p') : null;
  if (finish && !finish.textContent.includes(label)) finish.textContent += '　' + label;
  if (enabled && craneVisible && !craneMuted && !craneCueBusy && craneAudio?.state === 'running' && !document.hidden &&
      craneAudio.currentTime >= craneNextNote) {
    playCraneNote(craneAudio.currentTime);
    craneNextNote = craneAudio.currentTime + 0.47;
  }
};

crane.demoOnce = true;
K.game(crane);
