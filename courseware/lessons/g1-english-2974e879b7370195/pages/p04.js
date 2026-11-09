(function () {
  function makePlacement(answer) {
    return {
      answer,
      done: false,
      wrongs: 0,
      place(id) {
        if (this.done) return 'ignored';
        if (id === this.answer) {
          this.done = true;
          return 'correct';
        }
        this.wrongs++;
        return 'wrong';
      },
      reset() {
        this.done = false;
        this.wrongs = 0;
      },
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { makePlacement };
  if (typeof document === 'undefined') return;

  const model = makePlacement('place-on');
  const cat = K.$('#cat-mover');
  const bed = K.$('#bed-picture');
  const boxDemoCat = K.$('#box-demo-cat');
  const emptyBedSrc = bed.src;
  const targets = K.$$('.place-target');
  let selected = false;
  let demonstrating = false;
  let finishTimer;

  K.hud({ icon: '', title: '把小猫送到床上', levels: 1 });
  K.owl();

  function showBoxDemo(enabled) {
    demonstrating = enabled;
    boxDemoCat.classList.toggle('hide', !enabled);
    cat.classList.toggle('hide', enabled || model.done);
    targets.forEach(target => target.classList.toggle('hide', enabled || model.done));
    K.$('#place-prompt').textContent = enabled ? 'In the box.' : 'On the bed.';
    if (enabled) K.highlight('#box-picture');
    else K.$('#box-picture').classList.remove('teach-hl');
  }

  function reset() {
    clearTimeout(finishTimer);
    model.reset();
    selected = false;
    cat.classList.remove('selected', 'placed');
    cat.style.left = '60px';
    cat.style.top = '245px';
    bed.src = emptyBedSrc;
    showBoxDemo(false);
    K.$('#tip').style.display = 'none';
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(1, 0);
    K.say('听清位置，拖动小猫；也能先点再点。');
  }

  function place(target) {
    if (model.done || demonstrating || !target) return;
    if (model.place(target.id) === 'wrong') {
      selected = false;
      cat.classList.remove('selected');
      K.sfx.no();
      K.shake(cat);
      if (model.wrongs === 2) K.highlight('#bed-picture');
      if (model.wrongs >= 3) K.highlight('#place-on');
      K.say(model.wrongs === 1 ? '先停一停，看清床面和床底。' : '再听位置词，对着床找一找。', 'no');
      return;
    }

    K.star(1, cat);
    bed.src = '__IMG:on-bed__';
    cat.classList.remove('selected');
    showBoxDemo(false);
    K.$('#tip').style.display = 'none';
    bed.classList.remove('teach-hl');
    K.sfx.ok();
    K.levels(1, 1);
    K.say('小猫的位置和老师说的一样。', 'ok');
    finishTimer = setTimeout(() => K.finish({ title: '小猫安置好了', sub: '看清相对位置再回答', again: reset }), 1200);
  }

  function select() {
    if (model.done || demonstrating) return;
    selected = true;
    cat.classList.add('selected');
    K.say('现在点一个落点，让小猫过去。');
  }

  targets.forEach(target => target.addEventListener('click', () => {
    if (selected) place(target);
    else K.say('先点一下小猫，再点你选的位置。');
  }));
  K.drag(cat, {
    enabled: () => !model.done && !demonstrating,
    targets: () => targets,
    onTap: select,
    onDrop: (_, target) => place(target),
  });
  cat.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      select();
    }
  });

  K.onState = state => {
    if ('boxDemo' in state) showBoxDemo(state.boxDemo === true);
    if (state.pointOn) K.annotate('#place-on', 'on the bed');
  };
  K.$$('#play img').forEach(img => img.addEventListener('error', () => {
    K.$('#image-recovery').classList.remove('hide');
  }));
  K.$('#retry-pictures').addEventListener('click', () => {
    K.$('#image-recovery').classList.add('hide');
    K.$$('#play img').forEach(img => { img.src = img.src; });
  });
  K.onStart = reset;
  K.ready({ title: '把小猫送到床上', sub: '听位置，再摆放', emoji: '' });
})();
