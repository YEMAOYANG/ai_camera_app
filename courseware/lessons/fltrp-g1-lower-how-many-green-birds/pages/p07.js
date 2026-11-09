(function () {
  function makePlacement() {
    let stage = 'place';
    return {
      drop(position) {
        if (stage !== 'place' || position !== 'under') return false;
        stage = 'confirm';
        return true;
      },
      confirm(choice) {
        if (stage !== 'confirm' || choice !== 'no') return false;
        stage = 'complete';
        return true;
      },
      current() { return stage; },
      reset() { stage = 'place'; },
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { makePlacement };
  if (typeof document === 'undefined') return;

  const model = makePlacement();
  const map = K.$('#pick-map');
  const equipment = K.$('#equipment');
  const demoPicture = K.$('#equipment-demo');
  const zones = K.$$('.map-zone');
  const options = K.$$('#map-confirmation button');
  const placements = { on: '__IMG:map-on__', under: '__IMG:map-under__', in: '__IMG:map-in__' };
  let selected = false;
  let demonstrating = false;
  let wrongs = 0;
  let timer;
  K.hud({ icon: '', title: '摆地图卡，听问题', levels: 2 });
  K.owl();

  function showFailure() { K.$('#map-picture-failure').classList.remove('hide'); }

  function showLocation(place) {
    demoPicture.classList.toggle('hide', !place);
    if (place) demoPicture.src = placements[place];
  }

  function reset() {
    clearTimeout(timer);
    model.reset();
    selected = demonstrating = false;
    wrongs = 0;
    map.classList.remove('hide', 'selected');
    zones.forEach(zone => zone.classList.remove('hide'));
    options.forEach(button => { button.disabled = false; button.classList.remove('placed'); });
    K.$('#map-confirmation').classList.add('hide');
    equipment.classList.remove('confirming');
    K.$('#tip').style.display = 'none';
    showLocation(null);
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    K.levels(2, 0);
    K.say('先点地图卡，再点位置；也能拖过去。');
  }

  function chooseMap() {
    if (demonstrating || model.current() !== 'place') return;
    selected = true;
    map.classList.add('selected');
    K.sfx.pick();
  }

  function feedback(target, first, next) {
    wrongs += 1;
    K.shake(target);
    K.sfx.no();
    if (wrongs === 2) K.highlight('#equipment');
    K.say(wrongs === 1 ? first : next, 'no');
  }

  function place(target) {
    if (!target || demonstrating || model.current() !== 'place') return;
    if (!model.drop(target.dataset.place)) {
      feedback(target, '先比较桌面和桌脚。', '再听位置词，看它是说哪里。');
      return;
    }
    wrongs = 0;
    map.classList.add('hide');
    zones.forEach(zone => zone.classList.add('hide'));
    showLocation('under');
    K.levels(2, 1);
    K.star(1, equipment);
    K.sfx.drop();
    K.say('看清实际位置，再判断：Is it on the table?');
    timer = setTimeout(() => {
      equipment.classList.add('confirming');
      K.$('#map-confirmation').classList.remove('hide');
    }, 900);
  }

  function confirm(button) {
    if (model.current() !== 'confirm') return;
    if (!model.confirm(button.dataset.response)) {
      feedback(button, '比较实际放的位置和问句。', '要是位置不同，选那幅不一样的图。');
      return;
    }
    button.classList.add('placed');
    options.forEach(option => { option.disabled = true; });
    K.levels(2, 2);
    K.star(1, button);
    K.say('No, it isn’t. 地图卡在桌下。', 'ok');
    timer = setTimeout(() => K.finish({ title: '地图卡放好了', sub: '听清问句，再核对位置', again: reset }), 1250);
  }

  K.drag(map, {
    enabled: () => !demonstrating && model.current() === 'place',
    targets: () => zones,
    onTap: chooseMap,
    onDrop: (_, target) => place(target),
  });
  map.addEventListener('click', chooseMap);
  zones.forEach(zone => zone.addEventListener('click', () => {
    if (selected) place(zone);
    else if (!demonstrating) K.say('先点一下左边的地图卡。');
  }));
  options.forEach(button => button.addEventListener('click', () => confirm(button)));

  K.onState = state => {
    if (!Object.hasOwn(state, 'demoPlace')) return;
    if (!state.demoPlace) {
      reset();
      return;
    }
    demonstrating = true;
    map.classList.add('hide');
    zones.forEach(zone => zone.classList.add('hide'));
    showLocation(state.demoPlace);
    K.highlight('#equipment');
  };

  K.$$('#map-station img').forEach(img => img.addEventListener('error', showFailure));
  K.$('#reload-map').addEventListener('click', () => {
    K.$('#map-picture-failure').classList.add('hide');
    K.$$('#map-station img').forEach(img => { img.src = img.src; });
  });
  reset();
  K.onStart = reset;
  K.ready({ title: '地图卡放哪里', sub: '听位置，摆一摆，再听问句', emoji: '' });
})();
