(function () {
  'use strict';
  const K = window.K;
  const places = K.$$('.activity-place');
  const cards = K.$$('.activity-card');
  const assignment = [1,0];
  const directions = '先点一张图，再点它要去的地方。也可以拖过去。';
  const guidance = '__VOICE:activity-directions__';
  let selected = null, count = 0, misses = 0, demo = false, locked = false, clip = null;
  K.hud({icon:'▤',title:'给校园活动配照片',levels:2});
  K.owl();

  function stopAudio() {
    if (!clip) return;
    clip.pause();
    clip = null;
  }
  function hear() {
    if (demo || locked || guidance.startsWith('__VOICE:')) return;
    stopAudio();
    clip = new Audio(guidance);
    clip.play().catch(() => K.say('声音暂时打不开，请大人帮忙。','no'));
  }
  function show(card, place) {
    const image = cards[card].querySelector('img').cloneNode();
    image.classList.add('saved-photo');
    places[place].querySelector('.saved-photo')?.remove();
    places[place].append(image);
    places[place].classList.add('assigned');
    cards[card].classList.add('assigned');
  }
  function reset() {
    stopAudio();
    selected = null;
    count = misses = 0;
    demo = locked = false;
    for (const card of cards) card.classList.remove('selected','assigned');
    for (const place of places) {
      place.classList.remove('assigned');
      place.querySelector('.saved-photo')?.remove();
    }
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(2,0);
    K.say(directions);
  }
  function choose(card) {
    if (demo || locked || cards[card].classList.contains('assigned')) return;
    selected = card;
    cards.forEach((item,index) => item.classList.toggle('selected',index === card));
    K.sfx.pick();
    K.say('再点它要去的地方。');
  }
  function assign(card, place) {
    if (demo || locked || card === null || cards[card].classList.contains('assigned')) return;
    if (assignment[card] !== place) {
      misses++;
      K.sfx.no();
      K.shake(cards[card]);
      K.say(misses === 1 ? '仔细看，照片里的手正在做什么？' : '想一想，是在学新本领，还是在照顾班里的东西？','no');
      hear();
      return;
    }
    stopAudio();
    show(card,place);
    cards[card].classList.remove('selected');
    selected = null;
    misses = 0;
    count++;
    K.levels(2,count);
    K.star(1,places[place]);
    K.sfx.ok();
    K.say(place === 0 ? '跟着学搭桥，学会一个新本领。' : '给班里的花浇水，是在做力所能及的劳动。','ok');
    if (count === 2) {
      locked = true;
      setTimeout(() => K.finish({title:'照片都找到位置了',sub:'想一件能为大家做的小事。',again:reset}),1150);
    }
  }
  cards.forEach((card,index) => {
    K.drag(card,{onTap:() => choose(index),targets:() => places,onDrop:(_,target) => {
      if (target) assign(index,places.indexOf(target));
    }});
    card.addEventListener('keydown',event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(index); }
    });
  });
  places.forEach((place,index) => place.addEventListener('click',() => assign(selected,index)));
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) { reset(); return; }
    if (state.demo !== true) return;
    demo = true;
    const card = state.activityCard;
    if (Number.isInteger(card) && card >= 0 && card < assignment.length) show(card,assignment[card]);
  };
  for (const image of K.$$('img',K.$('#play'))) image.addEventListener('error',() => {
    image.alt = '图片暂时打不开，请大人重新打开。';
    K.say('图片暂时打不开，请大人帮忙。','no');
  },{once:true});
  K.$('#activity-hear').addEventListener('click',hear);
  window.addEventListener('pagehide',stopAudio);
  K.ready({title:'给校园活动配照片',sub:'听一听，选照片，找到它的位置。'});
  K.$('#ready button').addEventListener('click',hear);
})();
