(function () {
  const partners = [K.$('#block-partner-a'), K.$('#block-partner-b')];
  const pieces = K.$$('.bridge-piece');
  const ticket = K.$('#block-ticket');
  const speaker = K.$('#block-call');
  let placed = 0;
  let holder = 0;
  let misses = 0;
  let demonstrating = false;
  let broken = false;
  let finishTimer;
  let audio;

  function stopAudio() {
    const previous = audio;
    audio = null;
    if (previous) previous.pause();
  }

  function replay() {
    if (demonstrating || broken || placed === pieces.length) return;
    stopAudio();
    if (!speaker.dataset.clip) {
      K.say('玩法声音没有载入。', 'no');
      return;
    }
    const clip = new Audio(speaker.dataset.clip);
    audio = clip;
    function clear() { if (audio === clip) audio = null; }
    function failed() {
      if (audio !== clip) return;
      clear();
      K.say('玩法声音没有载入，请重新打开本页。', 'no');
    }
    clip.addEventListener('ended', clear, {once: true});
    clip.addEventListener('error', failed, {once: true});
    clip.play().catch(failed);
  }

  function render() {
    ticket.dataset.holder = String(holder);
    pieces.forEach((piece, index) => { piece.hidden = index >= placed; });
    K.levels(pieces.length, placed);
  }

  function reset() {
    clearTimeout(finishTimer);
    stopAudio();
    placed = 0;
    holder = 0;
    misses = 0;
    demonstrating = false;
    K.star(-K.stars);
    render();
    K.say('点拿着接力牌的伙伴。');
  }

  function choose(index) {
    if (demonstrating || broken || placed === pieces.length) return;
    if (index !== holder) {
      misses += 1;
      K.sfx.no();
      K.shake(partners[index]);
      K.say(misses === 1 ? '这位伙伴先等一等，看看接力牌。' : '看看牌离哪位伙伴更近。', 'no');
      if (misses > 1) K.highlight('#block-ticket');
      return;
    }
    stopAudio();
    placed += 1;
    holder = 1 - holder;
    misses = 0;
    render();
    K.star(1, partners[index]);
    K.sfx.ok();
    K.say(placed === pieces.length ? '大家轮流，小桥搭好了。' : '放好一块，接力牌传给伙伴。', 'ok');
    if (placed === pieces.length) {
      finishTimer = setTimeout(() => K.finish({title: '小桥搭好了', sub: '一人一块，轮流动手', again: reset}), 860);
    }
  }

  partners.forEach((partner, index) => partner.addEventListener('click', () => choose(index)));
  speaker.addEventListener('click', replay);

  function showImageError() {
    broken = true;
    stopAudio();
    K.$('#block-media-problem').classList.remove('hide');
    partners.forEach((button) => { button.disabled = true; });
  }

  [ticket, ...partners.map((button) => button.querySelector('img'))].forEach((image) => {
    image.addEventListener('error', showImageError, {once: true});
    if (image.complete && !image.naturalWidth) showImageError();
  });

  K.hud({icon: '', title: '积木接力', levels: pieces.length});
  K.owl();
  K.ready({emoji: '搭', title: '积木接力', sub: '看接力牌，轮流搭小桥'});
  K.onStart = reset;
  K.onState = (state) => {
    if (state.play) { reset(); return; }
    if (!['holder', 'place', 'pass'].includes(state.demo)) return;
    clearTimeout(finishTimer);
    stopAudio();
    demonstrating = true;
    placed = state.demo === 'holder' ? 0 : 1;
    holder = state.demo === 'pass' ? 1 : 0;
    render();
  };
  window.addEventListener('pagehide', stopAudio);
  render();
})();
