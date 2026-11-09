(() => {
  const K = window.K;
  const paper = K.$('#forge-paper');
  const caption = K.$('#forge-message');
  const actions = K.$('#forge-actions');
  const buttons = [K.$('#forge-a'), K.$('#forge-b')];
  const retry = K.$('#forge-retry');
  const plates = [
    {src:'__IMG:paper-0__', label:'整张纸上的横虚线'},
    {src:'__IMG:paper-1__', label:'叠好的纸和两侧短剪口'},
    {src:'__IMG:paper-2__', label:'纸身两侧的长虚线'},
    {src:'__IMG:paper-3__', label:'纸身折窄后，两片飞翼仍叠着'},
    {src:'__IMG:paper-4__', label:'两片飞翼已经打开，纸身仍相连'},
    {src:'__IMG:cut-across__', label:'一条从一边剪到另一边的线'},
  ];
  const levels = [
    {title:'找到先做的动作', options:[1,0], correct:1, hint:'想想怎样先把一张纸叠成两层。'},
    {title:'留住中间相连的纸', options:[1,5], correct:0, hint:'看看哪种动作能留下中间的纸。'},
    {title:'让下面的纸身变窄', options:[0,2], correct:1, hint:'看看剪口以下的纸往哪里合。'},
    {title:'让两片翼打开', options:[3,2], correct:0, hint:'再看看现在还贴着的两层纸。'},
  ];
  const completed = ['纸已经叠成两层','短口剪好了，中间还连着','纸身已经折窄','两片飞翼打开了'];
  let level = 0;
  let demo = false;
  let misses = 0;
  const broken = new Set();

  function syncRetry() {
    retry.classList.toggle('hide', !broken.size);
    buttons.forEach(button => { button.disabled = demo || broken.size > 0; });
  }

  function showImage(img, entry) {
    if (img.getAttribute('src') !== entry.src) {
      broken.delete(img);
      img.src = entry.src;
    }
    img.alt = entry.label;
  }

  function draw() {
    showImage(paper, plates[level]);
    const row = levels[level];
    actions.classList.toggle('hide', !row);
    caption.textContent = row ? row.title : '飞翼打开了，躯干仍连着';
    K.levels(4, level);
    if (row) {
      buttons.forEach((button, i) => {
        const choice = plates[row.options[i]];
        showImage(button.querySelector('img'), choice);
        button.setAttribute('aria-label', choice.label);
      });
    }
    syncRetry();
  }

  function reset() {
    level = 0;
    misses = 0;
    demo = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    draw();
    K.say('听老师讲过的四步，再来动手');
  }

  function choose(index) {
    const row = levels[level];
    if (demo || !row || broken.size) return;
    if (index !== row.correct) {
      misses += 1;
      K.shake(buttons[index]);
      K.sfx.no();
      K.say(row.hint, 'no');
      if (misses > 1) K.highlight('#forge-paper');
      return;
    }
    K.star(1, buttons[index]);
    K.sfx.ok();
    misses = 0;
    level += 1;
    draw();
    K.say(completed[level - 1], 'ok');
    if (level === 4) K.finish({title:'改进版做好了', sub:'纸身折紧，两翼打开', again:reset});
  }

  [paper, ...buttons.map(b => b.querySelector('img'))].forEach(img => {
    img.addEventListener('error', () => { broken.add(img); syncRetry(); });
    img.addEventListener('load', () => { broken.delete(img); syncRetry(); });
  });
  retry.onclick = () => broken.forEach(img => { img.src = img.getAttribute('src'); });
  buttons.forEach((button, i) => { button.onclick = () => choose(i); });
  K.hud({icon:'',title:'在纸上做四步',levels:4});
  K.owl();
  K.onStart = reset;
  K.onState = (state) => {
    if (state.paperDemo === false) reset();
    if (Number.isInteger(state.paperDemo) && state.paperDemo >= 0 && state.paperDemo <= 4) {
      demo = true;
      level = state.paperDemo;
      draw();
      K.say('看老师怎样改变这一张纸');
    }
  };
  reset();
  K.ready({emoji:'',title:'在纸上做四步',sub:'听老师示范，再来改纸蜻蜓'});
})();
