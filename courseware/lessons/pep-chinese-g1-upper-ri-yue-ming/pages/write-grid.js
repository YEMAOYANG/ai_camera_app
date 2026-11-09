(() => {
  const glyphs = {
    '力': [
      'M75 106 Q116 104 177 96 Q174 147 157 187 Q152 197 137 186 L122 177',
      'M130 65 Q121 131 85 169 Q68 189 48 198',
    ],
    '男': [
      'M79 53 Q76 77 73 104',
      'M79 54 Q128 48 177 51 L171 103',
      'M77 77 Q125 74 172 75',
      'M127 51 L126 101',
      'M74 104 L170 101',
      'M76 139 Q121 138 175 132 Q171 170 156 194 Q151 202 136 194',
      'M127 113 Q122 155 100 181 Q84 200 63 209',
    ],
    '土': [
      'M82 107 Q127 105 174 101',
      'M128 66 L128 178',
      'M57 181 Q130 175 201 175',
    ],
    '木': [
      'M70 105 Q132 101 188 97',
      'M129 63 L126 198',
      'M124 107 Q100 153 58 179',
      'M135 106 Q154 154 197 175',
    ],
    '心': [
      'M74 128 Q69 148 60 161',
      'M85 119 Q99 155 124 170 Q152 187 179 173 L166 155',
      'M119 83 Q134 93 143 107',
      'M169 87 Q186 94 197 111',
    ],
  };
  const sequence = {
    '力和男写在哪': ['力', '男'],
    '卧钩弯着落': ['心'],
    '土和木的横竖': ['土', '木'],
  }[document.title];
  if (!sequence) throw new Error('没有找到本课写字练习');

  const guide = K.$('#ry-glyph-strokes');
  const activeCharacter = K.$('#ry-character');
  const strip = K.$('#ry-sequence');
  const ink = K.$('#ry-ink');
  const brush = ink.getContext('2d');
  const showStroke = K.$('#ry-show-stroke');
  const clearInk = K.$('#ry-clear-ink');
  const confirm = K.$('#ry-confirm-ink');
  const progress = K.$('#ry-ink-progress-value');
  const svgNs = 'http://www.w3.org/2000/svg';
  const viewSize = 256;
  let level = 0;
  let demonstration = false;
  let advancing = false;
  let pointer = null;
  let previous = null;
  let samples = [];
  let visited = new Set();
  let timer;
  let demoTimer;

  function path(d, color) {
    const node = document.createElementNS(svgNs, 'path');
    node.setAttribute('d', d);
    node.setAttribute('fill', 'none');
    node.setAttribute('stroke', color);
    node.setAttribute('stroke-width', '9');
    node.setAttribute('stroke-linecap', 'round');
    node.setAttribute('stroke-linejoin', 'round');
    return node;
  }

  function paintGlyph(activeStroke = -1) {
    const word = sequence[level];
    const strokes = glyphs[word];
    activeCharacter.textContent = word;
    guide.replaceChildren();
    strip.replaceChildren();
    samples = [];
    strokes.forEach((d, index) => {
      const node = path(d, index === activeStroke ? '#b84c32' : '#bdc9b7');
      guide.append(node);
      const length = node.getTotalLength();
      for (let at = 0; at <= length; at += 7) {
        const {x, y} = node.getPointAtLength(at);
        samples.push({x, y});
      }
      const miniature = document.createElementNS(svgNs, 'svg');
      miniature.setAttribute('viewBox', '0 0 256 256');
      miniature.setAttribute('aria-hidden', 'true');
      if (activeStroke === index) miniature.classList.add('active');
      strokes.slice(0, index + 1).forEach((step, n) => {
        miniature.append(path(step, n === index ? '#b84c32' : '#9aaca2'));
      });
      strip.append(miniature);
    });
  }

  function clear() {
    pointer = null;
    previous = null;
    visited = new Set();
    brush.clearRect(0, 0, ink.width, ink.height);
    progress.style.width = '0%';
    confirm.disabled = true;
  }

  function startWriting() {
    clearTimeout(timer);
    clearTimeout(demoTimer);
    advancing = false;
    demonstration = false;
    clear();
    paintGlyph();
    showStroke.disabled = false;
    clearInk.disabled = false;
    K.levels(sequence.length, level);
    K.say('沿着淡色的笔画慢慢描，可以重画。');
  }

  function reset() {
    level = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$('#finish')?.classList.add('gone');
    startWriting();
  }

  function showExample(index, emphasis) {
    clearTimeout(timer);
    clearTimeout(demoTimer);
    level = index;
    advancing = false;
    demonstration = true;
    clear();
    paintGlyph(emphasis);
    showStroke.disabled = false;
    clearInk.disabled = true;
    K.levels(sequence.length, 0);
    K.say('看红色的这一笔，再看格子里的位置。');
  }

  function tracePoint(event) {
    const box = ink.getBoundingClientRect();
    return {x: (event.clientX - box.left) * viewSize / box.width,
      y: (event.clientY - box.top) * viewSize / box.height};
  }

  function near(point, start, end) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const size = dx * dx + dy * dy;
    const along = size ? Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / size)) : 0;
    return Math.hypot(point.x - start.x - along * dx, point.y - start.y - along * dy) < 10;
  }

  function stroke(start, end) {
    const scale = ink.width / viewSize;
    brush.lineWidth = 9 * scale;
    brush.strokeStyle = '#3f8d7e';
    brush.lineCap = 'round';
    brush.beginPath();
    brush.moveTo(start.x * scale, start.y * scale);
    brush.lineTo(end.x * scale, end.y * scale);
    brush.stroke();
    samples.forEach((sample, index) => {
      if (near(sample, start, end)) visited.add(index);
    });
    const coverage = visited.size / samples.length;
    progress.style.width = (coverage * 100).toFixed(1) + '%';
    if (coverage >= 0.48 && confirm.disabled) {
      confirm.disabled = false;
      K.say('已经留下不少描迹，可以继续。', 'ok');
    }
  }

  function pointerStopped() {
    pointer = null;
    previous = null;
  }

  ink.addEventListener('pointerdown', event => {
    if (!K.started || advancing || demonstration || event.button > 0 || pointer !== null) return;
    event.preventDefault();
    pointer = event.pointerId;
    previous = tracePoint(event);
    stroke(previous, previous);
    ink.setPointerCapture?.(pointer);
  });
  ink.addEventListener('pointermove', event => {
    if (event.pointerId !== pointer || !previous) return;
    const next = tracePoint(event);
    stroke(previous, next);
    previous = next;
  });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    ink.addEventListener(event, pointerStopped);
  }
  clearInk.addEventListener('click', () => {
    if (demonstration || advancing) return;
    clear();
    K.say('清干净了，沿淡字再试一遍。');
  });
  showStroke.addEventListener('click', () => {
    if (advancing) return;
    clearTimeout(demoTimer);
    const wasTeacherDemo = demonstration;
    const length = glyphs[sequence[level]].length;
    let index = 0;
    demonstration = true;
    clear();
    showStroke.disabled = true;
    clearInk.disabled = true;
    function nextStep() {
      if (index < length) {
        paintGlyph(index);
        index += 1;
        demoTimer = setTimeout(nextStep, 550);
      } else if (wasTeacherDemo) {
        showExample(level, length - 1);
      } else {
        startWriting();
      }
    }
    nextStep();
  });
  confirm.addEventListener('click', () => {
    if (confirm.disabled || advancing || demonstration) return;
    advancing = true;
    K.star(1, confirm);
    K.sfx.ok();
    K.levels(sequence.length, level + 1);
    K.say('这只记录描到的范围。写在纸上，再看笔顺和格位。', 'ok');
    timer = setTimeout(() => {
      if (level + 1 < sequence.length) {
        level += 1;
        startWriting();
      } else {
        K.finish({title:'田字格练习完成',sub:'请家人看纸上的字形和笔顺',again:reset});
      }
    }, 500);
  });

  K.hud({icon:'笔',title:document.title,levels:sequence.length});
  K.owl();
  K.ready({title:document.title,sub:'看清位置，再沿淡字描画',emoji:'字'});
  K.onStart = reset;
  K.onState = state => {
    if (state.phase === 'play') {
      reset();
    } else if (Number.isInteger(state.demoRound) && state.demoRound >= 0 && state.demoRound < sequence.length) {
      const index = sequence[state.demoRound] === '心' ? 1 : 0;
      showExample(state.demoRound, index);
    }
  };
  startWriting();
})();
