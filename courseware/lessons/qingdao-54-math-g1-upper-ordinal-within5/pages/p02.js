(() => {
  const exhibits = ['drum', 'trumpet', 'piano', 'harp', 'tambourine'].map(name => K.$('#row-' + name));
  const task = K.$('#row-task');
  const ranks = K.$('#row-ranks');
  const choices = Array.from(ranks.querySelectorAll('button'));
  const rounds = [
    { mode: 'locate', rank: 4, hint: '从门边往右数，点第四件。' },
    { mode: 'rank', rank: 2, hint: '从门边往右数，小号在第几位？' },
    { mode: 'locate', rank: 3, hint: '还是从门边往右数，点第三件。' }
  ];
  let level = 0;
  let mistakes = 0;
  let demo = false;
  let locked = false;
  let transition;

  function dots(container, count) {
    container.replaceChildren(...Array.from({ length: count }, () => {
      const dot = document.createElement('i');
      dot.className = 'rank-dot';
      dot.setAttribute('aria-hidden', 'true');
      return dot;
    }));
  }

  function draw(focus = 0) {
    const round = rounds[level];
    const isRank = round.mode === 'rank' && !demo;
    exhibits.forEach((button, index) => {
      button.disabled = demo || isRank || locked;
      button.classList.toggle('active', focus === index + 1 || (isRank && round.rank === index + 1));
      button.classList.remove('success');
    });
    ranks.hidden = !isRank;
    if (isRank) task.replaceChildren(exhibits[round.rank - 1].querySelector('img').cloneNode());
    else dots(task, demo ? focus : round.rank);
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
    draw();
    K.say(rounds[level].hint);
  }

  function choose(rank, button) {
    if (demo || locked) return;
    if (rank !== rounds[level].rank) {
      mistakes += 1;
      K.shake(button);
      K.sfx.no();
      if (mistakes > 1) K.highlight('#row-origin');
      K.say(mistakes === 1 ? '回到门边，一件接一件数。' : '先找到第一件，再沿箭头数到要找的位置。', 'no');
      return;
    }
    locked = true;
    draw();
    exhibits[rank - 1].classList.add('success');
    K.star(1);
    K.levels(rounds.length, level + 1);
    K.sfx.ok();
    K.say('展签亮了，位置找对了。', 'ok');
    transition = setTimeout(() => {
      if (level === rounds.length - 1) {
        K.finish({ title: '展签亮起来了', sub: '从门边出发，挨着数就能找到位置。', again: reset });
      } else {
        level += 1;
        mistakes = 0;
        locked = false;
        draw();
        K.say(rounds[level].hint);
      }
    }, 650);
  }

  choices.forEach(button => {
    dots(button, Number(button.dataset.rank));
    button.addEventListener('click', () => choose(Number(button.dataset.rank), button));
  });
  exhibits.forEach((button, index) => button.addEventListener('click', () => choose(index + 1, button)));
  K.hud({ icon: '◆', title: '从门边依次数', levels: rounds.length });
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) return reset();
    if (state.demo === true) {
      clearTimeout(transition);
      demo = true;
      draw(state.rank || 0);
      K.say('跟着老师的灯光，从门边往右看。');
    }
  };
  draw();
  K.ready({ emoji: '◆', title: '从门边依次数', sub: '给乐器点亮展签。' });
})();
