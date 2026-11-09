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
const tray = K.$('#pair-tray');
const groups = K.$('#pair-groups');
const sizes = [7, 6];
let round = 0;
let pairs = [];
let first = null;
let demonstration = false;
function pick(index, node) {
  if (stopDemo(reset)) return;
  if (pairs.flat().includes(index)) return miss(node, '这片已经找到同伴。');
  if (first === index) return miss(node, '还要选另一片。');
  if (first === null) {
    first = index;
    K.sfx.pick();
  } else {
    pairs.push([first,index]);
    first = null;
    K.sfx.ok();
  }
  draw();
}
function draw() {
  tray.replaceChildren();
  groups.replaceChildren();
  const paired = new Set(pairs.flat());
  for (let i = 0; i < sizes[round]; i++) {
    if (!paired.has(i)) tray.append(makeToken(i, i === first, pick));
  }
  for (const _pair of pairs) {
    const ring = document.createElement('div');
    ring.className = 'pair-outline';
    ring.append(makeDot(), makeDot());
    groups.append(ring);
  }
  K.$('#pair-result').textContent = pairs.length + ' 组';
}
function answer(odd, button) {
  if (stopDemo(reset)) return;
  const size = sizes[round];
  if (pairs.length !== Math.floor(size / 2)) return miss(tray, '再给没配成组的圆片找同伴。');
  if (odd !== (size % 2 === 1)) return miss(button, '看有没有没被配对的圆片。');
  if (round === 1) return complete(2, reset);
  K.star(1, button);
  K.levels(2, ++round);
  K.say('配对成功，再试一组。', 'ok');
  K.sfx.ok();
  pairs = [];
  first = null;
  draw();
}
K.$('#pair-no').addEventListener('click', event => answer(false, event.currentTarget));
K.$('#pair-yes').addEventListener('click', event => answer(true, event.currentTarget));
function reset() {
  round = 0;
  pairs = [];
  first = null;
  resetKit(2, '给圆片找同伴，两片一组。');
  draw();
}
K.onState = ({demo}) => {
  if (demo !== 'one') return;
  demonstration = true;
  round = 0;
  pairs = [[0,1]];
  first = null;
  draw();
};
startGame('两件一组找落单', reset, 2);
