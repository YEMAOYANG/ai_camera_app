(function () {
  'use strict';
  const pictures = {
    satchel: {src: '__IMG:satchel__', label: '蓝色布包'},
    tote: {src: '__IMG:tote__', label: '浅紫色提袋'},
    cap: {src: '__IMG:cap__', label: '橙色棒球帽'},
    hat: {src: '__IMG:hat__', label: '绿色针织帽'},
  };
  const rounds = [
    {choices: ['hat', 'cap', 'satchel'], answer: 'satchel'},
    {choices: ['tote', 'hat', 'cap'], answer: 'tote'},
  ];
  const demonstration = {choices: ['cap', 'satchel', 'hat'], answer: 'satchel'};
  const cards = ['#bag-card-a', '#bag-card-b', '#bag-card-c'].map((id) => K.$(id));
  const rack = K.$('#bag-rack');
  let round = 0;
  let misses = 0;
  let busy = false;
  let demo = false;
  let timer;

  K.hud({icon: '◉', title: '给观察员找包', levels: rounds.length});
  K.owl();
  K.ready({emoji: '◉', title: '给观察员找包', sub: '听老师说，点能装东西的包'});

  function assignPicture(node, key) {
    const picture = pictures[key];
    const image = node.querySelector('img');
    node.classList.remove('image-unavailable');
    image.alt = picture.label;
    node.querySelector('.picture-fallback').textContent = picture.label;
    image.onerror = () => node.classList.add('image-unavailable');
    image.onload = () => node.classList.remove('image-unavailable');
    image.src = picture.src;
    if (node.tagName === 'BUTTON') node.setAttribute('aria-label', picture.label);
  }

  function paint(item) {
    rack.classList.remove('stored');
    cards.forEach((card, index) => {
      assignPicture(card, item.choices[index]);
      card.classList.remove('chosen');
      card.disabled = demo || busy;
    });
    K.levels(rounds.length, round);
  }

  function putOnRack(key) {
    assignPicture(rack, key);
    rack.classList.add('stored');
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
    paint(rounds[0]);
    K.say('听到 bag，就把包送到备品台。');
  }

  function choose(index) {
    if (demo || busy || round >= rounds.length) return;
    const item = rounds[round];
    const card = cards[index];
    if (item.choices[index] !== item.answer) {
      misses += 1;
      K.sfx.no();
      K.shake(card);
      const hints = ['想一想，哪件东西能装物品？', '找一找袋口和能提起来的带子。', '沿着亮起来的袋口再看一眼。'];
      K.say(hints[Math.min(misses, 3) - 1], 'no');
      if (misses >= 3) K.highlight('#' + cards[item.choices.indexOf(item.answer)].id);
      return;
    }
    busy = true;
    misses = 0;
    cards.forEach((choice) => { choice.disabled = true; });
    card.classList.add('chosen');
    putOnRack(item.answer);
    K.sfx.ok();
    K.star(1, card);
    round += 1;
    K.levels(rounds.length, round);
    K.say('包已经放到备品台。', 'ok');
    timer = setTimeout(() => {
      if (round === rounds.length) {
        K.finish({title: '观察包备好了', sub: '听见 bag，就找能装东西的包。', again: reset});
        return;
      }
      busy = false;
      paint(rounds[round]);
      K.say('换一组，还是找包。');
    }, 950);
  }

  cards.forEach((card, index) => { card.onclick = () => choose(index); });
  K.onStart = reset;
  K.onState = (state) => {
    if (state.demoBag || state.demoPacked) {
      clearTimeout(timer);
      demo = true;
      busy = false;
      round = 0;
      paint(demonstration);
      if (state.demoPacked) {
        cards[1].classList.add('chosen');
        putOnRack(demonstration.answer);
      }
    }
    if (state.play) reset();
  };
  paint(rounds[0]);
})();
