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
  const display = K.$('#roll-object');
  const track = K.$('#roll-track');
  const token = K.$('#roll-task');
  const variants = {
    upright: { key: 'tube', image: '__IMG:tube__', label: '竖放的圆柱' },
    side: { key: 'side', image: '__IMG:tube-side__', label: '横放的圆柱' },
    sphere: { key: 'ball', image: '__IMG:model-ball__', label: '球' },
  };
  const levels = [
    { choice: 'side', cue: 'roll', label: '让圆柱滚' },
    { choice: 'upright', cue: 'stand', label: '让圆柱站' },
    { choice: 'sphere', cue: 'many', label: '换方向也能滚' },
  ];
  const options = { upright: K.$('#roll-stand'), side: K.$('#roll-side'), sphere: K.$('#roll-ball') };
  let round = 0;
  let demo = false;
  let busy = false;
  let mistakes = 0;
  let timer;

  K.hud({ icon: '↗', title: '站起来，滚出去', levels: levels.length });
  K.owl();
  K.ready({ emoji: '◉', title: '站起来，滚出去', sub: '看小牌上的方向图，再试不同的放法。' });

  function show(mode, move = false) {
    const variant = variants[mode];
    picture(display, variant.image, variant.key);
    display.alt = variant.label;
    track.dataset.mode = mode;
    track.classList.remove('moving');
    if (move) {
      void track.offsetWidth;
      track.classList.add('moving');
    }
  }

  function cue() {
    const level = levels[round];
    token.dataset.cue = level.cue;
    K.$('#roll-task-label').textContent = level.label;
    Object.values(options).forEach(button => { button.disabled = demo || busy; });
    K.levels(levels.length, round);
  }

  function reset() {
    clearTimeout(timer);
    round = mistakes = 0;
    demo = busy = false;
    show('upright');
    cue();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    Object.values(options).forEach(button => button.classList.remove('success'));
    K.say('先试试怎样让圆柱滚出去。');
  }

  function choose(mode) {
    if (demo || busy) return;
    show(mode, true);
    if (mode !== levels[round].choice) {
      mistakes += 1;
      K.sfx.no();
      K.shake(options[mode]);
      K.say(mistakes === 1 ? '看小牌上的方向，再试一种放法。' : '想想平面和弯面，碰着桌面会怎样？', 'no');
      return;
    }
    busy = true;
    cue();
    options[mode].classList.add('success');
    K.sfx.ok();
    K.star(1, options[mode]);
    K.say(mode === 'sphere' ? '球换一个方向也能滚。' : mode === 'side' ? '圆柱横放，轻推就滚。' : '圆柱用平圆面稳稳站住。', 'ok');
    timer = setTimeout(() => {
      options[mode].classList.remove('success');
      if (++round === levels.length) {
        K.levels(levels.length, levels.length);
        K.finish({ title: '方向试好了', sub: '圆柱有平圆面，球往不同方向都能滚。', again: reset });
        return;
      }
      busy = false;
      mistakes = 0;
      show('upright');
      cue();
      K.say(levels[round].label + '。');
    }, 920);
  }

  Object.entries(options).forEach(([mode, button]) => { button.onclick = () => choose(mode); });
  K.onStart = reset;
  K.onState = ({ mode }) => {
    if (mode === 'play') { reset(); return; }
    if (!Object.hasOwn(variants, mode)) return;
    reset();
    demo = true;
    round = mode === 'sphere' ? 2 : mode === 'side' ? 0 : 1;
    show(mode, mode !== 'upright');
    cue();
    K.say(variants[mode].label + '。');
  };
  show('upright');
  cue();
})();
