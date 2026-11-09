function makeDot() {
  const dot = document.createElement('span');
  dot.className = 'count-dot';
  dot.setAttribute('aria-hidden', 'true');
  return dot;
}
function makeToken(index, marked, onPick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'count-token' + (marked ? ' marked' : '');
  button.setAttribute('aria-label', '圆片 ' + (index + 1));
  button.append(makeDot());
  button.addEventListener('click', () => onPick(index, button));
  return button;
}
function makeChoice(number) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn ghost digit-choice';
  button.textContent = String(number);
  return button;
}
function miss(node, message) {
  K.shake(node);
  K.sfx.no();
  K.say(message, 'no');
}
function stopDemo(reset) {
  if (!demonstration) return false;
  demonstration = false;
  reset();
  return true;
}
function resetKit(levels, message) {
  K.stars = 0;
  K.$('#star-n').textContent = '0';
  K.levels(levels, 0);
  K.say(message);
}
function complete(levels, reset) {
  K.star(1);
  K.levels(levels, levels);
  K.say('完成了。', 'ok');
  K.finish({title:'这一轮完成了', sub:'还能再玩一次。', again:reset});
}
function startGame(title, reset, levels) {
  K.hud({title, icon:'', levels});
  K.owl();
  K.ready({title, sub:'听一听，再动手。', emoji:'○'});
  K.onStart = reset;
  reset();
}
const board = K.$('#route-board');
const objects = K.$('#route-objects');
const switcher = K.$('#route-shape');
const count = 8;
let round = 0;
let route = [];
let direction = 0;
let demonstration = false;
function mark(index, node) {
  if (stopDemo(reset)) return;
  if (round === 1 && !route.length && index !== 0) {
    miss(node, '从最左边的圆片开始。');
    return;
  }
  if (route.length) {
    const last = route.at(-1);
    const forward = (last + 1) % count;
    const backward = (last - 1 + count) % count;
    const next = direction ? (last + direction + count) % count : null;
    if (route.includes(index) || (next === null ? index !== forward && index !== backward : index !== next)) {
      miss(node, route.includes(index) ? '这片已经数过。' : '找沿着路线紧挨着的下一片。');
      return;
    }
    if (!direction) direction = index === forward ? 1 : -1;
  }
  route.push(index);
  K.sfx.tick(route.length);
  draw();
  if (route.length === count && round === 0) {
    K.star(1, board);
    K.levels(2, 1);
    K.say('数完一圈，换成一行再数。', 'ok');
    switcher.disabled = false;
  }
  if (route.length === count && round === 1) complete(2, reset);
}
function draw() {
  objects.replaceChildren();
  const step = Math.PI * 2 / count;
  for (let i = 0; i < count; i++) {
    const token = makeToken(i, route.includes(i), mark);
    const angle = i * step - Math.PI / 2;
    token.style.left = (round === 0 ? 574 + 167 * Math.cos(angle) : 175 + i * 114) + 'px';
    token.style.top = (round === 0 ? 204 + 143 * Math.sin(angle) : 203) + 'px';
    if (i === route[0]) token.classList.add('origin');
    token.disabled = route.length === count;
    objects.append(token);
  }
  objects.classList.toggle('linear', round === 1);
  K.$('#route-tally').textContent = String(route.length);
  K.$('#route-caption').textContent = round === 0 ? '先选一片当起点' : '从左往右，挨着数';
  switcher.disabled = round === 1 || route.length < count;
}
switcher.addEventListener('click', () => {
  if (stopDemo(reset)) return;
  round = 1;
  route = [];
  direction = 1;
  K.say('按一行的方向，再数一次。');
  draw();
});
function reset() {
  round = 0;
  route = [];
  direction = 0;
  resetKit(2, '选起点，沿着同一方向数。');
  draw();
}
K.onState = ({demo}) => {
  demonstration = true;
  round = 0;
  route = demo === 'start' ? [0] : [0,1,2];
  direction = demo === 'start' ? 0 : 1;
  draw();
};
startGame('圈起来不重数', reset, 2);
