(() => {
  const K = window.K;
  const target = K.$('#fold-target');
  const paper = K.$('#fold-paper');
  const tools = [K.$('#fold-cut'), K.$('#fold-crease')];
  const note = K.$('#fold-note');
  const steps = [
    {image: '__IMG:paper-pattern__', alt: '未剪的纸样', area: [227, 188, 140, 94], tool: 0, topic: '先看两边的小口'},
    {image: '__IMG:paper-slit__', alt: '两侧短口已经剪开', area: [238, 211, 118, 128], tool: 1, topic: '看纸条下面的两条线'},
    {image: '__IMG:paper-body__', alt: '下段已折成细躯干', area: [250, 58, 94, 136], tool: 0, topic: '找到上端的中线和止点'},
    {image: '__IMG:paper-split__', alt: '上端分成两片仍连着根的翼', area: [232, 137, 130, 94], tool: 1, topic: '在翼根把两片向反方向折'},
    {image: '__IMG:paper-rotor__', alt: '两翼反向展开的纸蜻蜓', topic: '两片翼展开了'},
  ];
  let level = 0;
  let picked = null;
  let misses = 0;
  let demo = false;

  function draw() {
    const step = steps[level];
    paper.src = step.image;
    paper.alt = step.alt;
    note.textContent = step.topic;
    K.levels(4, level);
    target.hidden = level === 4;
    target.disabled = demo || level === 4;
    target.classList.remove('hint');
    if (step.area) {
      ['left', 'top', 'width', 'height'].forEach((key, index) => { target.style[key] = step.area[index] + 'px'; });
    }
    picked = null;
    misses = 0;
    tools.forEach((button) => {
      button.disabled = demo || level === 4;
      button.classList.remove('selected');
    });
    K.say(demo ? '看老师示范纸样怎样改变' : '先选剪或折，再点框里的线');
  }

  function reset() {
    level = 0;
    demo = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    draw();
  }

  function select(index) {
    if (demo || level >= 4) return;
    picked = index;
    tools.forEach((button, n) => button.classList.toggle('selected', index === n));
    K.sfx.pick();
  }

  function use() {
    if (demo || level >= 4) return;
    if (picked === null || picked !== steps[level].tool) {
      misses += 1;
      target.classList.add('hint');
      K.shake(picked === null ? target : tools[picked]);
      K.sfx.no();
      K.say(picked === null ? '先选一个动作' : '再看框里的线是连着还是断开的', 'no');
      if (misses > 1 && picked !== null) K.annotate('#fold-board', '完整的线要剪，断开的线要折');
      return;
    }
    K.star(1, target);
    K.sfx.ok();
    level += 1;
    draw();
    if (level === 4) K.finish({title: '纸蜻蜓做好了', sub: '两片翼朝相反方向展开', again: reset});
  }

  tools.forEach((button, index) => {
    button.onclick = () => select(index);
    K.drag(button, {
      enabled: () => !demo && level < 4,
      targets: () => [target],
      onTap: () => select(index),
      onDrop: (_button, drop) => { if (drop) { select(index); use(); } },
    });
  });
  target.onclick = use;
  paper.onerror = () => {
    const existing = K.$('.fold-retry');
    if (existing) return;
    const retry = K.el('button', 'fold-retry', '↻', K.$('#fold-board'));
    retry.setAttribute('aria-label', '重新加载纸样');
    retry.onclick = () => { paper.src = steps[level].image; };
    paper.onload = () => { retry.remove(); };
  };
  K.hud({icon: '', title: '把纸折成小飞翼', levels: 4});
  K.owl();
  K.onStart = reset;
  K.onState = (state) => {
    if (state.foldDemo === false) reset();
    if (Number.isInteger(state.foldDemo) && state.foldDemo >= 0 && state.foldDemo <= 4) {
      demo = true;
      level = state.foldDemo;
      draw();
    }
  };
  draw();
  K.ready({emoji: '↻', title: '把纸折成小飞翼', sub: '看清标记，再选剪还是折'});
})();
