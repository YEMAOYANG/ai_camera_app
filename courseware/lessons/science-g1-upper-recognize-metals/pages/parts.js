(() => {
  const board = K.$('#parts-board');
  const source = K.$('#parts-image');
  const upper = K.$('#parts-upper');
  const lower = K.$('#parts-lower');
  const slot = K.$('#parts-slot');
  const saved = K.$('#parts-saved');
  const result = K.$('#parts-result');
  const marker = K.$('#parts-marker');
  const label = K.$('#parts-label');
  const retry = K.$('#parts-retry');
  const rounds = [
    { image:'__IMG:chair__', alt:'蓝色座面和银色腿的椅子', upper:'蓝色座面', lower:'金属腿', top:[50,43], bottom:[61,75], instruction:'找一找，椅子用金属的是哪一处？', clue:'从蓝色座面往下，看一看支撑它的部位。' },
    { image:'__IMG:window__', alt:'有银色边框和玻璃的窗户', upper:'玻璃', lower:'金属窗框', top:[33,48], bottom:[85,48], instruction:'换成窗户，找一找金属窗框。', clue:'比较透明的玻璃和包住它的边框。' },
  ];
  const desk = { image:'__IMG:desk__', alt:'有木面和铁腿的桌子', upper:'木桌面', lower:'铁桌腿', top:[51,21], bottom:[74,68] };
  let level = 0;
  let miss = 0;
  let locked = false;
  let demo = false;
  let timer;
  K.hud({icon:'',title:'找对部位再记录',levels:2});
  K.owl();
  K.ready({emoji:'',title:'找对部位再记录',sub:'看清部位，把发现放进记录卡'});

  function place(element, point) {
    element.style.left = point[0] + '%';
    element.style.top = point[1] + '%';
  }

  function render(item) {
    clearTimeout(timer);
    miss = 0;
    locked = false;
    upper.classList.remove('selected','teach-hl');
    lower.classList.remove('selected','teach-hl');
    K.$('#parts-card').classList.remove('teach-hl');
    source.alt = item.alt;
    source.src = item.image;
    result.src = item.image;
    result.alt = item.lower;
    upper.setAttribute('aria-label', item.upper);
    lower.setAttribute('aria-label', item.lower);
    place(upper,item.top);
    place(lower,item.bottom);
    place(marker,item.bottom);
    saved.classList.add('hide');
    slot.classList.remove('filled');
    label.textContent = '把找到的部位记在这里';
    setControls();
  }

  function setControls() {
    const disabled = demo || locked || !retry.classList.contains('hide');
    upper.disabled = disabled;
    lower.disabled = disabled;
  }

  function filePart(item) {
    lower.classList.add('selected');
    saved.classList.remove('hide');
    slot.classList.add('filled');
    label.textContent = '已记录 · ' + item.lower;
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

  function choose(part) {
    if (!K.started || part.disabled) return;
    if (part === upper) {
      miss += 1;
      K.shake(part);
      K.sfx.no();
      K.say(miss === 1 ? '还没记进卡里。再看一看两个部位。' : rounds[level].clue,'no');
      if (miss >= 3) K.highlight('#parts-lower');
      return;
    }
    locked = true;
    setControls();
    filePart(rounds[level]);
    K.star(1,part);
    K.sfx.ok();
    K.say('这个金属部位放进记录卡了。','ok');
    timer = setTimeout(() => {
      level += 1;
      if (level < rounds.length) showRound();
      else {
        K.levels(rounds.length,level);
        K.finish({title:'部位找到了',sub:'一件物品，可以用好几种材料',again:restart});
      }
    },1300);
  }

  [upper,lower].forEach(part => {
    K.drag(part,{enabled:() => K.started && !part.disabled,targets:() => [slot],
      onTap:choose,onDrop:(element,target) => {if (target) choose(element);}});
    part.addEventListener('click',event => {if (event.detail === 0) choose(part);});
  });

  K.onStart = restart;
  K.onState = state => {
    if (state.mode === 'play') { restart(); return; }
    demo = true;
    render(desk);
    K.say('老师示范：先从上到下看，再记具体部位。');
    if (state.mode === 'demo-record') filePart(desk);
  };

  [source,result].forEach(img => {
    img.addEventListener('error',() => {
      img.classList.add('parts-failed');
      retry.classList.remove('hide');
      K.say('观察图没有载入，点重试图片。');
      setControls();
    });
    img.addEventListener('load',() => {
      img.classList.remove('parts-failed');
      if (!board.classList.contains('hide') && !K.$('.parts-failed')) retry.classList.add('hide');
      setControls();
    });
  });
  retry.addEventListener('click',() => K.$$('.parts-failed').forEach(img => {img.src = img.src;}));

  window.__lessonTest = async () => {
    const checks = [];
    const expect = (name,condition) => checks.push([name,!!condition]);
    K.begin();
    restart();
    await K.cp('first-round');
    K.sim.tap(upper);
    await K.cp('first-error');
    expect('first miss saves nothing or reveals the answer',saved.classList.contains('hide') && !lower.classList.contains('teach-hl'));
    K.sim.drag(lower,slot);
    await K.cp('first-correct');
    expect('drag files the actual selected part',!saved.classList.contains('hide') && result.alt === '金属腿');
    await K.wait(1370);
    await K.cp('second-round');
    K.sim.tap(lower);
    await K.wait(1370);
    expect('tap finishes the second round',!K.$('#finish').classList.contains('gone') && K.stars === 2);
    await K.cp('complete');
    K.$('#btn-again').click();
    expect('replay resets both the part and stars',level === 0 && saved.classList.contains('hide') && K.stars === 0);
    K.onState({mode:'demo-top'});
    K.highlight('#parts-upper');
    await K.cp('teacher-top');
    expect('teacher shows the desk surface first',upper.getAttribute('aria-label') === '木桌面');
    K.onState({mode:'demo-leg'});
    K.highlight('#parts-lower');
    await K.cp('teacher-leg');
    K.onState({mode:'demo-record'});
    await K.cp('teacher-record');
    expect('teacher files a desk leg',result.alt === '铁桌腿' && !saved.classList.contains('hide'));
    K.onState({mode:'play'});
    expect('teacher resets for the child',!demo && level === 0 && !lower.disabled && K.stars === 0);
    return checks;
  };
})();
