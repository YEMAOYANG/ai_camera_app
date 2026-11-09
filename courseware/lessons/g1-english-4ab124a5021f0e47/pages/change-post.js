(function () {
  'use strict';
  const guide = K.$('#station-guide');
  const card = K.$('#sighting-card');
  const birds = {left: K.$('#post-left'), right: K.$('#post-right')};
  const locations = ['right', 'left'];
  let round = 0;
  let misses = 0;
  let busy = false;
  let demo = false;
  let timer;

  K.hud({icon: '◉', title: '换个站位再指', levels: locations.length});
  K.owl();
  K.ready({emoji: '◉', title: '换个站位再指', sub: '每一关都找离观察员较远的鸟'});

  function trackPicture(node) {
    const image = node.querySelector('img');
    image.onload = () => node.classList.remove('image-unavailable');
    image.onerror = () => node.classList.add('image-unavailable');
    if (image.hasAttribute('src') && image.complete && !image.naturalWidth) image.onerror();
  }
  [guide, card, birds.left, birds.right].forEach(trackPicture);

  function paint(side) {
    guide.classList.toggle('station-right', side === 'right');
    card.classList.remove('stored');
    Object.values(birds).forEach((bird) => {
      bird.disabled = demo || busy;
      bird.classList.remove('chosen');
    });
    K.levels(locations.length, round);
  }

  function saveBird(side) {
    const chosen = birds[side];
    const source = chosen.querySelector('img');
    const preview = card.querySelector('img');
    preview.alt = source.alt;
    preview.src = source.src;
    card.querySelector('.picture-fallback').textContent = source.alt;
    card.classList.add('stored');
    chosen.classList.add('chosen');
  }

  function reset() {
    clearTimeout(timer);
    K.$$('.cf,.flystar').forEach((effect) => effect.remove());
    round = 0;
    misses = 0;
    busy = false;
    demo = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    paint(locations[0]);
    K.say('先看观察员站哪儿，再找远处的鸟。');
  }

  function choose(side) {
    if (demo || busy || round >= locations.length) return;
    const speakerSide = locations[round];
    const distantSide = speakerSide === 'left' ? 'right' : 'left';
    if (side !== distantSide) {
      misses += 1;
      K.sfx.no();
      K.shake(birds[side]);
      const hints = ['先找说话的观察员，她站在哪儿？', '从观察员那里看看两边，哪边更远？', '顺着较长的那段路再看一眼。'];
      K.say(hints[Math.min(misses, 3) - 1], 'no');
      if (misses === 2) K.highlight('#station-guide');
      if (misses >= 3) K.highlight('#' + birds[distantSide].id);
      return;
    }
    busy = true;
    misses = 0;
    Object.values(birds).forEach((bird) => { bird.disabled = true; });
    saveBird(side);
    K.sfx.ok();
    K.star(1, birds[side]);
    round += 1;
    K.levels(locations.length, round);
    K.say('远处的鸟进了观察记录。', 'ok');
    timer = setTimeout(() => {
      if (round === locations.length) {
        K.finish({title: '两次都找到了', sub: '换了站位，远近也要重新看。', again: reset});
        return;
      }
      busy = false;
      paint(locations[round]);
      K.say('观察员换站了，再找离她远的鸟。');
    }, 950);
  }

  birds.left.onclick = () => choose('left');
  birds.right.onclick = () => choose('right');
  K.onStart = reset;
  K.onState = (state) => {
    if (state.demoPost || state.demoSighting) {
      clearTimeout(timer);
      demo = true;
      busy = false;
      round = 0;
      paint('left');
      if (state.demoSighting) saveBird('right');
    }
    if (state.play) reset();
  };
  paint(locations[0]);
})();
