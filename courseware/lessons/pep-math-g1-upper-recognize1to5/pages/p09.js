(() => {
  // Each arrow and the colored trace are derived from the same written curve.
  const digits = {
    1: [{ path: 'M112 28 L81 145', start: [112, 28], end: [81, 145] }],
    2: [{ path: 'M72 54 C78 25 125 22 133 49 C142 75 100 112 77 145 L140 145', start: [72, 54], end: [140, 145] }],
    3: [{ path: 'M70 50 C83 23 127 22 130 57 C132 73 116 82 99 88 C120 90 137 108 131 129 C123 153 85 153 69 134', start: [70, 50], end: [69, 134] }],
    4: [{ path: 'M106 27 L75 109 L141 109', start: [106, 27], end: [141, 109] },
        { path: 'M133 52 L100 146', start: [133, 52], end: [100, 146] }],
    5: [{ path: 'M91 28 L76 82 C94 65 128 75 136 101 C146 140 107 158 71 135', start: [91, 28], end: [71, 135] },
        { path: 'M88 37 L136 37', start: [88, 37], end: [136, 37] }],
  };
  const board = K.$('#writing-board');
  const route = K.$('#writing-route');
  const svgNamespace = 'http://www.w3.org/2000/svg';
  let number = 1;
  let stroke = 0;
  let teaching = false;
  let accepted = false;
  let misses = 0;
  let timer;

  K.hud({ icon: '↙', title: '数字沿线走', levels: 5 });
  K.owl();
  K.ready({ emoji: '1–5', title: '数字沿线走', sub: '点一端，看亮线怎样走' });

  function svgElement(tag, attrs, parent) {
    const node = document.createElementNS(svgNamespace, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    parent.appendChild(node);
    return node;
  }

  function arrow(svg, path, start) {
    const length = path.getTotalLength();
    const end = path.getPointAtLength(length);
    const before = path.getPointAtLength(Math.max(0, length - 12));
    const angle = Math.atan2(end.y - before.y, end.x - before.x) * 180 / Math.PI;
    svgElement('path', { d: 'M -8 -5 L 0 0 L -8 5', class: 'digit-arrow', transform: `translate(${end.x} ${end.y}) rotate(${angle})` }, svg);
    svgElement('circle', { cx: start[0], cy: start[1], r: 4, class: 'digit-start' }, svg);
  }

  function endpoint(point, isStart) {
    const button = K.el('button', 'writing-endpoint', '<span></span>', board);
    button.type = 'button';
    button.id = isStart ? 'writing-point-a' : 'writing-point-b';
    button.style.left = (point[0] / 2) + '%';
    button.style.top = (point[1] / 176 * 100) + '%';
    button.setAttribute('aria-label', point[1] < 85 ? '上面的圆点' : '下面的圆点');
    if (Math.abs(digits[number][stroke].start[1] - digits[number][stroke].end[1]) < 15) {
      button.setAttribute('aria-label', point[0] < 110 ? '左边的圆点' : '右边的圆点');
    }
    button.addEventListener('click', () => choose(isStart));
  }

  function render() {
    board.replaceChildren();
    route.replaceChildren();
    const svg = svgElement('svg', { viewBox: '0 0 200 176', 'aria-hidden': 'true' }, board);
    svgElement('path', { d: 'M20 22 H180 M20 88 H180 M20 154 H180 M100 22 V154', class: 'writing-grid' }, svg);
    const paths = digits[number];
    for (const segment of paths) svgElement('path', { d: segment.path, class: 'digit-outline' }, svg);
    for (let i = 0; i < stroke; i++) svgElement('path', { d: paths[i].path, class: 'digit-ink' }, svg);
    const active = paths[stroke];
    if (teaching || accepted) {
      const ink = svgElement('path', { d: active.path, class: 'digit-ink digit-animate', pathLength: 1 }, svg);
      arrow(svg, ink, active.start);
    } else {
      svgElement('path', { d: active.path, class: 'digit-dashed' }, svg);
      endpoint(active.start, true);
      endpoint(active.end, false);
    }
    K.el('strong', 'writing-number', String(number), route);
    const dots = K.el('span', 'writing-row', '', route);
    for (let i = 0; i < paths.length; i++) {
      K.el('i', 'writing-pill' + (i < stroke || (accepted && i === stroke) ? ' done' : i === stroke ? ' active' : ''), '', dots);
    }
    K.el('span', 'writing-caption', teaching ? '跟着亮线看方向' : '找到这一段的起点', route);
    K.levels(5, number - 1);
  }

  function choose(isStart) {
    if (teaching || accepted) return;
    if (!isStart) {
      misses++;
      K.sfx.no();
      K.say(misses === 1 ? '想想老师让笔从哪边出发。' : '先看这段线在数字的什么地方。', 'no');
      if (misses >= 3) K.highlight('#writing-point-a');
      return;
    }
    accepted = true;
    render();
    K.sfx.tick(number);
    K.say('看亮线顺着这一段走到末尾。', 'ok');
    const lastStroke = stroke + 1 === digits[number].length;
    if (lastStroke) K.star(1, route);
    timer = setTimeout(() => {
      if (lastStroke && number === 5) {
        K.finish({ title: '数字路线看清了', sub: '有纸笔时描一描，再请家人看一看。', again: reset });
        return;
      }
      if (lastStroke) { number++; stroke = 0; }
      else stroke++;
      accepted = false;
      misses = 0;
      render();
      K.say('点一点，看下一段从哪里出发。');
    }, 970);
  }

  function reset() {
    clearTimeout(timer);
    number = 1;
    stroke = 0;
    teaching = false;
    accepted = false;
    misses = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    render();
    K.say('看数字和线，试着找起点。');
  }

  K.onStart = reset;
  K.onState = state => {
    if (state.play) { reset(); return; }
    if (!digits[state.digit] || !digits[state.digit][state.stroke]) return;
    clearTimeout(timer);
    teaching = true;
    accepted = false;
    number = state.digit;
    stroke = state.stroke;
    render();
    K.say('看圆点出发，沿亮线到箭头。');
  };
  reset();
})();
