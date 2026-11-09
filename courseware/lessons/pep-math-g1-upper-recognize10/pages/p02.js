(() => {
  const rack = K.$('#p02-rack');
  const cells = K.$('#p02-cells');
  const tray = K.$('#p02-tray');
  const groups = K.$('#p02-groups');
  const choices = K.$('#p02-choices');
  const pots = [];
  const slots = [];
  let count = 6;
  let misses = 0;
  let done = false;
  let timer;
  K.hud({title:'把花架摆满', icon:'10', levels:2});
  K.owl();

  function pot(parent) {
    const unit = K.el('span', 'p02-pot', '<img src="__IMG:seedling__" alt="一盆幼苗"><i data-semantic-diagram="一盆对应一个点"></i>', parent);
    K.$('img', unit).addEventListener('error', () => unit.classList.add('failed'));
    return unit;
  }

  for (let i = 0; i < 10; i++) {
    const slot = K.el('div', 'p02-cell', null, cells);
    slots.push(pot(slot));
  }
  for (let i = 0; i < 4; i++) {
    const button = K.el('button', 'p02-source', null, tray);
    button.id = 'p02-source-' + (i + 1);
    button.setAttribute('aria-label', '将这盆幼苗摆上架');
    pot(button);
    pots.push(button);
    button.onclick = () => {
      if (done || button.disabled) return;
      button.disabled = true;
      button.classList.add('placed');
      slots[count].hidden = false;
      count++;
      K.sfx.tick(count);
      if (count === 10) {
        K.levels(2, 1);
        choices.hidden = false;
        K.say('满架有多少盆？选出这个数。');
      } else {
        K.say('再给一个空格摆上一盆。');
      }
    };
  }

  function renderRack() {
    slots.forEach((slot, i) => { slot.hidden = i >= count; });
    groups.replaceChildren();
  }

  function reset() {
    clearTimeout(timer);
    count = 6;
    misses = 0;
    done = false;
    tray.hidden = false;
    choices.hidden = true;
    K.$$('.p02-choices button').forEach(button => { button.disabled = false; });
    pots.forEach(button => {
      button.disabled = false;
      button.classList.remove('placed');
    });
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(2, 0);
    renderRack();
    K.say('点一盆，就摆进一个空格。');
  }

  choices.onclick = event => {
    const button = event.target.closest('button');
    if (done || !button) return;
    if (Number(button.dataset.number) !== count) {
      misses++;
      K.sfx.no();
      K.shake(choices);
      K.say(misses === 1 ? '用手指从头数，每盆只数一次。' : '架上一排五盆，两排一样多，再数数。', 'no');
      if (misses > 1) K.highlight('#p02-rack');
      return;
    }
    done = true;
    K.$$('.p02-choices button').forEach(option => { option.disabled = true; });
    K.star(1, button);
    K.levels(2, 2);
    K.sfx.ok();
    K.say('两排摆满，正好十盆。', 'ok');
    timer = setTimeout(() => K.finish({title:'满架十盆',sub:'一格一盆，摆满就是十',again:reset}), 900);
  };
  K.onStart = reset;
  K.onState = state => {
    if (state.resetTask) reset();
    if (Number.isInteger(state.demoFill)) {
      count = state.demoFill;
      tray.hidden = true;
      choices.hidden = true;
      renderRack();
      K.say(count === 9 ? '先看架上已有九盆。' : '九盆再添一盆，满架是十盆。');
    }
    if (state.demoGroups === 2 || state.demoGroups === 5) {
      groups.replaceChildren();
      K.say(state.demoGroups === 2 ? '每两盆圈成一组。' : '每五盆圈成一组。');
      for (let i = 0; i < 10 / state.demoGroups; i++) {
        K.el('span', 'p02-band p02-band-' + state.demoGroups, null, groups);
      }
    }
  };
  reset();
  K.ready({title:'把花架摆满', sub:'一个空格摆一盆', emoji:'10'});
})();
