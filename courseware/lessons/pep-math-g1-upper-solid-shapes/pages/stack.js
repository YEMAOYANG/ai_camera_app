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
  const base = K.$('#stack-base');
  const top = K.$('#stack-top');
  const baseImage = base.querySelector('img');
  const topImage = top.querySelector('img');
  const marker = K.$('#stack-task');
  const target = K.$('#stack-target');
  const choices = K.$$('.stack-choices button');
  const tasks = [
    { shape: 'box', image: '__IMG:model-box__', label: '先放长方体在下面。', layer: 'base' },
    { shape: 'cube', image: '__IMG:model-cube__', label: '再放正方体在上面。', layer: 'top' },
  ];
  let step = 0;
  let mistakes = 0;
  let demo = false;
  let busy = false;
  let upper = null;
  let timer;

  K.hud({ icon: '▦', title: '照着顺序搭两块', levels: tasks.length });
  K.owl();
  K.ready({ emoji: '▦', title: '照着顺序搭两块', sub: '看小牌上亮起来的一层，再选积木。' });

  function render() {
    const task = tasks[Math.min(step, 1)];
    marker.dataset.layer = task.layer;
    const showingCylinder = demo && step === 1;
    picture(target, showingCylinder ? '__IMG:model-tube__' : task.image, showingCylinder ? 'tube' : task.shape);
    target.alt = showingCylinder ? '准备放圆柱在上面' : task.label;
    baseImage.hidden = step === 0;
    base.classList.toggle('placed', step > 0);
    topImage.hidden = !upper;
    top.classList.toggle('placed', !!upper);
    if (upper) {
      picture(topImage, upper === 'cube' ? '__IMG:model-cube__' : '__IMG:model-tube__', upper);
      topImage.alt = upper === 'cube' ? '上层正方体' : '上层圆柱';
    }
    choices.forEach(button => { button.disabled = demo || busy; });
    K.levels(tasks.length, step);
  }

  function reset() {
    clearTimeout(timer);
    step = mistakes = 0;
    demo = busy = false;
    upper = null;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    choices.forEach(button => button.classList.remove('success'));
    render();
    K.say(tasks[0].label);
  }

  function choose(button) {
    if (demo || busy) return;
    if (button.dataset.form !== tasks[step].shape) {
      mistakes += 1;
      K.sfx.no();
      K.shake(button);
      K.say(mistakes === 1 ? '先看看小牌上亮的是哪一层。' : '照着小牌上的模型，找整体形状一样的积木。', 'no');
      return;
    }
    if (step === 1) upper = 'cube';
    step += 1;
    busy = true;
    render();
    button.classList.add('success');
    K.sfx.ok();
    K.star(1, button);
    K.say(step === 1 ? '底座放好了，看看它的上面。' : '上面是正方体，下面是长方体。', 'ok');
    timer = setTimeout(() => {
      button.classList.remove('success');
      if (step === tasks.length) {
        K.finish({ title: '两块积木搭好了', sub: '先放下面，再把另一块放到上面。', again: reset });
        return;
      }
      busy = false;
      mistakes = 0;
      render();
      K.say(tasks[step].label);
    }, 920);
  }

  choices.forEach(button => { button.onclick = () => choose(button); });
  K.onStart = reset;
  K.onState = ({ mode }) => {
    if (mode === 'play') { reset(); return; }
    if (!['clear', 'base', 'top'].includes(mode)) return;
    reset();
    demo = true;
    step = mode === 'clear' ? 0 : 1;
    upper = mode === 'top' ? 'tube' : null;
    render();
    K.say(mode === 'top' ? '圆柱的平圆面贴着底座。' : mode === 'base' ? '长方体在下面。' : '先从下面开始。');
  };
  render();
})();
