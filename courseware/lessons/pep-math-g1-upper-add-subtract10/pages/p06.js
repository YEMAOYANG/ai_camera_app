(function () {
  const rounds = [[2,8,'join'], [3,7,'take-second'], [1,9,'take-first']];
  let level = 0, task = rounds[0], chosen = '', choices = [], demo = false, misses = 0, timer;
  K.hud({icon:'◈', title:'给算式配动作图', levels:rounds.length});
  K.owl();
  K.ready({emoji:'◈', title:'给算式配动作图', sub:'看两组灯片怎样合进或移出'});

  function group(parent, count, color) {
    const cluster = K.el('span','cluster','',parent);
    for (let i = 0; i < count; i++) K.el('i','lamp '+color,'',cluster);
    return cluster;
  }
  function formula() {
    const [a,b,mode] = task;
    if (mode === 'join') return a + ' + ' + b + ' = 10';
    return '10 − ' + (mode === 'take-first' ? a : b) + ' = ' + (mode === 'take-first' ? b : a);
  }
  function render() {
    const [a,b,mode] = task;
    K.$('#map-equation').textContent = formula();
    const board = K.$('#map-board'); board.replaceChildren();
    for (let i = 0; i < 10; i++) {
      const slot = K.el('span', 'slot', '', board);
      const shown = (mode !== 'join' || chosen) &&
        ((i < a && chosen !== 'take-first') || (i >= a && chosen !== 'take-second'));
      if (shown) {
        K.el('i', 'lamp ' + (i < a ? 'blue' : 'green'), '', slot);
      }
    }
    const cards = K.$('#action-cards'); cards.replaceChildren();
    for (const option of choices) {
      const card = K.el('button','card action-card','',cards);
      card.type = 'button'; card.disabled = demo || !!chosen; card.classList.toggle('selected', chosen === option);
      if (option === 'join') {
        group(card,a,'blue'); K.el('span','action-arrow','+',card); group(card,b,'green');
        card.setAttribute('aria-label','把'+a+'片和'+b+'片合起来');
      } else {
        const moved = option === 'take-first' ? a : b;
        const kept = 10 - moved;
        const keptColor = option === 'take-first' ? 'green' : 'blue';
        const whole = K.el('span','cluster whole-mini','',card);
        for (let i = 0; i < 10; i++) {
          const firstGroup = i < a;
          const remove = firstGroup === (option === 'take-first');
          K.el('i','lamp '+(firstGroup ? 'blue' : 'green')+(remove ? ' crossed' : ''),'',whole);
        }
        K.el('span','action-arrow','→',card);
        group(card,kept,keptColor);
        card.setAttribute('aria-label','从十片里拿走'+moved+'片');
      }
      card.onclick = () => choose(option);
    }
    K.levels(rounds.length,level);
  }
  function choose(option) {
    if (demo || chosen) return;
    if (option !== task[2]) {
      misses++; K.sfx.no(); K.say(misses === 1 ? '看看符号，说的是合起来，还是拿走？' : '再比对算式中的数和动作图里的灯片。', 'no');
      return;
    }
    chosen = option; render(); K.star(1,K.$('#map-board')); K.sfx.ok();
    K.say(option === 'join' ? '两组放在同一块板上，合成十。' : '拿走的格子空了，剩下的是另一组。','ok');
    timer = setTimeout(() => {
      level++;
      if (level === rounds.length) K.finish({title:'算式和动作配好啦',sub:'图上的动作给算式说明了意思。',again:reset});
      else load();
    },1050);
  }
  function load() {
    task = rounds[level]; chosen = ''; misses = 0;
    choices = K.shuffle(['join','take-first','take-second']); render(); K.say('看看这个算式，选同样意思的动作图。');
  }
  function reset() {
    clearTimeout(timer); level = 0; demo = false; K.stars = 0; K.$('#star-n').textContent='0'; load();
  }
  K.onStart=reset;
  K.onState = state => {
    if (state.play) {reset();return;}
    if (!state.demoJoin && !state.demoTake && !state.demoOther) return;
    clearTimeout(timer); demo = true; level = 0; K.stars = 0; K.$('#star-n').textContent='0';
    const mode=state.demoJoin ? 'join' : state.demoTake ? 'take-first' : 'take-second';
    task=[4,6,mode];chosen=mode;choices=['join','take-first','take-second'];render();K.say(mode === 'join' ? '这道加法把两部分合在一起。' : '这道减法从整板十片取走一个部分。');
  };
  load();
})();
