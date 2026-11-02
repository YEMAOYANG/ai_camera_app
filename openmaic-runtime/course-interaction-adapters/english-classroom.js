/* Release-bound input adapter. Speech self-practice is never pronunciation evidence. */
(function () {
  'use strict';
  window.installEnglishClassroomAdapter = function (sceneId) {
    const page = Number(sceneId.replace('scene-p', ''));
    const api = window.miraCourseOperation;
    let aligned = false, disposed = false, pending = false, timer = null, previous = null;
    const stable = value => JSON.stringify((function sort(v) {
      return Array.isArray(v) ? v.map(sort) : v && typeof v === 'object'
        ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v;
    })(value));
    const capture = () => window.miraActivityCheckpoint?.capture();
    function project(s) {
      if (!s || s.version !== 1 || s.page !== page) throw new Error('english_checkpoint_unavailable');
      const value = Object.fromEntries(['round','seed','started','poses','door','window','selected','turnSwap','lastAction','oral','chosen'].map(k => [k, s[k]]));
      value.route = s.route.map(step => step ? {cmd: step.cmd, actor: step.actor} : null);
      return value;
    }
    function error() {
      aligned = false; pending = false;
      window.dispatchEvent(new Event('mira-course-operation-error'));
    }
    function handle(event) {
      if (!event.isTrusted || disposed) return;
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest('#stage')) return;
      if (!aligned || !api.ready || pending) {
        event.preventDefault(); event.stopImmediatePropagation(); return;
      }
      if (!['click', 'pointerup', 'keydown'].includes(event.type)) return;
      if (event.type === 'keydown' && !['Enter',' ','ArrowUp','ArrowDown'].includes(event.key)) return;
      const before = capture();
      if (!before) return; // disabled inputs during narration/animation earn no credit
      const activate = event.type === 'click' || (event.type === 'keydown' && ['Enter',' '].includes(event.key)
        && !!target.closest('[data-object],[data-person],[data-chair],[data-mic],[data-create],[data-slot]'));
      const submit = activate && (!!target.closest('#check,#playRoute')
        || (!!target.closest('[data-create]') && before.oral === 'waiting'));
      const help = activate && !!target.closest('#hint,#replay,[data-round]');
      clearTimeout(timer);
      if (submit || help) pending = true;
      // Pointerup must allow the following native click. Coalesce work there;
      // continuous drags suppress that click and are captured here instead.
      timer = setTimeout(function settle(tries = 0) {
        if (disposed || !aligned || !api.ready) return;
        const shot = capture();
        if (!shot) {
          if (tries >= 500) { error(); return; }
          timer = setTimeout(() => settle(tries + 1), 40); return;
        }
        let work;
        try { work = project(shot); } catch (_) { error(); return; }
        const encoded = stable(work);
        if (encoded === previous && !submit && !help) { pending = false; return; }
        if (!work.started) { pending = false; return; }
        pending = true;
        void api.send({name: help ? 'help' : submit ? 'submit' : 'work', work}).then(() => {
          previous = encoded; pending = false;
          window.dispatchEvent(new CustomEvent('mira-activity-state-changed'));
        }).catch(error);
      }, 0);
    }
    const events = ['click','pointerup','keydown'];
    events.forEach(name => document.addEventListener(name, handle, true));
    return {restore(server) {
      try {
        const work = project(capture()); previous = stable(work);
        aligned = server?.kind === 'english-classroom' && server.validator === 'english-classroom-p' + page + '.v1'
          && (server.lastWork === null ? !work.started : previous === stable(server.lastWork));
      } catch (_) { aligned = false; }
      api.restoreConfirmed(aligned);
    }, dispose() {
      disposed = true; clearTimeout(timer);
      events.forEach(name => document.removeEventListener(name, handle, true));
    }};
  };
})();
