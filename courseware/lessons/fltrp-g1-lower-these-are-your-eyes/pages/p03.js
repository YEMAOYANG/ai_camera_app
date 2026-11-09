(() => {
  'use strict';
  const title = '给模型的眼睛点亮计数';
  const panel = K.$('#eye-panel');
  const total = K.$('#count-total');
  const sound = K.$('#count-sound');
  const end = K.$('#count-end');
  const baby = K.$('#baby-picture img');
  const numberNames = ['一','二','三','四','五','六','七','八'];
  const lamps = numberNames.map((name) => {
    const lamp = K.el('button','eye-lamp',
      '<svg viewBox="0 0 124 62" aria-hidden="true"><path d="M5 31Q62-21 119 31Q62 83 5 31Z" fill="#fffaf0" stroke="#234758" stroke-width="5"/><circle cx="62" cy="31" r="16" fill="#315e72"/><circle cx="62" cy="31" r="8" fill="#173646"/><circle cx="57" cy="26" r="3" fill="#ffffff"/></svg>',panel);
    lamp.type = 'button';
    lamp.setAttribute('aria-label','第'+name+'只眼灯');
    return lamp;
  });
  let count = 0;
  let misses = 0;
  let active = false;
  let clip = null;
  K.hud({icon:'',title,levels:lamps.length});
  K.owl();
  K.ready({emoji:'',title,sub:'',btn:'start-btn'});

  function stopAudio() {
    if (clip) clip.pause();
    clip = null;
  }
  function replay() {
    stopAudio();
    const url = '__VOICE:p03-7__';
    if (!active || url.startsWith('__VOICE:')) return;
    clip = new Audio(url);
    const current = clip;
    current.play().then(() => sound.classList.remove('audio-error')).catch(() => {
      if (clip === current) sound.classList.add('audio-error');
    });
  }
  function paint() {
    total.value = String(count);
    lamps.forEach((lamp,index) => {
      lamp.classList.toggle('lit',index < count);
      lamp.classList.toggle('hinted',active && misses >= 3 && index === count);
      lamp.setAttribute('aria-pressed',String(index < count));
    });
    K.levels(lamps.length,count);
    end.hidden = !active || count !== lamps.length;
  }
  function begin() {
    count = 0;
    misses = 0;
    active = true;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    paint();
    K.say('先听问题，从上排左边开始。');
    replay();
  }
  lamps.forEach((lamp,index) => lamp.addEventListener('click',() => {
    if (!active || count === lamps.length) return;
    if (index !== count) {
      misses++;
      K.sfx.no();
      K.say(index < count ? '这只已经数过，找下一只。' : '沿着这一排，从左往右数。','no');
      paint();
      return;
    }
    count++;
    misses = 0;
    K.star(1,lamp);
    K.sfx.tick(count - 1);
    paint();
    K.say(count === lamps.length ? '八只眼睛都亮了！' : '亮了一只，接着数。','ok');
  }));
  end.addEventListener('click',() => {
    if (!active || count !== lamps.length) return;
    active = false;
    paint();
    stopAudio();
    K.finish({title:'八只眼睛都数到了',sub:'每一只都数了一遍。',again:begin});
  });
  K.onState = (state) => {
    if (Number.isInteger(state.demo)) {
      stopAudio();
      active = false;
      count = state.demo;
      misses = 0;
      paint();
    }
    if (state.handoff) begin();
  };
  K.$('#start-btn').addEventListener('click',begin);
  sound.addEventListener('click',replay);
  baby.addEventListener('error',() => {
    baby.hidden = true;
    baby.parentElement.classList.add('picture-error');
    K.say('宝宝图暂时打不开，右边的灯板还可以数。');
  });
  window.addEventListener('message',event => { if (event.data?.type === 'PAUSE_WIDGET_AUDIO') stopAudio(); });
  window.addEventListener('pagehide',stopAudio);
  paint();
})();
