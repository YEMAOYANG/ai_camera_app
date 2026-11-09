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
const tray = K.$('#match-tray');
const choices = K.$('#match-choices');
const plus = K.$('#match-add');
let round = 0;
let amount = 2;
let marked = new Set();
let demonstration = false;
function draw() {
  tray.replaceChildren();
  choices.replaceChildren();
  K.$('#match-caption').textContent = round === 0 ? '逐个标记，再选数字' : '先添一片，再选新数字';
  K.$('#match-marks').textContent = String(marked.size);
  for (let i = 0; i < amount; i++) {
    tray.append(makeToken(i, marked.has(i), (index, node) => {
      if (stopDemo(reset)) return;
      if (marked.has(index)) return miss(node, '已经点过这一片。');
      marked.add(index);
      K.sfx.tick(marked.size);
      draw();
    }));
  }
  const values = round === 0 ? [3, 2, 4] : [4, 6, 5];
  values.forEach(number => {
    const button = makeChoice(number);
    button.addEventListener('click', () => {
      if (stopDemo(reset)) return;
      if (round === 1 && amount === 4) return miss(plus, '先添一片，再来数。');
      if (marked.size !== amount) return miss(tray, '先把圆片一个一个点完。');
      if (number !== amount) return miss(button, '沿着圆片重新点数。');
      if (round === 1) return complete(2, reset);
      K.star(1, button);
      K.levels(2, ++round);
      amount = 4;
      marked.clear();
      K.sfx.ok();
      K.say('这回先添一片。', 'ok');
      draw();
    });
    choices.append(button);
  });
  plus.disabled = round === 0 || amount === 5;
}
plus.addEventListener('click', () => {
  if (stopDemo(reset)) return;
  amount = 5;
  K.sfx.pick();
  draw();
});
function reset() {
  round = 0;
  amount = 2;
  marked = new Set();
  resetKit(2, '数完圆片，再选同样多的数字。');
  draw();
}
K.onState = ({demo}) => {
  demonstration = true;
  round = demo === 'added' ? 1 : 0;
  amount = demo === 'added' ? 5 : 2;
  marked = new Set(demo === 'added' ? [0,1,2,3,4] : [0]);
  draw();
};
startGame('把数和数量配上', reset, 2);
