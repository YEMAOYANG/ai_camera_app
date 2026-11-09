(() => {
  const K = window.K;
  const context = K.$('#family-context img');
  const character = K.$('#family-character');
  const options = K.$('#family-options');
  const buttons = K.$$('#family-options button');
  const nextButton = K.$('#family-next');
  const retry = K.$('#family-retry');
  const cues = [
    {src:'__IMG:scene-river__', alt:'河水很清，能看见水底', glyph:'清', choices:['日','氵','目'], answer:1, hint:'这幅图要我们留意水'},
    {src:'__IMG:scene-sun__', alt:'太阳出来了，是个晴天', glyph:'晴', choices:['日','氵','讠'], answer:0, hint:'这幅图要我们留意太阳'},
    {src:'__IMG:scene-eyes__', alt:'青蛙的一双大眼睛', glyph:'睛', choices:['忄','日','目'], answer:2, hint:'这幅图要我们留意用什么看'},
    {src:'__IMG:scene-mood__', alt:'积木桥搭好，小朋友很高兴', glyph:'情', choices:['目','忄','氵'], answer:1, hint:'想一想小朋友心里有什么感受'},
    {src:'__IMG:scene-request__', alt:'小朋友开口请伙伴让一让', glyph:'请', choices:['讠','忄','日'], answer:0, hint:'想一想小朋友是怎样开口的'},
  ];
  const radicalNames = {'日':'日字旁','氵':'三点水','目':'目字旁','忄':'竖心旁','讠':'言字旁'};
  const teacher = [
    {image:0, glyph:'青'},
    {image:0, glyph:'清'},
    {image:1, glyph:'晴'},
    {image:2, glyph:'睛'},
    {image:3, glyph:'情'},
    {image:4, glyph:'请'},
  ];
  let level = 0;
  let demo = null;
  let joined = false;
  let misses = 0;
  let failedImage = false;

  function updateRetry() {
    retry.classList.toggle('hide', !failedImage);
    nextButton.disabled = failedImage;
    buttons.forEach(button => { button.disabled = failedImage || demo !== null || joined; });
  }
  function draw() {
    const active = cues[level];
    const frame = demo === null ? active : cues[teacher[demo].image];
    if (context.getAttribute('src') !== frame.src) {
      failedImage = false;
      context.src = frame.src;
    }
    context.alt = frame.alt;
    character.textContent = demo !== null ? teacher[demo].glyph : joined ? active.glyph : '青';
    options.classList.toggle('hide', demo !== null || joined);
    nextButton.classList.toggle('hide', demo !== null || !joined);
    buttons.forEach((button,i) => {
      const radical = active.choices[i];
      button.textContent = radical;
      button.setAttribute('aria-label', radicalNames[radical]);
    });
    K.levels(cues.length, level + (joined ? 1 : 0));
    updateRetry();
  }
  function reset() {
    level = 0;
    demo = null;
    joined = false;
    misses = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    draw();
    K.say('看这幅图，给青选一个左边的偏旁');
  }
  function choose(index) {
    if (buttons[index].disabled) return;
    const active = cues[level];
    if (index !== active.answer) {
      misses += 1;
      K.shake(buttons[index]);
      K.sfx.no();
      K.say(active.hint, 'no');
      if (misses > 1) K.highlight('#family-context');
      return;
    }
    K.star(1, buttons[index]);
    K.sfx.ok();
    joined = true;
    misses = 0;
    draw();
    K.say('偏旁和青合成了一个字，试着念一念', 'ok');
  }

  context.addEventListener('error', () => { failedImage = true; updateRetry(); });
  context.addEventListener('load', () => { failedImage = false; updateRetry(); });
  retry.addEventListener('click', () => { context.src = context.getAttribute('src'); });
  buttons.forEach((button,index) => { button.onclick = () => choose(index); });
  nextButton.onclick = () => {
    if (demo !== null || !joined || failedImage) return;
    if (level === cues.length - 1) {
      K.finish({title:'青的五个伙伴找齐了',sub:'偏旁帮我们想字义',again:reset});
    } else {
      level += 1;
      joined = false;
      draw();
      K.say('看新的一幅图，想想它和什么有关');
    }
  };
  K.hud({icon:'',title:'找出青的五个伙伴',levels:5});
  K.owl();
  K.onStart = reset;
  K.onState = state => {
    if (state.familyDemo === false) reset();
    else if (Number.isInteger(state.familyDemo) && state.familyDemo >= 0 && state.familyDemo < teacher.length) {
      demo = state.familyDemo;
      draw();
      K.highlight('#family-character');
    }
  };
  reset();
  K.ready({emoji:'',title:'找出青的五个伙伴',sub:'先听，再把字合起来'});
})();
