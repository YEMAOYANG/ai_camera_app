(() => {
  const activity = K.$('#ceremony-activity');
  const anthem = K.$('#ceremony-anthem');
  const flag = K.$('#ceremony-flag');
  const yard = K.$('#ceremony-yard');
  const rope = K.$('#ceremony-rope');
  const button = K.$('#ceremony-start');
  const status = K.$('#ceremony-status');
  const completion = K.$('#ceremony-done');

  const statusText = {
    locked: '先听老师讲，再来升旗。',
    ready: '向下拉一下绳子，或按下升旗。',
    loading: '请稍等，正在准备国歌。',
    playing: '面向国旗，立正，注视国旗。',
    buffering: '国歌正在缓冲，请稍等。',
    interrupted: '国歌已暂停，可以接着听。',
    error: '国歌没有顺利播放，可以重试。',
    done: '国歌奏毕，升旗仪式结束。'
  };
  let teacherReady = false;
  let active = true;
  let flagMissing = false;
  let startedSound = false;
  let attempt = 0;
  let frame = 0;
  let watchdog = 0;
  let drag = null;

  const phase = () => activity.dataset.phase;
  const running = () => ['loading', 'playing', 'buffering'].includes(phase());
  const hasFlag = () => flag.complete && flag.naturalWidth > 0;

  function setPhase(next) {
    activity.dataset.phase = next;
    status.textContent = flagMissing ? '国旗图片没有加载，请重新打开这一页。' : statusText[next];
    button.hidden = ['loading', 'playing', 'buffering', 'done'].includes(next);
    button.disabled = !teacherReady || !active || !hasFlag();
    button.textContent = next === 'interrupted' ? '继续听国歌' : next === 'error' ? '重试播放' : '升旗';
    completion.hidden = next !== 'done';
  }

  function placeFlag(progress) {
    const ratio = Math.max(0, Math.min(1, progress));
    flag.style.setProperty('--flag-lift', 324 * (1 - ratio) + 'px');
  }

  function stopMonitoring() {
    cancelAnimationFrame(frame);
    clearTimeout(watchdog);
    frame = watchdog = 0;
  }

  function updatePosition() {
    if (phase() !== 'playing') return;
    if (Number.isFinite(anthem.duration) && anthem.duration > 0) {
      // Only the browser's actual playback clock moves the flag.
      placeFlag(anthem.currentTime / anthem.duration);
    }
    frame = requestAnimationFrame(updatePosition);
  }

  function failed() {
    ++attempt;
    stopMonitoring();
    startedSound = false;
    setPhase('error');
    anthem.pause();
    placeFlag(0);
  }

  function waitForAudio() {
    clearTimeout(watchdog);
    watchdog = setTimeout(() => {
      if (phase() === 'loading' || phase() === 'buffering') failed();
    }, 20000);
  }

  function play() {
    const previous = phase();
    if (!teacherReady || !active || !hasFlag() || !['ready', 'interrupted', 'error'].includes(previous)) return;
    const thisAttempt = ++attempt;
    setPhase('loading');
    waitForAudio();
    if (previous === 'error') anthem.load();
    anthem.play().catch(() => {
      if (thisAttempt === attempt && running()) failed();
    });
  }

  function interrupt() {
    if (!running()) return;
    ++attempt;
    stopMonitoring();
    setPhase('interrupted');
    anthem.pause();
  }

  anthem.addEventListener('playing', () => {
    if (!active || !running()) {
      anthem.pause();
      return;
    }
    startedSound = true;
    stopMonitoring();
    setPhase('playing');
    updatePosition();
  });
  anthem.addEventListener('waiting', () => {
    if (phase() !== 'playing') return;
    stopMonitoring();
    setPhase('buffering');
    waitForAudio();
  });
  anthem.addEventListener('pause', () => {
    if (!anthem.ended) interrupt();
  });
  anthem.addEventListener('ended', () => {
    if (!active || !running() || !startedSound || !anthem.ended ||
        !Number.isFinite(anthem.duration) || anthem.currentTime < anthem.duration - 0.15) return;
    stopMonitoring();
    placeFlag(1);
    setPhase('done');
  });
  anthem.addEventListener('error', failed);
  flag.addEventListener('load', () => setPhase(phase()));
  flag.addEventListener('error', () => {
    flagMissing = true;
    flag.hidden = true;
    setPhase(phase());
  });
  yard.addEventListener('error', () => { yard.hidden = true; });

  function clearDrag() {
    drag = null;
    rope.style.removeProperty('--rope-drag');
  }

  rope.addEventListener('pointerdown', (event) => {
    if (!event.isPrimary || event.button !== 0 || phase() !== 'ready' || !active || !hasFlag()) return;
    event.preventDefault();
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
    rope.setPointerCapture(event.pointerId);
  });
  rope.addEventListener('pointermove', (event) => {
    if (event.pointerId !== drag?.id) return;
    const y = (event.clientY - drag.y) / K.scale;
    rope.style.setProperty('--rope-drag', Math.min(60, Math.max(0, y)) + 'px');
  });
  rope.addEventListener('pointerup', (event) => {
    if (event.pointerId !== drag?.id) return;
    const pulled = (event.clientY - drag.y) / K.scale >= 46 &&
      Math.abs(event.clientX - drag.x) / K.scale <= 110;
    clearDrag();
    if (pulled) play();
  });
  rope.addEventListener('pointercancel', clearDrag);
  rope.addEventListener('lostpointercapture', clearDrag);
  button.addEventListener('click', play);
  window.addEventListener('keydown', (event) => {
    if (event.code !== 'Space' || event.repeat || button.hidden || button.disabled) return;
    event.preventDefault();
    play();
  });

  K.onState = (state) => {
    if (state.ceremonyReady !== true && state.activityReady !== true) return;
    teacherReady = true;
    if (phase() === 'locked') setPhase('ready');
    else setPhase(phase());
  };

  // This iframe can be hidden but kept alive during classroom navigation.
  window.addEventListener('message', (event) => {
    if (event.source !== window.parent || event.data?.type !== 'mira:checkpoint-visibility' ||
        typeof event.data.active !== 'boolean') return;
    active = event.data.active;
    if (!active) {
      clearDrag();
      interrupt();
    }
    setPhase(phase());
  });
  window.addEventListener('pagehide', interrupt);
})();
