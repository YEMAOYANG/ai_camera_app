(() => {
  'use strict';
  const title = '听问句，送图卡作回答';
  const trials = [
    ['one-foot','__VOICE:p05-17__'],['two-ears','__VOICE:p05-18__'],
    ['two-feet','__VOICE:p05-19__'],['one-ear','__VOICE:p05-20__']
  ];
  const cards = K.$$('.delivery-card');
  const byKey = new Map(cards.map(card => [card.dataset.card,card]));
  const slot = K.$('#delivery-slot');
  const output = K.$('#delivered-image');
  const next = K.$('#delivery-next');
  const sound = K.$('#delivery-sound');
  let round = 0;
  let misses = 0;
  let active = false;
  let accepted = false;
  let imageError = false;
  let clip = null;

  K.hud({icon:'',title,levels:trials.length});
  K.owl();
  K.ready({emoji:'',title,sub:'',btn:'start-btn'});
  function stopAudio() {
    if (clip) clip.pause();
    clip = null;
  }
  function replay() {
    stopAudio();
    if (!active || accepted || trials[round][1].startsWith('__VOICE:')) return;
    clip = new Audio(trials[round][1]);
    const current = clip;
    current.play().then(() => sound.classList.remove('audio-error')).catch(() => {
      if (clip === current) sound.classList.add('audio-error');
    });
  }
  function clearCard() {
    output.hidden = true;
    output.removeAttribute('src');
    slot.classList.remove('filled');
    cards.forEach(card => card.classList.remove('selected','hinted'));
  }
  function display(card) {
    clearCard();
    const image = card.querySelector('img');
    output.src = image.src;
    output.alt = image.alt;
    output.hidden = false;
    slot.classList.add('filled');
    card.classList.add('selected');
  }
  function setRound() {
    misses = 0;
    accepted = false;
    next.hidden = true;
    clearCard();
    K.levels(trials.length,round);
    K.say(imageError ? '图卡没有打开，请重新进入。' : '听一听，看看图卡上的圈。');
  }
  function begin() {
    active = true;
    round = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    setRound();
    replay();
  }
  cards.forEach(card => {
    card.querySelector('img').addEventListener('error',() => {
      imageError = true;
      card.disabled = true;
      K.say('图卡没有打开，请重新进入。','no');
    });
    card.addEventListener('click',() => {
      if (!active || accepted || imageError) return;
      if (card.dataset.card !== trials[round][0]) {
        misses++;
        K.sfx.no();
        K.shake(card);
        K.say(misses === 1 ? '再听一遍，看看圈在哪里。' : '还要听清指的是一个还是多个。','no');
        if (misses >= 3) byKey.get(trials[round][0]).classList.add('hinted');
        replay();
        return;
      }
      accepted = true;
      stopAudio();
      display(card);
      K.star(1,card);
      K.sfx.ok();
      K.say('收到图卡了！','ok');
      next.hidden = false;
    });
  });
  next.addEventListener('click',() => {
    if (!accepted) return;
    round++;
    if (round < trials.length) {
      setRound();
      replay();
      return;
    }
    active = false;
    accepted = false;
    next.hidden = true;
    K.levels(trials.length,trials.length);
    K.finish({title:'图卡都送到了',sub:'每张图都和声音对上了。',again:begin});
  });
  K.onState = (state) => {
    if (state.demo && !imageError) {
      stopAudio();
      active = false;
      accepted = false;
      next.hidden = true;
      display(byKey.get(state.demo));
    }
    if (state.handoff) begin();
  };
  K.$('#start-btn').addEventListener('click',begin);
  sound.addEventListener('click',replay);
  window.addEventListener('message',event => { if (event.data?.type === 'PAUSE_WIDGET_AUDIO') stopAudio(); });
  window.addEventListener('pagehide',stopAudio);
  setRound();
})();
