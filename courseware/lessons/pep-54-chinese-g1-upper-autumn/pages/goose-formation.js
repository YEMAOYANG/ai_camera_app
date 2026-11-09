(function () {
  'use strict';
  const K = window.K;
  const sky = K.$('#flight-sky');
  const choices = K.$$('.flight-choice');
  const prompts = ['先选像人字一样分两边的照片。','再选排成一条横线的照片。'];
  const clips = ['/api/classroom-media/__STAGE__/media/tts-p09-16-f89df0c478e0c06ee41fd6fef92af1145516345ebbd9d6a607609dd63276598a.wav','/api/classroom-media/__STAGE__/media/tts-p09-17-44f67a5e3895ff7e073ea58c072dcb7a00d777cca9fa77981249869d3fbb15bf.wav'];
  const layout = {
    scatter:[[14,26],[23,60],[36,36],[47,71],[62,30],[73,64],[86,46]],
    ren:[[50,20],[40,38],[30,56],[20,74],[60,38],[70,56],[80,74]],
    yi:[[16,45],[27,45],[38,45],[50,45],[62,45],[73,45],[84,45]]
  };
  let next = 0, misses = 0, busy = false, demo = false, player = null;
  K.hud({icon:'▤',title:'大雁换队形',levels:2});
  K.owl();
  const birds = layout.scatter.map(() => {
    const bird = new Image();
    bird.src = '__IMG:goose__';
    bird.alt = '';
    bird.addEventListener('error', () => K.say('大雁图片暂时打不开，请大人帮忙。','no'),{once:true});
    sky.append(bird);
    return bird;
  });
  function position(key) {
    const points = layout[key];
    if (!points) return;
    sky.dataset.formation = key;
    birds.forEach((bird,index) => {
      bird.style.left = points[index][0] + '%';
      bird.style.top = points[index][1] + '%';
    });
  }
  function stop() {
    if (!player) return;
    player.pause();
    player = null;
  }
  function hear() {
    if (demo || busy || next >= clips.length) return;
    stop();
    player = new Audio(clips[next]);
    player.play().catch(() => K.say('声音暂时打不开，请大人帮忙。','no'));
  }
  function reset() {
    stop();
    next = misses = 0;
    busy = demo = false;
    position('scatter');
    choices.forEach(choice => choice.classList.remove('picked'));
    K.levels(2,0);
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.say(prompts[0]);
  }
  function choose(index) {
    if (busy || demo) return;
    if (index !== next+1) {
      misses++;
      K.shake(choices[index]);
      K.sfx.no();
      K.say(misses === 1 ? '沿着每张图里的雁群看一看。' : prompts[next],'no');
      hear();
      return;
    }
    stop();
    busy = true;
    choices.forEach(choice => choice.classList.remove('picked'));
    choices[index].classList.add('picked');
    position(index === 1 ? 'ren' : 'yi');
    next++;
    misses = 0;
    K.star(1,choices[index]);
    K.sfx.ok();
    K.levels(2,next);
    K.say(index === 1 ? '雁群展开成了两边。' : '大雁排成一条横线了。','ok');
    setTimeout(() => {
      if (next === 2) {
        K.finish({title:'雁阵照片收齐了',sub:'一会儿排这一种，一会儿排那一种。',again:reset});
        return;
      }
      busy = false;
      K.say(prompts[next]);
      hear();
    },1350);
  }
  choices.forEach((choice,index) => choice.addEventListener('click',() => choose(index)));
  K.$('#flight-replay').addEventListener('click',hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) { reset(); return; }
    if (state.demo !== true) return;
    demo = true;
    position(state.formation);
  };
  for (const image of K.$$('img',K.$('#flight-photos'))) image.addEventListener('error',() => {
    image.alt = '图暂时打不开，请大人重新打开。';
    K.say('图片暂时打不开，请大人帮忙。','no');
  },{once:true});
  position('scatter');
  window.addEventListener('pagehide',stop);
  K.ready({title:'大雁换队形',sub:'听老师说，选照片让大雁变一变。'});
  K.$('#ready button').addEventListener('click',hear);
})();
