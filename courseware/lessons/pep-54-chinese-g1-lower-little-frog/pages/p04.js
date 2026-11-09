(() => {
  const K = window.K;
  const board = K.$('#rice-picture img');
  const buttons = K.$$('#rice-choices button');
  const retry = K.$('#rice-retry');
  const plates = [
    {src:'__IMG:scene-rice__', alt:'田里细细长长的禾苗'},
    {src:'__IMG:scene-insect__', alt:'害虫在咬稻苗的叶子'},
    {src:'__IMG:story-help__', alt:'青蛙捉到了稻苗旁的害虫'},
    {src:'__IMG:story-see__', alt:'青蛙蹲在河边'},
  ];
  const levels = [
    {picture:3, choices:[0,1], answer:0, prompt:'先找出田里长的禾苗', hint:'看看哪幅图是一株株长着细叶的小苗'},
    {picture:0, choices:[2,1], answer:1, prompt:'再找出会咬苗的害虫', hint:'看看哪幅图有虫和叶子上的咬口'},
    {picture:1, choices:[2,3], answer:0, prompt:'最后找出青蛙怎样帮忙', hint:'看看哪幅图里的青蛙正在动'},
  ];
  const teacher = [0,1,2,0];
  const broken = new Set();
  let level = 0;
  let demo = null;
  let misses = 0;
  let visible = [];

  function updateRetry() {
    retry.classList.toggle('hide', !visible.some(image => broken.has(image)));
    buttons.forEach(button => { button.disabled = demo !== null || level === levels.length || !retry.classList.contains('hide'); });
  }
  function show(image, key) {
    const plate = plates[key];
    if (image.getAttribute('src') !== plate.src) {
      broken.delete(image);
      image.src = plate.src;
    }
    image.alt = plate.alt;
  }
  function draw() {
    const active = levels[level];
    const controls = demo === null && !!active;
    K.$('#rice-choices').classList.toggle('hide', !controls);
    show(board, demo === null ? (active ? active.picture : 2) : teacher[demo]);
    visible = [board];
    if (controls) buttons.forEach((button, index) => {
      const image = button.querySelector('img');
      show(image, active.choices[index]);
      visible.push(image);
      button.setAttribute('aria-label', image.alt);
    });
    K.levels(levels.length, level);
    updateRetry();
  }
  function reset() {
    level = 0;
    demo = null;
    misses = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    draw();
    K.say(levels[0].prompt);
  }
  function choose(index) {
    const active = levels[level];
    if (buttons[index].disabled || !active) return;
    if (index !== active.answer) {
      misses += 1;
      K.shake(buttons[index]);
      K.sfx.no();
      K.say(active.hint, 'no');
      if (misses > 1) K.highlight('#rice-picture');
      return;
    }
    K.star(1, buttons[index]);
    K.sfx.ok();
    level += 1;
    misses = 0;
    draw();
    if (level === levels.length) {
      K.finish({title:'找到田里的小帮手',sub:'青蛙吃害虫，帮着保护禾苗',again:reset});
    } else {
      K.say(levels[level].prompt, 'ok');
    }
  }

  [board, ...buttons.map(button => button.querySelector('img'))].forEach(image => {
    image.addEventListener('error', () => { broken.add(image); updateRetry(); });
    image.addEventListener('load', () => { broken.delete(image); updateRetry(); });
  });
  retry.addEventListener('click', () => visible.filter(image => broken.has(image)).forEach(image => { image.src = image.getAttribute('src'); }));
  buttons.forEach((button,index) => { button.onclick = () => choose(index); });
  K.hud({icon:'',title:'看它帮了什么',levels:3});
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.riceStep === false) reset();
    else if (Number.isInteger(state.riceStep) && state.riceStep >= 0 && state.riceStep < teacher.length) {
      demo = state.riceStep;
      draw();
      K.highlight('#rice-picture');
    }
  };
  reset();
  K.ready({emoji:'',title:'看它帮了什么',sub:'先听，再找图'});
})();
