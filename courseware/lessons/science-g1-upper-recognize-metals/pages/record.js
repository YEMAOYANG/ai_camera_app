(() => {
  const photo = K.$('#record-photo');
  const image = K.$('#record-image');
  const result = K.$('#record-result');
  const copy = K.$('#record-copy');
  const retry = K.$('#record-retry');
  const pockets = {known:K.$('#record-known'),unknown:K.$('#record-unknown')};
  const buttons = {known:K.$('#record-confirmed'),unknown:K.$('#record-pending')};
  const rounds = [
    {image:'__IMG:window__',alt:'观察单确认窗框是金属的窗户',answer:'known',instruction:'窗框的材料已经查清楚了，照片放哪儿？',clue:'刚才的观察单告诉了我们窗框的材料。'},
    {image:'__IMG:painted-box__',alt:'只看见橙色表面的盒子',answer:'unknown',instruction:'只看见橙色盒子的表面，照片放哪儿？',clue:'目前只看见颜色，还没有查到盒子的材料。'},
  ];
  const bridge = {image:'__IMG:bridge__',alt:'显示桥面下钢梁的大桥示意图'};
  let level = 0;
  let miss = 0;
  let locked = false;
  let demo = false;
  let timer;
  K.hud({icon:'',title:'把证据放进记录卡',levels:2});
  K.owl();
  K.ready({emoji:'',title:'把证据放进记录卡',sub:'看观察结果，选合适的记录袋'});

  function setControls() {
    const disabled = demo || locked || !retry.classList.contains('hide');
    Object.values(buttons).forEach(button => {button.disabled = disabled;});
    photo.disabled = disabled;
  }

  function render(item) {
    clearTimeout(timer);
    locked = false;
    miss = 0;
    image.src = item.image;
    image.alt = item.alt;
    copy.src = item.image;
    copy.alt = item.alt;
    result.className = 'hide';
    Object.values(pockets).forEach(pocket => pocket.classList.remove('received','teach-hl'));
    photo.classList.remove('filed','show-focus','teach-hl');
    setControls();
  }

  function filePhoto(side) {
    result.className = side === 'known' ? 'left' : 'right';
    pockets[side].classList.add('received');
    photo.classList.add('filed');
  }

  function showRound() {
    demo = false;
    render(rounds[level]);
    K.levels(rounds.length,level);
    K.say(rounds[level].instruction);
  }

  function restart() {
    level = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    showRound();
  }

  function choose(side) {
    if (!K.started || buttons[side].disabled) return;
    const item = rounds[level];
    if (side !== item.answer) {
      miss += 1;
      K.shake(buttons[side]);
      K.sfx.no();
      K.say(miss === 1 ? '照片还没放进去。想想查到了什么。' : item.clue,'no');
      if (miss >= 3) K.highlight(side === 'known' ? '#record-unknown' : '#record-known');
      return;
    }
    locked = true;
    setControls();
    filePhoto(side);
    K.star(1,buttons[side]);
    K.sfx.ok();
    K.say(side === 'known' ? '已经确认的材料，记下具体部位。' : '先留下看到的，材料以后再查。','ok');
    timer = setTimeout(() => {
      level += 1;
      if (level < rounds.length) showRound();
      else {
        K.levels(rounds.length,level);
        K.finish({title:'观察记录收好了',sub:'记下证据，留下疑问',again:restart});
      }
    },1300);
  }

  Object.entries(buttons).forEach(([side,button]) => button.addEventListener('click',() => choose(side)));
  K.drag(photo,{enabled:() => K.started && !photo.disabled,targets:() => Object.values(pockets),
    onDrop:(element,target) => {if (target) choose(target === pockets.known ? 'known' : 'unknown');},
    onTap:() => K.say('把照片拖进记录袋，也可以直接点袋子。')});
  photo.addEventListener('click',event => {
    if (event.detail === 0 && !photo.disabled) K.say('把照片拖进记录袋，也可以直接点袋子。');
  });

  K.onStart = restart;
  K.onState = state => {
    if (state.mode === 'play') { restart(); return; }
    demo = true;
    render(bridge);
    photo.classList.add('show-focus');
    K.say('老师示范：找到部位，查清材料，再收进袋子。');
    if (state.mode === 'demo-file') filePhoto('known');
  };

  [image,copy].forEach(img => {
    img.addEventListener('error',() => {
      img.classList.add('record-failed');
      retry.classList.remove('hide');
      K.say('照片没有载入，点重试图片。');
      setControls();
    });
    img.addEventListener('load',() => {
      img.classList.remove('record-failed');
      if (!K.$('.record-failed')) retry.classList.add('hide');
      setControls();
    });
  });
  retry.addEventListener('click',() => K.$$('.record-failed').forEach(img => {img.src = img.src;}));

  window.__lessonTest = async () => {
    const checks = [];
    const expect = (name,condition) => checks.push([name,!!condition]);
    K.begin();
    restart();
    await K.cp('first-round');
    K.sim.click(buttons.unknown);
    await K.cp('first-error');
    expect('first miss does not file a card or show its destination',result.classList.contains('hide') && !pockets.known.classList.contains('teach-hl'));
    K.sim.drag(photo,pockets.known);
    await K.cp('first-correct');
    expect('drag files the window evidence',pockets.known.classList.contains('received') && copy.alt.includes('窗框'));
    await K.wait(1370);
    await K.cp('second-round');
    K.sim.click(buttons.unknown);
    await K.wait(1370);
    expect('tapping unknown finishes without asserting a material',pockets.unknown.classList.contains('received') && K.stars === 2 && !K.$('#finish').classList.contains('gone'));
    await K.cp('complete');
    K.$('#btn-again').click();
    expect('replay empties both pockets',result.classList.contains('hide') && K.stars === 0 && level === 0);
    K.onState({mode:'demo-look'});
    K.highlight('#record-photo');
    await K.cp('teacher-look');
    expect('teacher shows the bridge beam',image.alt.includes('钢梁') && photo.classList.contains('show-focus'));
    K.onState({mode:'demo-evidence'});
    K.highlight('#record-known');
    await K.cp('teacher-evidence');
    K.onState({mode:'demo-file'});
    await K.cp('teacher-file');
    expect('teacher files bridge evidence',pockets.known.classList.contains('received') && copy.alt.includes('大桥'));
    K.onState({mode:'play'});
    expect('teacher resets for the child',!demo && level === 0 && !photo.disabled && K.stars === 0);
    return checks;
  };
})();
