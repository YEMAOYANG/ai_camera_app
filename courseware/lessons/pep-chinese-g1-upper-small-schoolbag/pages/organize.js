(function () {
  const items = K.$$('#pack-items button');
  const targets = K.$$('#pack-targets button');
  const packed = new Set();
  let selected = null;
  let phase = 'play';
  let wrong = 0;
  let epoch = 0;
  let imagesReady = true;

  K.hud({icon:'◇',title:document.title,levels:items.length});
  K.owl();
  K.ready({emoji:'◇',title:document.title,sub:'点一件用品，再点它要去的地方'});

  function watchImage(img) {
    img.addEventListener('error', () => {
      imagesReady = false;
      img.style.visibility = 'hidden';
      K.say('图片暂未载入，请重新打开本页', 'no');
    });
  }

  function clearSelection() {
    selected = null;
    for (const item of items) item.classList.remove('selected');
  }

  function clearBoard() {
    clearSelection();
    packed.clear();
    for (const item of items) {
      item.classList.remove('pack-done');
      item.disabled = false;
    }
    for (const target of targets) target.querySelector('.pack-received').replaceChildren();
  }

  function reset() {
    epoch += 1;
    wrong = 0;
    phase = 'play';
    clearBoard();
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(items.length, 0);
    K.say('先选桌上的一件用品，再找收纳位置');
  }

  function move(item, target) {
    const picture = item.querySelector('img').cloneNode(false);
    watchImage(picture);
    target.querySelector('.pack-received').append(picture);
    item.classList.add('pack-done');
    item.disabled = true;
    packed.add(item.dataset.item);
    clearSelection();
    K.pop(picture);
  }

  function put(item, target) {
    if (!K.started || phase !== 'play' || !item || !imagesReady || packed.has(item.dataset.item)) return;
    if (item.dataset.home !== target.dataset.target) {
      wrong += 1;
      K.shake(target);
      K.sfx.no();
      if (wrong === 1) K.say('看看用品是小文具，还是要放平的书本', 'no');
      else if (wrong === 2) K.say('比比用品的大小，想想哪里装得合适', 'no');
      else {
        K.highlight('#pack-' + item.dataset.home);
        K.say('看看老师提示的收纳位置', 'no');
      }
      return;
    }
    wrong = 0;
    move(item, target);
    K.star(1, target);
    K.levels(items.length, packed.size);
    K.sfx.ok();
    K.say('用品放好了，桌面又整齐了一点', 'ok');
    if (packed.size !== items.length) return;
    phase = 'complete';
    const ticket = epoch;
    setTimeout(() => {
      if (ticket === epoch) K.finish({title:'书包整理好啦',sub:'回家把自己的书包也整理一下',again:reset});
    }, 850);
  }

  function select(item) {
    if (!K.started || phase !== 'play' || !imagesReady || item.disabled) return;
    clearSelection();
    selected = item;
    item.classList.add('selected');
    wrong = 0;
    K.sfx.pick();
  }

  for (const img of K.$$('#pack-board img')) watchImage(img);
  for (const item of items) {
    K.drag(item, {
      enabled: () => K.started && phase === 'play' && imagesReady && !item.disabled,
      targets: () => targets,
      onTap: () => select(item),
      onDrop: (_, target) => { if (target) put(item, target); },
    });
    item.addEventListener('click', event => { if (event.detail === 0) select(item); });
  }
  for (const target of targets) target.addEventListener('click', () => put(selected, target));
  K.onStart = reset;
  K.onState = state => {
    if (state.phase === 'play') { reset(); return; }
    if (!Array.isArray(state.items)) return;
    epoch += 1;
    phase = 'demo';
    clearBoard();
    for (const name of new Set(state.items)) {
      const item = items.find(value => value.dataset.item === name);
      if (item) move(item, targets.find(target => target.dataset.target === item.dataset.home));
    }
  };
  reset();
})();
