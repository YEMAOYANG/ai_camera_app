(() => {
  const rail = K.$('#p03-rail');
  const pot = K.$('#p03-pot');
  const arrow = K.$('#p03-dir');
  const path = [8, 9, 10, 9];
  const tiles = [];
  let step = 0;
  let misses = 0;
  let demo = false;
  let done = false;
  let animation;
  let timer;
  K.hud({title:'花盆走数轨',icon:'0—10',levels:3});
  K.owl();
  K.$('img', pot).addEventListener('error', () => pot.classList.add('failed'));

  function show(index, backward) {
    tiles.forEach((tile, i) => {
      tile.disabled = demo || done;
      tile.classList.toggle('active', i === index);
      tile.setAttribute('aria-pressed', String(i === index));
    });
    pot.style.left = (24 + index * 100) + 'px';
    arrow.textContent = backward ? '⟵' : '⟶';
    arrow.classList.toggle('backward', backward);
  }

  function choose(index, tile) {
    if (done || demo) return;
    if (index !== path[step + 1]) {
      misses++;
      K.sfx.no();
      K.shake(tile);
      K.say(misses === 1 ? '看箭头，花盆每次只挪一格。' : '从花盆下方开始，朝箭头那边找紧挨的一格。', 'no');
      if (misses > 1) K.highlight('#p03-dir');
      return;
    }
    step++;
    misses = 0;
    done = step === path.length - 1;
    K.levels(3, step);
    show(index, step >= 2);
    K.sfx.tick(step);
    if (done) {
      K.star(1, tile);
      K.say('十往回走一格，回到九。', 'ok');
      timer = setTimeout(() => K.finish({title:'数轨走通了',sub:'十紧挨在九后面',again:reset}), 1100);
    } else {
      K.say(step === 2 ? '到十啦。箭头掉头，往回走一格。' : '到了九。沿着箭头再向前一格。', 'ok');
    }
  }

  for (let i = 0; i <= 10; i++) {
    const tile = K.el('button', 'p03-number', String(i), rail);
    tile.id = 'p03-number-' + i;
    tile.onclick = () => choose(i, tile);
    tiles.push(tile);
  }
  function reset() {
    clearInterval(animation);
    clearTimeout(timer);
    demo = false;
    done = false;
    step = 0;
    misses = 0;
    show(path[0], false);
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(3, 0);
    K.say('顺着箭头点紧挨着的一格。');
  }
  const sections = {
    'forward-first': [0, 5],
    'forward-last': [6, 10],
    'backward-first': [10, 6],
    'backward-last': [5, 0]
  };
  function run(section) {
    clearInterval(animation);
    demo = true;
    const [start, end] = sections[section];
    const backward = start > end;
    const increment = backward ? -1 : 1;
    let index = start;
    show(index, backward);
    K.say(backward ? '沿着数轨往回数。' : '沿着数轨向前数。');
    animation = setInterval(() => {
      index += increment;
      show(index, backward);
      if (index === end) clearInterval(animation);
    }, 390);
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.resetTask) reset();
    if (state.demoOrigin) {
      demo = true;
      show(0, false);
      K.say('花盆在零的位置。');
    }
    if (Object.hasOwn(sections, state.demoTrack)) run(state.demoTrack);
  };
  reset();
  K.ready({title:'花盆走数轨',sub:'看箭头，每次走一格',emoji:'0—10'});
})();
