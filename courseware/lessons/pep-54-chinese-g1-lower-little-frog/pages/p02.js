(() => {
  const K = window.K;
  const places = K.$$('.story-board figure');
  const buttons = K.$$('.story-choices button');
  const retry = K.$('#story-retry');
  const scenes = [
    {image:'__IMG:story-see__', alt:'晴天河边，青蛙蹲着'},
    {image:'__IMG:story-help__', alt:'青蛙捉到了稻苗旁的害虫'},
    {image:'__IMG:story-care__', alt:'孩子和大人从远处安静看青蛙'},
  ];
  const hints = ['想一想，课文开头介绍的是谁。','想一想，它给禾苗做了什么。','想一想，我们该怎样对待小青蛙。'];
  const broken = new Set();
  let order = [1,2,0];
  let next = 0;
  let misses = 0;

  function updateRetry() {
    retry.classList.toggle('hide', !Array.from(broken).some(image => !image.closest('button:disabled')));
  }
  function imageAt(image, key) {
    const scene = scenes[key];
    if (image.getAttribute('src') !== scene.image) {
      broken.delete(image);
      image.src = scene.image;
    }
    image.alt = scene.alt;
  }
  function draw() {
    places.forEach((place, i) => place.classList.toggle('active', i === next));
    K.levels(scenes.length, next);
    updateRetry();
  }
  function reset() {
    next = 0;
    misses = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    order = K.shuffle(scenes.map((_, i) => i));
    buttons.forEach((button, i) => {
      button.disabled = false;
      imageAt(button.querySelector('img'), order[i]);
      button.setAttribute('aria-label', scenes[order[i]].alt);
    });
    places.forEach(place => {
      const image = place.querySelector('img');
      broken.delete(image);
      image.removeAttribute('src');
      image.classList.add('hide');
    });
    draw();
    K.say('听老师说，再把图放进亮起的格子');
  }
  function choose(i, target) {
    const button = buttons[i];
    if (next === scenes.length || button.disabled || !retry.classList.contains('hide')) return;
    if (order[i] !== next || (target && target !== places[next])) {
      misses += 1;
      K.shake(button);
      K.sfx.no();
      K.say(hints[next], 'no');
      if (misses > 1) K.highlight('#' + places[next].id);
      return;
    }
    const placed = places[next].querySelector('img');
    imageAt(placed, next);
    placed.classList.remove('hide');
    K.star(1, button);
    K.sfx.ok();
    button.disabled = true;
    next += 1;
    misses = 0;
    draw();
    if (next === scenes.length) {
      K.finish({title:'三张图排好了',sub:'看着图，说说小青蛙的故事',again:reset});
    } else {
      K.say('再找下一幅图', 'ok');
    }
  }

  K.$$('.story img').forEach(image => {
    image.addEventListener('error', () => {
      if (image.hasAttribute('src')) broken.add(image);
      updateRetry();
    });
    image.addEventListener('load', () => { broken.delete(image); updateRetry(); });
  });
  retry.addEventListener('click', () => broken.forEach(image => { image.src = image.getAttribute('src'); }));
  buttons.forEach((button, i) => {
    button.addEventListener('click', () => choose(i));
    K.drag(button, {
      targets:() => places,
      enabled:() => !button.disabled,
      onDrop:(_button, target) => { if (target) choose(i, target); },
    });
  });
  K.hud({icon:'',title:'把三幅图排好',levels:3});
  K.owl();
  K.onStart = reset;
  reset();
  K.ready({emoji:'',title:'把三幅图排好',sub:'先听，再排'});
})();
