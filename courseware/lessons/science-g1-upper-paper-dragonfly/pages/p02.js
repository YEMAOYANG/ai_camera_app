(() => {
  const K = window.K;
  const fields = ['快慢', '路线', '动作'];
  const choices = [K.$('#predict-same'), K.$('#predict-different')];
  const ledger = K.$('#predict-ledger');
  const save = K.$('#predict-save');
  let level = 0;
  let choice = null;
  let misses = 0;
  let demo = false;

  function drawing(step, different) {
    const patterns = [
      ['M61 30v64m84-64v64', 'M61 30v64m84-64v36'],
      ['M61 27v68m84-68v68', 'M61 27v68m84-68q39 22 0 44q-27 14 0 24'],
      ['M61 28v67m84-67v67', 'M61 28v67m85-12a24 24 0 1 1 15-29'],
    ];
    return '<svg viewBox="0 0 210 128" aria-hidden="true">'
      + '<path d="M28 112h154" stroke="#b0cec3" stroke-width="4"/>'
      + '<path d="' + patterns[step][different] + '" stroke="#237978" stroke-width="9" fill="none" stroke-linecap="round"/>'
      + '<circle cx="61" cy="24" r="10" fill="#f2b853"/><circle cx="145" cy="24" r="10" fill="#d95e53"/>'
      + (step === 2 && different ? '<path d="M158 44l9 17-18 2" fill="#237978"/>' : '')
      + '</svg>';
  }

  function show() {
    K.levels(3, level);
    choice = null;
    misses = 0;
    K.$('#predict-topic').textContent = fields[level] || '猜想已记录';
    choices.forEach((button, index) => {
      button.innerHTML = drawing(Math.min(level, 2), index);
      button.setAttribute('aria-label', (fields[level] || '动作') + (index ? '不一样' : '一样'));
      button.classList.remove('selected');
      button.disabled = demo || level === 3;
    });
    save.disabled = demo || level === 3;
    K.say(level === 3 ? '猜想留好了，试飞后再来比' : '点一幅猜想图，再放进记录夹');
  }

  function reset() {
    level = 0;
    demo = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.$$('.predict-slot').forEach((slot) => {
      slot.replaceChildren();
      slot.classList.remove('stored');
    });
    show();
  }

  function select(index) {
    if (demo || level >= 3) return;
    choice = index;
    choices.forEach((button, n) => button.classList.toggle('selected', n === index));
    K.sfx.pick();
  }

  function store() {
    if (demo || level >= 3) return;
    if (choice === null) {
      misses += 1;
      K.sfx.no();
      K.shake(ledger);
      if (misses > 1) K.highlight('#predict-choices');
      K.say('先点一幅图，两种猜想都能记录', 'no');
      return;
    }
    const slot = K.$('#predict-record-' + (level + 1));
    slot.innerHTML = drawing(level, choice);
    slot.classList.add('stored');
    K.star(1, slot);
    K.sfx.ok();
    level += 1;
    show();
    if (level === 3) K.finish({title: '猜想记录好了', sub: '等试飞后，看看与你想的是否一样', again: reset});
  }

  choices.forEach((button, index) => {
    button.onclick = () => select(index);
    K.drag(button, {
      enabled: () => !demo && level < 3,
      targets: () => [ledger],
      onTap: () => select(index),
      onDrop: (_button, target) => { if (target) { select(index); store(); } },
    });
  });
  save.onclick = store;
  K.hud({icon: '', title: '先把猜想存下来', levels: 3});
  K.owl();
  K.onStart = reset;
  K.onState = (state) => {
    if (state.predictDemo === false) reset();
    if (state.predictDemo === true) {
      reset();
      demo = true;
      show();
      const sample = K.$('#predict-record-1');
      sample.innerHTML = drawing(0, 1);
      sample.classList.add('stored');
      K.say('示范：把一幅猜想图放进夹子');
    }
  };
  show();
  K.ready({emoji: '↻', title: '先把猜想存下来', sub: '听老师说，挑一幅图'});
})();
