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
  const boards = [K.$('#turn-flat'), K.$('#turn-cube')];
  const target = K.$('#turn-target');
  const control = K.$('#turn-control');
  const views = { flat: '__IMG:flat-plum__', cube: '__IMG:cube-plum__' };
  const tasks = [
    { order: ['flat', 'cube'], answer: 'cube', image: '__IMG:model-cube__', label: '正方体' },
    { order: ['cube', 'flat'], answer: 'flat', image: '__IMG:model-box__', label: '扁长方体' },
  ];
  let round = 0;
  let turned = false;
  let demo = false;
  let busy = false;
  let mistakes = 0;
  let timer;

  K.hud({ icon: '◈', title: '方盒转个身', levels: tasks.length });
  K.owl();
  K.ready({ emoji: '▣', title: '方盒转个身', sub: '先转一转，再找和小模型同形的盒子。' });

  function render() {
    const task = tasks[round];
    picture(target, task.image, task.answer === 'cube' ? 'cube' : 'box');
    target.alt = task.label;
    boards.forEach((board, i) => {
      const shape = task.order[i];
      picture(board.querySelector('img'), turned ? views[shape] : '__IMG:face-front__',
        !turned ? 'square' : shape === 'flat' ? 'box' : 'cube');
      board.disabled = demo || busy;
      board.classList.toggle('turned', turned);
    });
    control.disabled = demo || busy;
    K.levels(tasks.length, round);
  }

  function reset() {
    clearTimeout(timer);
    round = 0;
    turned = demo = busy = false;
    mistakes = 0;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    boards.forEach(board => board.classList.remove('success', 'incorrect'));
    render();
    K.say('先用弯箭头把两个盒子转过来。');
  }

  function choose(board, i) {
    if (demo || busy) return;
    if (!turned) {
      K.sfx.no();
      K.say('先转一转，看看盒子的旁边。', 'no');
      K.pop(control);
      return;
    }
    if (tasks[round].order[i] !== tasks[round].answer) {
      mistakes += 1;
      K.sfx.no();
      K.shake(board);
      K.say(mistakes === 1 ? '再看看两个盒子的侧面。' : '把正面和侧面的厚薄一起比一比。', 'no');
      return;
    }
    busy = true;
    render();
    board.classList.add('success');
    K.star(1, board);
    K.sfx.ok();
    K.say('你用了正面和侧面的线索。', 'ok');
    timer = setTimeout(() => {
      board.classList.remove('success');
      if (++round === tasks.length) {
        K.levels(tasks.length, tasks.length);
        K.finish({ title: '两个盒子都分清了', sub: '看方盒，要把前面和旁边一起看。', again: reset });
        return;
      }
      turned = busy = false;
      mistakes = 0;
      render();
      K.say('轮到另一种盒子了。先转，再找。');
    }, 850);
  }

  control.onclick = () => {
    if (demo || busy) return;
    turned = true;
    K.sfx.pick();
    render();
    K.say('看看旁边，哪一个和小模型同形？');
  };
  boards.forEach((board, i) => { board.onclick = () => choose(board, i); });
  K.onStart = reset;
  K.onState = ({ mode }) => {
    if (mode === 'play') { reset(); return; }
    if (mode !== 'front' && mode !== 'turned') return;
    reset();
    demo = true;
    turned = mode === 'turned';
    render();
    K.say(turned ? '比较前面和旁边。' : '两个正面一样方。');
  };
  render();
})();
