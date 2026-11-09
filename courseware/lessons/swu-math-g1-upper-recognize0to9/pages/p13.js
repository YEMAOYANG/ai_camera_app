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
const scale = K.$('#order-scale');
const cards = K.$('#order-cards');
const goals = [4, 8];
let round = 0;
let demonstration = false;
function draw(demoState) {
  scale.replaceChildren();
  cards.replaceChildren();
  K.drags = K.drags.filter(entry => entry.el.isConnected);
  const missing = demoState ? 6 : goals[round];
  let gap;
  for (let value = 0; value < 10; value++) {
    const tick = document.createElement('span');
    tick.className = 'tick' + (value === missing ? ' target-gap' : '');
    tick.textContent = value === missing && demoState !== 'reveal' ? '□' : String(value);
    if (value === missing) {
      gap = tick;
      if (demoState === 'mark') gap.classList.add('marked');
      if (demoState === 'reveal') gap.classList.add('success');
    }
    scale.append(tick);
  }
  const numbers = demoState ? [5, 6, 7] : round === 0 ? [5, 4, 3] : [8, 7, 9];
  numbers.forEach(number => {
    const button = makeChoice(number);
    cards.append(button);
    const choose = () => {
      if (stopDemo(reset)) return;
      if (number !== goals[round]) return miss(button, '沿着刻度，听听前后两个数。');
      gap.textContent = String(number);
      gap.classList.add('success');
      if (round === 1) return complete(2, reset);
      K.star(1, gap);
      K.levels(2, ++round);
      K.say('找到位置了，再来一个。', 'ok');
      K.sfx.ok();
      draw();
    };
    K.drag(button, {targets: () => [gap], onTap: choose, onDrop: (_, target) => {
      if (target) choose();
      else miss(button, '把数字拖到有边框的空位。');
    }});
    button.addEventListener('click', event => {
      if (event.detail === 0) choose();
    });
  });
}
function reset() {
  round = 0;
  resetKit(2, '沿刻度数，把数字放回空位。');
  draw();
}
K.onState = ({demo}) => {
  if (demo !== 'mark' && demo !== 'reveal') return;
  demonstration = true;
  round = 0;
  draw(demo);
};
startGame('在有序位置找空缺', reset, 2);
