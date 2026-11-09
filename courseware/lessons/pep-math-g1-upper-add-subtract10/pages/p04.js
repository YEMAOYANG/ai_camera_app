(function () {
  const rounds = [[1,9,1], [7,3,7], [5,5,5]];
  let level = 0, parts = rounds[0], taken = -1, demo = false, misses = 0, timer;
  K.hud({icon:'◈', title:'整盒拿走一组', levels:rounds.length});
  K.owl();
  K.ready({emoji:'◈', title:'整盒拿走一组', sub:'点要拿走的一组，看盒里剩几片'});

  function render() {
    const whole = K.$('#whole-box'), tray = K.$('#removed-tray');
    whole.replaceChildren(); tray.replaceChildren();
    const strip = K.el('span', 'cluster', '', tray);
    for (let side = 0; side < 2; side++) {
      const n = parts[side];
      const group = K.el('button', 'group', '', whole);
      group.type = 'button'; group.id = side ? 'take-second' : 'take-first';
      group.classList.toggle('moved', side === taken);
      group.setAttribute('aria-label', side === taken ? '这组已拿走' : '拿走' + n + '片');
      group.disabled = demo || taken >= 0;
      const inside = K.el('span', 'cluster', '', group);
      for (let i = 0; i < n; i++) K.el('i', 'lamp ' + (side ? 'green' : 'blue'), '', side === taken ? strip : inside);
      group.onclick = () => choose(side);
    }
    K.$('#take-equation').textContent = '10 − ' + parts[2] + ' = ' + (taken < 0 ? '?' : parts[1 - taken]);
    K.levels(rounds.length, level);
  }
  function choose(side) {
    if (demo || taken >= 0) return;
    if (parts[side] !== parts[2]) {
      misses++; K.sfx.no(); K.say(misses === 1 ? '先数你选的这一组，再听要拿走几片。' : '减号后面的数，告诉你拿走几片。', 'no');
      return;
    }
    taken = side; render(); K.star(1, K.$('#whole-box')); K.sfx.ok();
    K.say('这组已经移到盒外，数盒里留下的灯片。', 'ok');
    timer = setTimeout(() => {
      level++;
      if (level === rounds.length) K.finish({title:'能找出剩下的一组', sub:'先有整体，再减拿走的部分。', again:reset});
      else load();
    }, 1050);
  }
  function load() {
    parts = rounds[level]; taken = -1; misses = 0; render();
    K.say('整盒原有十片，这次拿走' + parts[2] + '片。');
  }
  function reset() {
    clearTimeout(timer); level = 0; demo = false; K.stars = 0;
    K.$('#star-n').textContent = '0'; load();
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.play) { reset(); return; }
    if (!state.demo && !state.demoFirst && !state.demoSecond) return;
    clearTimeout(timer); demo = true; level = 0; K.stars = 0; K.$('#star-n').textContent = '0';
    parts = [4,6,state.demoSecond ? 6 : 4]; taken = state.demoSecond ? 1 : state.demoFirst ? 0 : -1;
    render(); K.say(taken < 0 ? '蓝组四片，绿组六片，整盒十片。' : '盒外是拿走的，盒内是剩下的。');
  };
  load();
})();
