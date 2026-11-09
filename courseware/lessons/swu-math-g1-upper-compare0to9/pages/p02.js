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
function pairedRows(top, bottom, { connect = false, mark = false } = {}) {
  const svg = svgNode('svg', { viewBox: '0 0 760 214', role: 'img',
    'aria-label': '上排' + top + '个圆片，下排' + bottom + '个方片' });
  const paired = Math.min(top, bottom);
  for (let index = 0; index < Math.max(top, bottom); index++) {
    const x = 68 + 78 * index;
    if (connect && index < paired) {
      svg.append(svgNode('path', { d: 'M ' + x + ' 73 V 143', stroke: '#6d9184',
        'stroke-width': 4, 'stroke-dasharray': '5 7' }));
    }
    if (mark && index >= paired) {
      svg.append(svgNode('rect', { x: x - 30, y: top > bottom ? 27 : 129, width: 60,
        height: 60, rx: 18, fill: '#f9e4c3', stroke: '#c2782d', 'stroke-width': 3 }));
    }
    if (index < top) svg.append(token(x, 57, 'circle'));
    if (index < bottom) svg.append(token(x, 159, 'square'));
  }
  return svg;
}
function choicePicture(count, shape) {
  const svg = svgNode('svg', { viewBox: '0 0 176 78', 'aria-hidden': true });
  for (let index = 0; index < count; index++) {
    svg.append(token(24 + (index % 5) * 32, 23 + Math.floor(index / 5) * 31, shape, 10));
  }
  return svg;
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

const levels = [{ reference: 2, choices: [6, 2, 7] }, { reference: 5, choices: [5, 8, 1] }];
const preview = { reference: 3, choices: [4, 3, 5] };
const board = K.$('#match-board');
const choices = K.$('#match-choices');
function draw(item, selected = 0, showRelation = false) {
  board.replaceChildren(pairedRows(item.reference, selected, { connect: selected > 0 }));
  formula(item.reference, showRelation ? '=' : '·', showRelation ? selected : '□');
  choices.replaceChildren(...item.choices.map((count) =>
    choice(count + '个方片', choicePicture(count, 'square'), (button) => pick(count, button))));
  if (selected) choices.children[item.choices.indexOf(selected)].classList.add('chosen');
}
async function pick(count, button) {
  if (busy || unlockForPractice()) return;
  const item = levels[round];
  if (count !== item.reference) {
    wrong(button, '从上面取一个，对下面一个。', '看两排有没有一边会剩下。');
    return;
  }
  busy = true;
  draw(item, count, true);
  await reward(choices.children[item.choices.indexOf(count)]);
  round++;
  misses = 0;
  if (round === levels.length) return finish();
  busy = false;
  draw(levels[round]);
  K.say('换一组，再找同样多的。');
}
function reset() {
  round = misses = 0;
  busy = demonstration = false;
  draw(levels[round]);
  stars('选一盘和上面同样多的方片。');
}
K.onState = ({ demo }) => {
  if (demo === 'practice') return reset();
  demonstration = true;
  draw(preview, demo === 'trays' ? 0 : 3, demo === 'relation');
  K.highlight(demo === 'relation' ? '.formula-card' : '#match-board');
};
setup('配一配找同样多');
