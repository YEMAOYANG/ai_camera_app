(function () {
  'use strict';
  const K = window.K;
  const cards = K.$$('.photo');
  const pocket = K.$('#autumn-pocket');
  const hear = K.$('#ground-replay');
  const cues = ['先找穿着外套的孩子。','再找还长在枝头的黄叶。','最后找已经飘离树枝的叶子。'];
  const clips = ['/api/classroom-media/__STAGE__/media/tts-p02-17-edbe53090e27bd8c49566f7b0ac03b73ee7a95702472fd5f5dad2bb18dc349a4.wav','/api/classroom-media/__STAGE__/media/tts-p02-18-c88afa3c4aa81bcd5588ff167799bddcb3c61cc552e669ce79c3327921f1d2e8.wav','/api/classroom-media/__STAGE__/media/tts-p02-19-61d6c280af4be009741aa4ba2d2acc425e227811bd1674a5b77b365cec8fcdca.wav'];
  let next = 0, misses = 0, demo = false, complete = false, currentClip = null;
  K.hud({icon:'▤',title:'把秋信装好',levels:3});
  K.owl();
  function stop() {
    if (!currentClip) return;
    currentClip.pause();
    currentClip = null;
  }
  function listen() {
    if (demo || complete) return;
    stop();
    currentClip = new Audio(clips[next]);
    currentClip.play().catch(() => K.say('声音暂时打不开，请大人帮忙。','no'));
  }
  function addPicture(index) {
    cards[index].classList.add('stamped');
    const image = cards[index].querySelector('img').cloneNode();
    image.alt = cards[index].getAttribute('aria-label');
    pocket.append(image);
  }
  function reset() {
    stop();
    next = misses = 0;
    demo = complete = false;
    cards.forEach(card => card.classList.remove('stamped'));
    pocket.replaceChildren();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(3,0);
    K.say(cues[0]);
  }
  function choose(index) {
    if (demo || complete) return;
    if (index !== next) {
      misses++;
      K.shake(cards[index]);
      K.sfx.no();
      K.say(misses === 1 ? '听一遍，再比较画面里的位置。' : cues[next],'no');
      listen();
      return;
    }
    stop();
    addPicture(next);
    next++;
    misses = 0;
    K.star(1,pocket);
    K.sfx.ok();
    K.levels(3,next);
    if (next < 3) {
      K.say(cues[next],'ok');
      setTimeout(listen, 480);
    } else {
      complete = true;
      K.say('三张图装进秋信了。','ok');
      setTimeout(() => K.finish({title:'秋信装好了',sub:'照着图，说一说你看见的变化。',again:reset}), 1350);
    }
  }
  cards.forEach((card,index) => card.addEventListener('click',() => choose(index)));
  hear.addEventListener('click',listen);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) { reset(); return; }
    if (state.demo !== true) return;
    demo = true;
    if (Number.isInteger(state.picture) && state.picture >= 0 && state.picture < cards.length) {
      pocket.replaceChildren();
      cards.forEach(card => card.classList.remove('stamped'));
      addPicture(state.picture);
    }
  };
  for (const card of cards) card.querySelector('img').addEventListener('error', () => {
    card.style.background = '#f7dbae';
    card.querySelector('img').alt = '图暂时打不开，请重试';
    K.say('图片暂时打不开，点原图位置试试。','no');
    card.addEventListener('click',() => {
      const image = card.querySelector('img');
      image.src = image.getAttribute('src');
    },{once:true,capture:true});
  },{once:true});
  window.addEventListener('pagehide',stop);
  K.ready({title:'把秋信装好',sub:'听老师说，找一张图放进去。'});
  K.$('#ready button').addEventListener('click',listen);
})();
