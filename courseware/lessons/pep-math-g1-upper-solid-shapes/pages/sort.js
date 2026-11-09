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
  const specimens = [
    { family: 'box', image: '__IMG:eraser__', label: '盒装橡皮' },
    { family: 'tube', image: '__IMG:tube__', label: '直身小筒' },
    { family: 'cube', image: '__IMG:parcel__', label: '带纸带的小方包裹' },
    { family: 'ball', image: '__IMG:yarn__', label: '毛线团' },
  ];
  const names = { box: '长方体', cube: '正方体', tube: '圆柱', ball: '球' };
  const current = K.$('#sort-current');
  const shelves = K.$$('[data-family]');
  const stored = new Map();
  let round = 0;
  let demo = false;
  let busy = false;
  let mistakes = 0;
  let timer;

  K.hud({ icon: '▤', title: '把零件送回家', levels: specimens.length });
  K.owl();
  K.ready({ emoji: '▤', title: '把零件送回家', sub: '看上面的物品，点下面形状相同的架子。' });

  function render() {
    const item = specimens[round];
    picture(current, item.image, item.family);
    current.alt = item.label;
    current.hidden = stored.has(item.family);
    shelves.forEach(button => {
      const saved = stored.get(button.dataset.family);
      const image = button.querySelector('.stored');
      image.hidden = !saved;
      button.classList.toggle('placed', !!saved);
      if (saved) {
        picture(image, saved.image, saved.family);
        image.alt = saved.label;
      }
      button.disabled = demo || busy || !!saved;
    });
    K.levels(specimens.length, round);
  }

  function reset() {
    clearTimeout(timer);
    round = mistakes = 0;
    demo = busy = false;
    stored.clear();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    render();
    K.say('看物品整个身子，找同形的架子。');
  }

  function choose(button) {
    if (demo || busy || button.disabled) return;
    const item = specimens[round];
    if (button.dataset.family !== item.family) {
      mistakes += 1;
      K.sfx.no();
      K.shake(button);
      K.say(mistakes === 1 ? '先看外形，再和架上的模型比一比。' : '看平面或弯面，找整个形状相同的。', 'no');
      return;
    }
    stored.set(item.family, item);
    busy = true;
    render();
    K.sfx.ok();
    K.star(1, button);
    K.say('它的整体形状像' + names[item.family] + '。', 'ok');
    timer = setTimeout(() => {
      if (++round === specimens.length) {
        K.levels(specimens.length, specimens.length);
        K.finish({ title: '物品都回架了', sub: '颜色和花纹可以不同，整体形状相同就放一起。', again: reset });
        return;
      }
      busy = false;
      mistakes = 0;
      render();
      K.say('新的物品来了，再看一看。');
    }, 850);
  }

  shelves.forEach(button => { button.onclick = () => choose(button); });
  K.onStart = reset;
  K.onState = ({ mode }) => {
    if (mode === 'play') { reset(); return; }
    if (mode !== 'look' && mode !== 'placed') return;
    reset();
    demo = true;
    if (mode === 'placed') stored.set('box', specimens[0]);
    render();
    K.say(mode === 'placed' ? '橡皮和长方体模型放在一起。' : '看看橡皮的整体形状。');
  };
  render();
})();
