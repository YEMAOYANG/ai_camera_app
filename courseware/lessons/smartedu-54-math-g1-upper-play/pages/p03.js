(function () {
  const mat = K.$('#group-mat');
  const bench = K.$('#group-bench');
  const cue = K.$('#group-cue');
  const speaker = K.$('#group-call');
  const confirm = K.$('#group-confirm');
  const players = K.$$('.group-player');
  const selected = new Set();
  const targets = [2, 3];
  let round = 0;
  let misses = 0;
  let demonstrating = false;
  let changingRound = false;
  let broken = false;
  let nextRound;
  let audio;

  function stopAudio() {
    const previous = audio;
    audio = null;
    if (previous) previous.pause();
  }

  function replay() {
    if (demonstrating || changingRound || broken) return;
    stopAudio();
    const url = targets[round] === 2 ? speaker.dataset.clipTwo : speaker.dataset.clipThree;
    if (!url) {
      K.say('口令声音没有载入。', 'no');
      return;
    }
    const clip = new Audio(url);
    audio = clip;
    function clear() { if (audio === clip) audio = null; }
    function failed() {
      if (audio !== clip) return;
      clear();
      K.say('口令声音没有载入，请重新打开本页。', 'no');
    }
    clip.addEventListener('ended', clear, {once: true});
    clip.addEventListener('error', failed, {once: true});
    clip.play().catch(failed);
  }

  function render() {
    players.forEach((player, index) => {
      const onMat = selected.has(index);
      player.classList.toggle('placed', onMat);
      player.setAttribute('aria-pressed', String(onMat));
    });
    cue.replaceChildren(...Array.from({length: targets[round]}, () => document.createElement('span')));
    cue.setAttribute('aria-label', `口令人数 ${targets[round]}`);
    K.levels(targets.length, round);
  }

  function reset() {
    clearTimeout(nextRound);
    stopAudio();
    round = 0;
    misses = 0;
    changingRound = false;
    demonstrating = false;
    selected.clear();
    K.star(-K.stars);
    render();
    K.say('听清口令，再请伙伴进垫子。');
  }

  function enabled() { return !demonstrating && !changingRound && !broken; }

  function move(index, onMat) {
    if (!enabled()) return;
    if (onMat) selected.add(index);
    else selected.delete(index);
    render();
    K.sfx.pick();
  }

  confirm.addEventListener('click', () => {
    if (!enabled()) return;
    if (selected.size !== targets[round]) {
      misses += 1;
      K.sfx.no();
      K.shake(confirm);
      K.say(misses === 1 ? '再听听口令，点着垫子里的伙伴数。' : '一个点配一个伙伴，再看两边是否一样多。', 'no');
      if (misses > 1) K.highlight('#group-cue');
      return;
    }
    stopAudio();
    changingRound = true;
    K.levels(targets.length, round + 1);
    K.star(1, confirm);
    K.sfx.ok();
    K.say('人数和约好的一样。', 'ok');
    nextRound = setTimeout(() => {
      if (round + 1 === targets.length) {
        K.finish({title: '两次结队成功', sub: '听清口令再行动', again: reset});
        return;
      }
      round += 1;
      misses = 0;
      changingRound = false;
      selected.clear();
      render();
      K.say('下一轮口令变了。');
      replay();
    }, 680);
  });

  players.forEach((player, index) => {
    K.drag(player, {
      enabled,
      targets: () => [mat, bench],
      onTap: () => move(index, !selected.has(index)),
      onDrop: (_player, target) => { if (target) move(index, target === mat); },
    });
    player.addEventListener('click', (event) => {
      if (event.detail === 0) move(index, !selected.has(index));
    });
  });
  speaker.addEventListener('click', replay);

  function showImageError() {
    broken = true;
    stopAudio();
    K.$('#group-media-problem').classList.remove('hide');
    players.forEach((button) => { button.disabled = true; });
    confirm.disabled = true;
  }

  players.forEach((player) => {
    const image = player.querySelector('img');
    image.addEventListener('error', showImageError, {once: true});
    if (image.complete && !image.naturalWidth) showImageError();
  });
  K.hud({icon: '', title: '听口令结队', levels: targets.length});
  K.owl();
  K.ready({emoji: '听', title: '听口令结队', sub: '请伙伴走进集合垫'});
  K.onStart = reset;
  K.onState = (state) => {
    if (state.play) { reset(); return; }
    if (!['one', 'two'].includes(state.demo)) return;
    clearTimeout(nextRound);
    stopAudio();
    demonstrating = true;
    round = 0;
    selected.clear();
    selected.add(0);
    if (state.demo === 'two') selected.add(1);
    render();
  };
  window.addEventListener('pagehide', stopAudio);
  render();
})();
