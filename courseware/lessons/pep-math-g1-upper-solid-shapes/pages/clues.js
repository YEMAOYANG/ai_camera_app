(() => {
  // Keep the relevant geometry visible even if its registered image cannot load.
  const fallbackForms = {
    square: '<path d="M30 14h78v78H30z" fill="#ae739c"/>',
    box: '<path d="M14 44 48 24h79l-33 20v44H14z" fill="#70ab95"/><path d="M94 44l33-20v45L94 88z" fill="#4d7f74"/>',
    cube: '<path d="M27 38 54 14h63L91 38v62H27z" fill="#e99d82"/><path d="M91 38l26-24v62l-26 24z" fill="#ad5a52"/>',
    tube: '<path d="M38 28v54c0 23 64 23 64 0V28z" fill="#709fbd"/><ellipse cx="70" cy="28" rx="32" ry="15" fill="#abd1e7"/>',
    side: '<path d="M34 22h72v65H34z" fill="#709fbd"/><ellipse cx="34" cy="54.5" rx="16" ry="32.5" fill="#abd1e7"/><path d="M106 22c22 0 22 65 0 65" fill="none"/>',
    ball: '<circle cx="70" cy="54" r="39" fill="#e6ae54"/><ellipse cx="55" cy="40" rx="11" ry="7" fill="#f9dc9f" stroke="none"/>',
  };
  const activeFallbacks = new WeakMap();
  function clearFallback(image) {
    const fallback = activeFallbacks.get(image);
    if (!fallback) return;
    fallback.observer.disconnect();
    fallback.svg.remove();
    image.style.opacity = '';
    activeFallbacks.delete(image);
  }
  function picture(image, source, shape) {
    image.dataset.form = shape;
    if (image.getAttribute('src') === source || image.dataset.pictureUrl === source) return;
    clearFallback(image);
    image.dataset.pictureUrl = source;
    image.src = source;
  }
  K.$$('img[data-form], #clue-object, #stack-top img, .stored').forEach(image => {
    image.addEventListener('error', () => {
      const geometry = fallbackForms[image.dataset.form];
      if (!geometry || activeFallbacks.has(image)) return;
      const parent = image.parentElement;
      if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('class', 'geometry-fallback');
      svg.setAttribute('aria-hidden', 'true');
      svg.setAttribute('viewBox', '0 0 140 110');
      svg.innerHTML = '<g stroke="#303b3d" stroke-width="3" stroke-linejoin="round">' + geometry + '</g>';
      const place = () => {
        Object.assign(svg.style, {left: image.offsetLeft + 'px', top: image.offsetTop + 'px',
          width: image.offsetWidth + 'px', height: image.offsetHeight + 'px'});
      };
      const observer = new ResizeObserver(place);
      activeFallbacks.set(image, {svg, observer});
      image.after(svg);
      image.style.opacity = '0';
      place();
      observer.observe(image);
    });
    image.addEventListener('load', () => clearFallback(image));
  });
  const tasks = [
    { shape: 'tube', image: '__IMG:model-tube__', label: '圆柱', cue: '两个平圆印和一条滚动路线。' },
    { shape: 'cube', image: '__IMG:model-cube__', label: '正方体', cue: '印下的方形面一样大。' },
    { shape: 'ball', image: '__IMG:model-ball__', label: '球', cue: '没有平面印痕，往不同方向都能滚。' },
  ];
  const trace = K.$('#clue-trace');
  const reveal = K.$('#clue-reveal');
  const object = K.$('#clue-object');
  const choices = K.$$('#clue-choices button');
  let round = 0;
  let demo = false;
  let revealed = false;
  let busy = false;
  let mistakes = 0;
  let timer;

  K.hud({ icon: '◇', title: '听线索，猜一猜', levels: tasks.length });
  K.owl();
  K.ready({ emoji: '▣', title: '听线索，猜一猜', sub: '看印痕和路线，猜猜盖子下是什么。' });

  function render() {
    const task = tasks[round];
    trace.dataset.cue = task.shape;
    reveal.classList.toggle('revealed', revealed);
    object.hidden = !revealed;
    if (revealed) {
      picture(object, task.image, task.shape);
      object.alt = task.label;
    }
    choices.forEach(button => { button.disabled = demo || busy; });
    K.levels(tasks.length, round);
  }

  function reset() {
    clearTimeout(timer);
    round = mistakes = 0;
    demo = busy = revealed = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    choices.forEach(button => button.classList.remove('success'));
    render();
    K.say(tasks[round].cue);
  }

  function choose(button) {
    if (demo || busy) return;
    const task = tasks[round];
    if (button.dataset.form !== task.shape) {
      mistakes += 1;
      K.sfx.no();
      K.shake(button);
      K.say(mistakes === 1 ? '把印痕和路线一起看。' : '换个角度想，哪个模型能留下这些线索？', 'no');
      return;
    }
    revealed = busy = true;
    render();
    button.classList.add('success');
    K.sfx.ok();
    K.star(1, button);
    K.say('盖子打开了，是' + task.label + '。', 'ok');
    timer = setTimeout(() => {
      button.classList.remove('success');
      if (++round === tasks.length) {
        K.levels(tasks.length, tasks.length);
        K.finish({ title: '三个形状都猜到了', sub: '多用一条线索，猜得更准。', again: reset });
        return;
      }
      mistakes = 0;
      busy = revealed = false;
      render();
      K.say(tasks[round].cue);
    }, 1000);
  }

  choices.forEach(button => { button.onclick = () => choose(button); });
  K.onStart = reset;
  K.onState = ({ mode }) => {
    if (mode === 'play') { reset(); return; }
    if (mode !== 'flat' && mode !== 'revealed') return;
    reset();
    demo = true;
    revealed = mode === 'revealed';
    render();
    K.say(revealed ? '圆柱有平圆面，横放又能滚。' : tasks[round].cue);
  };
  render();
})();
