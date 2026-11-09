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
const whole = 7;
const left = K.$('#split-left');
const right = K.$('#split-right');
const transfer = K.$('#split-transfer');
const record = K.$('#split-record');
let moved = 0;
let demonstration = false;
function draw() {
  left.replaceChildren();
  right.replaceChildren();
  for (let i = 0; i < whole; i++) {
    const node = makeToken(i, i === moved && moved > 0, (index, button) => {
      if (stopDemo(reset)) return;
      if (index <= moved) return miss(button, '圆片要从右框向左框移。');
      move();
    });
    (i <= moved ? left : right).append(node);
  }
  record.replaceChildren();
  for (let step = 0; step <= moved; step++) {
    const entry = document.createElement('div');
    entry.className = 'split-entry';
    const leftAmount = step + 1;
    const rightAmount = whole - leftAmount;
    entry.setAttribute('aria-label', '左边 ' + leftAmount + '，右边 ' + rightAmount);
    for (const amount of [leftAmount, rightAmount]) {
      const label = document.createElement('span');
      label.textContent = String(amount);
      entry.append(label);
    }
    record.append(entry);
  }
}
function move() {
  if (stopDemo(reset) || moved >= 3) return;
  moved++;
  K.sfx.drop();
  draw();
  K.levels(3, moved);
  if (moved === 3) return complete(3, reset);
  K.star(1, left);
  K.say('左边多一片，右边少一片。', 'ok');
}
transfer.addEventListener('click', move);
function reset() {
  moved = 0;
  resetKit(3, '保持总数，每次从右边移一片。');
  draw();
}
K.onState = ({demo}) => {
  demonstration = true;
  moved = demo === 'first' ? 0 : 1;
  draw();
};
startGame('移动一件找下一种分法', reset, 3);
