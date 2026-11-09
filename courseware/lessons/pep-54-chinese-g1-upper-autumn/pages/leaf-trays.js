(function () {
  'use strict';
  const K = window.K;
  const trays = K.$$('.tray');
  const destination = K.$('#leaf-drop');
  const picture = destination.querySelector('img');
  const blank = '__IMG:empty-tray__';
  const descriptions = ['找一片叶子，放到右边。','找一片片叶子，放到右边。'];
  const clips = ['/api/classroom-media/__STAGE__/media/tts-p07-16-377250cc544ce14a517157e5b85dbfa79cc4a6f519da40a3cbab0c8518b7a75a.wav','/api/classroom-media/__STAGE__/media/tts-p07-17-fe3a6eed073ca6cb403cc5b8aa36b7db0b44295bdd0b2040ae155b183f7988ee.wav'];
  let next = 0, errors = 0, demo = false, moving = false, player = null;
  K.hud({icon:'▤',title:'银杏采集盘',levels:2});
  K.owl();
  function stop() {
    if (!player) return;
    player.pause();
    player = null;
  }
  function hear() {
    if (demo || moving || next >= clips.length) return;
    stop();
    player = new Audio(clips[next]);
    player.play().catch(() => K.say('声音暂时打不开，请大人帮忙。','no'));
  }
  function show(src, filled, alt) {
    destination.classList.toggle('filled',filled);
    picture.src = src;
    picture.alt = alt;
  }
  function reset() {
    stop();
    next = errors = 0;
    demo = moving = false;
    show(blank,false,'空采集盘');
    K.levels(2,0);
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.say(descriptions[0]);
  }
  function choose(index) {
    if (moving || demo) return;
    if (index !== next) {
      errors++;
      K.sfx.no();
      K.shake(trays[index]);
      K.say(errors === 1 ? '再比较每张图里有几片。' : descriptions[next],'no');
      hear();
      return;
    }
    moving = true;
    stop();
    const photo = trays[index].querySelector('img');
    show(photo.src,true,photo.alt);
    K.star(1,destination);
    K.sfx.ok();
    next++;
    errors = 0;
    K.levels(2,next);
    K.say(index === 0 ? '一片叶子，从左边到了右边。' : '一片片叶子都来到了采集盘。','ok');
    setTimeout(() => {
      if (next === 2) {
        K.finish({title:'叶子收进秋信了',sub:'把一片和一片片说给大人听。',again:reset});
        return;
      }
      moving = false;
      show(blank,false,'空采集盘');
      K.say(descriptions[next]);
      hear();
    },1350);
  }
  trays.forEach((tray,index) => {
    K.drag(tray,{onTap:() => choose(index),targets:() => [destination],onDrop:(_,target) => {
      if (target === destination) choose(index);
    }});
    tray.addEventListener('keydown',event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(index); }
    });
  });
  K.$('#leaf-replay').addEventListener('click',hear);
  K.onStart = reset;
  K.onState = state => {
    if (state.demo === false) { reset(); return; }
    if (state.demo !== true) return;
    demo = true;
    if (state.picture !== 0 && state.picture !== 1) return;
    const photo = trays[state.picture].querySelector('img');
    show(photo.src,true,photo.alt);
  };
  for (const image of K.$$('img',K.$('#play'))) image.addEventListener('error',() => {
    image.alt = '图暂时打不开，请请大人重新打开。';
    K.say('图暂时打不开，请大人重新打开。','no');
  },{once:true});
  window.addEventListener('pagehide',stop);
  K.ready({title:'银杏采集盘',sub:'点一下，或把叶子图拖进右边的盘。'});
  K.$('#ready button').addEventListener('click',hear);
})();
