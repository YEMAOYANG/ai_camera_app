(() => {
  const shelves = ['one', 'two', 'three', 'four'].map(key => K.$('#rack-' + key));
  const direction = K.$('#rack-direction');
  const task = K.$('#rack-task');
  const rounds = [
    { up: false, rank: 3, hint: '从上面的星灯往下数，点第三格。' },
    { up: true, rank: 2, hint: '从下面的门铃往上数，点第二格。' },
    { up: true, rank: 4, hint: '还是从下面往上数，这次点第四格。' }
  ];
  let level = 0;
  let mistakes = 0;
  let demo = false;
  let locked = false;
  let transition;

  function draw(round, highlighted) {
    direction.classList.toggle('up', round.up);
    direction.setAttribute('aria-label', round.up ? '从下往上数' : '从上往下数');
    task.replaceChildren(...Array.from({ length: round.rank }, () => {
      const dot = document.createElement('i');
      dot.className = 'rack-dot';
      dot.setAttribute('aria-hidden', 'true');
      return dot;
    }));
    shelves.forEach((shelf, index) => {
      shelf.disabled = demo || locked;
      shelf.classList.toggle('active', index === highlighted);
      shelf.classList.remove('success');
    });
  }

  function reset() {
    clearTimeout(transition);
    level = 0;
    mistakes = 0;
    demo = false;
    locked = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(rounds.length, 0);
    draw(rounds[level]);
    K.say(rounds[level].hint);
  }

  function choose(index) {
    if (demo || locked) return;
    const round = rounds[level];
    const position = round.up ? shelves.length - index : index + 1;
    if (position !== round.rank) {
      mistakes += 1;
      K.shake(shelves[index]);
      K.sfx.no();
      if (mistakes > 1) K.highlight(round.up ? '#rack-bottom' : '#rack-top');
      K.say(mistakes === 1 ? '先看箭头从哪头出发。' : '挨着第一格继续数，数到要求的那一格。', 'no');
      return;
    }
    locked = true;
    draw(round);
    shelves[index].classList.add('success');
    K.star(1);
    K.levels(rounds.length, level + 1);
    K.sfx.ok();
    K.say('找到这格了。', 'ok');
    transition = setTimeout(() => {
      if (level === rounds.length - 1) {
        K.finish({ title: '展格全找到了', sub: '先找起点，再沿箭头逐格数。', again: reset });
      } else {
        level += 1;
        mistakes = 0;
        locked = false;
        draw(rounds[level]);
        K.say(rounds[level].hint);
      }
    }, 650);
  }

  shelves.forEach((shelf, index) => shelf.addEventListener('click', () => choose(index)));
  K.hud({ icon: '◆', title: '上下两头找展格', levels: rounds.length });
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) return reset();
    if (state.demo === true) {
      clearTimeout(transition);
      demo = true;
      draw({ up: state.up === true, rank: state.rank || 1 }, state.mark);
      K.say('老师示范，从亮着的一端开始数。');
    }
  };
  draw(rounds[0]);
  K.ready({ emoji: '◆', title: '上下两头找展格', sub: '看箭头，点亮展格。' });
})();
