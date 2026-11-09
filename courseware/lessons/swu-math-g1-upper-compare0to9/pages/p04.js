const SVG = 'http://www.w3.org/2000/svg';
const svgNode = (tag, attributes) => {
  const element = document.createElementNS(SVG, tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  return element;
};
function token(x, y, shape, size = 17) {
  const geometry = shape === 'circle'
    ? { cx: x, cy: y, r: size }
    : { x: x - size, y: y - size, width: size * 2, height: size * 2, rx: 6 };
  return svgNode(shape === 'circle' ? 'circle' : 'rect', {
    ...geometry, fill: shape === 'circle' ? '#2b857b' : '#edac58',
    stroke: shape === 'circle' ? '#23695e' : '#ab632c', 'stroke-width': 2,
  });
}
function choice(label, content, callback) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'choice-tile';
  button.setAttribute('aria-label', label);
  button.append(content);
  button.addEventListener('click', () => callback(button));
  return button;
}
function formula(left, sign, right) {
  K.$('.formula-left').textContent = left;
  K.$('.formula-symbol').textContent = sign;
  K.$('.formula-right').textContent = right;
}
function wrong(button, first, next) {
  K.shake(button);
  K.sfx.no();
  K.say(++misses === 1 ? first : next, 'no');
}
function stars(resetMessage) {
  K.stars = 0;
  K.$('#star-n').textContent = '0';
  K.levels(levels.length, 0);
  K.say(resetMessage);
}
function reward(button) {
  K.star(1, button);
  K.levels(levels.length, round + 1);
  K.sfx.ok();
  K.say('配好了，看看图上怎么检查。', 'ok');
  return K.wait(460);
}
function finish() {
  K.finish({ title: '这一轮完成了', sub: '还能再玩一次。', again: reset });
}
function setup(title) {
  K.hud({ title, icon: '', levels: levels.length });
  K.owl();
  K.ready({ title, sub: '听一听，再动手。', emoji: '○ □' });
  K.onStart = reset;
  reset();
}
let round = 0;
let misses = 0;
let busy = false;
let demonstration = false;
function unlockForPractice() {
  if (!demonstration) return false;
  reset();
  return true;
}

const levels = [[7, 4], [4, 7], [8, 8]];
const signs = ['<', '=', '>'];
const board = K.$('#sign-board');
const choices = K.$('#sign-choices');
const slot = K.$('.formula-card');
function trayPair(left, right, connect) {
  const svg = svgNode('svg', { viewBox: '0 0 760 214', role: 'img',
    'aria-label': '左边' + left + '个圆片，右边' + right + '个方片' });
  const groups = [[left, 120, 'circle'], [right, 469, 'square']];
  groups.forEach(([, x]) => {
    svg.append(svgNode('rect', { x: x - 44, y: 14, width: 233, height: 186, rx: 24,
      fill: '#fffdf5', stroke: '#8db1a7', 'stroke-width': 3 }));
  });
  if (connect) {
    for (let index = 0; index < Math.min(left, right); index++) {
      const y = 49 + (index % 3) * 53;
      svg.append(svgNode('path', { d: 'M 256 ' + y + ' H 447', stroke: '#6d9184',
        'stroke-width': 4, 'stroke-dasharray': '5 7' }));
    }
  }
  groups.forEach(([count, x, shape]) => {
    for (let index = 0; index < count; index++) {
      const column = Math.floor(index / 3);
      const tokenX = shape === 'circle' ? x + (2 - column) * 58 : x + column * 58;
      svg.append(token(tokenX, 49 + (index % 3) * 53, shape));
    }
  });
  return svg;
}
function draw(pair, selected = '', connect = false) {
  const [left, right] = pair;
  board.replaceChildren(trayPair(left, right, connect));
  formula(left, selected || '□', right);
  K.drags = K.drags.filter((entry) => !choices.contains(entry.el));
  const buttons = signs.map((sign) => {
    const name = sign === '<' ? '小于号' : sign === '>' ? '大于号' : '等号';
    const button = choice(name, sign, (node) => pick(sign, node));
    if (sign === selected) button.classList.add('chosen');
    K.drag(button, { enabled: () => !busy, targets: () => [slot],
      onTap: null, onDrop: (_, target) => { if (target) pick(sign, button); } });
    return button;
  });
  choices.replaceChildren(...buttons);
}
async function pick(sign, button) {
  if (busy || unlockForPractice()) return;
  const [left, right] = levels[round];
  const expected = left < right ? '<' : left > right ? '>' : '=';
  if (sign !== expected) {
    wrong(button, '先数两边，看看哪边多。', '相同用两横。不同就检查开口朝向。');
    return;
  }
  busy = true;
  draw(levels[round], sign);
  await reward(choices.children[signs.indexOf(sign)]);
  round++;
  misses = 0;
  if (round === levels.length) return finish();
  busy = false;
  draw(levels[round]);
  K.say('先看两边，再选符号。');
}
function reset() {
  round = misses = 0;
  busy = demonstration = false;
  draw(levels[round]);
  stars('点符号，或者拖进中间。');
}
K.onState = ({ demo }) => {
  if (demo === 'practice') return reset();
  demonstration = true;
  draw([6, 2], demo === 'symbol' ? '>' : '', true);
  K.highlight(demo === 'symbol' ? '.formula-card' : '#sign-board');
};
setup('把开口朝向大数');
