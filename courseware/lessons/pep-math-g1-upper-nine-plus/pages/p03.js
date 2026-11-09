(() => {
  const model = K.$('#split-model');
  const options = K.$('#split-options');
  const equation = K.$('#split-equation');
  let addend, demo, selected, misses, finishTimer;
  K.hud({ title: '找出合适的分法', icon: '10', levels: 1 });
  K.owl();

  function group(parent, count, warm, added = false) {
    const box = K.el('span', warm ? 'group warm' : 'group', '', parent);
    for (let i = 0; i < count; i++) K.el('i', added && i === count - 1 ? 'disc moved' : 'disc', '', box);
  }

  function render() {
    model.replaceChildren();
    group(model, selected ? 10 : 9, false, selected);
    K.el('span', '', '＋', model);
    group(model, selected ? addend - 1 : addend, true);
    options.replaceChildren();
    for (const first of [2, 0, 1]) {
      const choice = K.el('button', 'split-option', '', options);
      choice.type = 'button';
      choice.disabled = demo || selected;
      choice.setAttribute('aria-label', '分成' + first + '枚和' + (addend - first) + '枚');
      group(choice, first, true);
      group(choice, addend - first, true);
      if (selected && first === 1) choice.classList.add('chosen');
      choice.onclick = () => {
        if (first !== 1) {
          misses++;
          K.shake(choice);
          K.sfx.no();
          K.say(misses === 1 ? '九离十差几？看看左边这一小组。' : '往十格里的空位放一放，想想要挪几枚。', 'no');
          if (misses > 1) K.highlight('#split-model');
          return;
        }
        selected = true;
        K.levels(1, 1);
        K.star(1);
        K.sfx.ok();
        render();
        K.say('拿一枚去凑十，原来那组还剩两枚。', 'ok');
        finishTimer = setTimeout(() => K.finish({ title: '分对了', sub: '一枚已经算进十里', again: reset }), 1100);
      };
    }
    equation.textContent = selected ? '10 ＋ ' + (addend - 1) + ' ＝ ' + (9 + addend) : '9 ＋ ' + addend + ' ＝ ？';
  }

  function reset() {
    clearTimeout(finishTimer);
    addend = 3;
    demo = selected = false;
    misses = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(1, 0);
    K.say('点一张图，选出从盘外拿一枚的分法。');
    render();
  }
  K.onStart = reset;
  K.onState = state => {
    if (state.resetTask) reset();
    if (state.demoRegroup === true || state.demoRegroup === false) {
      demo = true;
      selected = state.demoRegroup;
      addend = 5;
      render();
    }
  };
  reset();
  K.ready({ title: '找出合适的分法', sub: '一枚进托盘，其余留在外面', emoji: '10' });
})();
