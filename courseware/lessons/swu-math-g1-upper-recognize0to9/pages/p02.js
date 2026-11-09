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
const units = [2, 3];
let round = 0;
let selected = new Set();
let demonstration = false;
const unitGroups = K.$('#unit-groups');

function draw() {
  unitGroups.replaceChildren();
  K.$('#unit-mode').textContent = round === 0 ? '按单件数' : '按整组数';
  K.$('#unit-preview').textContent = String(selected.size);
  units.forEach((size, group) => {
    const tile = round === 0 ? document.createElement('div') : document.createElement('button');
    tile.className = 'tile unit-tile';
    if (round === 1) {
      tile.type = 'button';
      tile.setAttribute('aria-label', '第' + (group + 1) + '组');
      tile.classList.toggle('chosen', selected.has(group));
      tile.addEventListener('click', () => mark(group, tile));
    }
    for (let i = 0; i < size; i++) {
      if (round === 0) {
        const index = group * 3 + i;
        tile.append(makeToken(index, selected.has(index), mark));
      } else {
        tile.append(makeDot());
      }
    }
    unitGroups.append(tile);
  });
}
function mark(index, node) {
  if (stopDemo(reset)) return;
  if (selected.has(index)) {
    miss(node, '这个已经记过一次。');
    return;
  }
  selected.add(index);
  K.sfx.tick(selected.size);
  draw();
}
function reset() {
  round = 0;
  selected = new Set();
  resetKit(2, '一个圆片记一次。');
  draw();
}
K.$('#unit-check').addEventListener('click', () => {
  if (stopDemo(reset)) return;
  if (selected.size !== (round === 0 ? 5 : 2)) {
    miss(unitGroups, round === 0 ? '还有没点过的圆片。' : '看看还有哪个框没有标记。');
    return;
  }
  if (round === 1) return complete(2, reset);
  K.star(1, unitGroups);
  K.levels(2, ++round);
  K.say('这次数框，一个框记一次。', 'ok');
  K.sfx.ok();
  selected.clear();
  draw();
});
K.onState = ({demo}) => {
  demonstration = true;
  round = demo === 'group' ? 1 : 0;
  selected = new Set([0]);
  draw();
};
startGame('一次数一个单位', reset, 2);
