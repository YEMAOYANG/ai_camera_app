(function () {
  'use strict';
  const K = window.K;
  const photos = K.$$('.route-photo');
  const stops = K.$$('.route-stop');
  const order = [1, 2, 0];
  const prompts = ['先找在家把课本放进包的图。','再找背好书包走出家门的图。','最后找孩子到了学校的图。'];
  const cueFiles = ['__VOICE:route-pack__','__VOICE:route-leave__','__VOICE:route-arrive__'];
  let step = 0, mistakes = 0, demo = false, locked = false, sound = null;
  K.hud({icon:'▤',title:'接起上学路线',levels:3});
  K.owl();

  function stopAudio() {
    if (!sound) return;
    sound.pause();
    sound = null;
  }
  function listen() {
    const cue = cueFiles[step];
    if (demo || locked || !cue || cue.startsWith('__VOICE:')) return;
    stopAudio();
    sound = new Audio(cue);
    sound.play().catch(() => K.say('声音暂时打不开，请大人帮忙。','no'));
  }
  function display(index, place) {
    const photo = photos[index];
    const stop = stops[place];
    photo.classList.add('placed');
    stop.classList.add('full');
    stop.querySelector('img')?.remove();
    stop.append(photo.querySelector('img').cloneNode());
  }
  function reset() {
    stopAudio();
    step = mistakes = 0;
    demo = locked = false;
    for (const photo of photos) photo.classList.remove('placed');
    for (const stop of stops) {
      stop.classList.remove('full');
      stop.querySelector('img')?.remove();
    }
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(3,0);
    K.say(prompts[0]);
  }
  function select(index, target) {
    if (demo || locked || photos[index].classList.contains('placed')) return;
    if (index !== order[step] || (target && target !== stops[step])) {
      mistakes++;
      K.sfx.no();
      K.shake(photos[index]);
      K.say(mistakes === 1 ? '看看孩子在哪里，再听一遍。' : prompts[step],'no');
      listen();
      return;
    }
    stopAudio();
    display(index,step);
    K.star(1,stops[step]);
    step++;
    mistakes = 0;
    K.levels(3,step);
    K.sfx.ok();
    if (step === 3) {
      locked = true;
      K.say('从家出发，到学校啦。','ok');
      setTimeout(() => K.finish({title:'走到学校了',sub:'今晚和家人一起准备书包。',again:reset}),1150);
    } else {
      K.say(prompts[step],'ok');
      setTimeout(listen,480);
    }
  }
  photos.forEach((photo,index) => {
    K.drag(photo,{onTap:() => select(index),targets:() => stops,onDrop:(_,target) => {
      if (target) select(index,target);
    }});
    photo.addEventListener('keydown',event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(index); }
    });
    const image = photo.querySelector('img');
    image.addEventListener('error',() => {
      image.alt = '图片暂时打不开，请请大人重新打开。';
      K.say('图片暂时打不开，请大人帮忙。','no');
    },{once:true});
  });
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) { reset(); return; }
    if (state.demo !== true) return;
    demo = true;
    const place = state.routeStep;
    if (Number.isInteger(place) && place >= 0 && place < order.length) display(order[place],place);
  };
  K.$('#route-hear').addEventListener('click',listen);
  window.addEventListener('pagehide',stopAudio);
  K.ready({title:'接起上学路线',sub:'听老师说，把照片放上路。'});
  K.$('#ready button').addEventListener('click',listen);
})();
