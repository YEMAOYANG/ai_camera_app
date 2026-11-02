/* Exact sensory-lab release: report user inputs after their real effect settles.
 * Simulation playback is client-reported, never real-world sensory evidence. */
(function () {
  'use strict';
  window.installScienceSensoryAdapter = function (sceneId) {
    const page = Number(sceneId.replace('scene-p', ''));
    const api = window.miraCourseOperation, checkpoint = window.miraActivityCheckpoint;
    let aligned = false, disposed = false, pending = false, timer = null;
    const capture = () => checkpoint.capture();
    const guarded = Object.freeze({...checkpoint, capture() {
      return pending || timer !== null ? null : capture();
    }});
    window.miraActivityCheckpoint = guarded;
    const keys = 'started phase selected channels clues excluded guess firstGuess revealed revised rotation force probes direction heard links route robot help'.split(' ');
    const stable = x => JSON.stringify((function sort(v) {
      return Array.isArray(v) ? v.map(sort) : v && typeof v === 'object'
        ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v;
    })(x));
    function project(shot) {
      if (shot?.schemaVersion !== 'mira.science.sensory-lab.v1' || shot.state?.page !== page)
        throw new Error('science_checkpoint_unavailable');
      return Object.fromEntries(keys.map(k => [k, shot.state[k]]));
    }
    function error() {
      aligned = false; pending = false; timer = null;
      window.dispatchEvent(new Event('mira-course-operation-error'));
    }
    function handle(event) {
      if (!event.isTrusted || disposed) return;
      const target = event.target instanceof Element ? event.target : null;
      const control = target?.closest('[data-act],#begin,#reset,#help,#replay');
      if (!control) return;
      if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
      if (!aligned || !api.ready || pending || timer !== null) {
        event.preventDefault(); event.stopImmediatePropagation(); return;
      }
      const before = capture();
      if (!before) return; // a disabled input cannot manufacture a response
      let action = control.dataset.act || ({begin: 'start', reset: 'reset', help: 'help', replay: 'replay'})[control.id];
      if (!action) return;
      if (!before.state.started && ['replay', 'help'].includes(action)) return;
      // Native buttons produce their own click on keyboard activation; SVG
      // controls use their authored keydown handler and do not synthesize one.
      if (event.type === 'keydown' && !control.dataset.act) return;
      pending = true;
      timer = setTimeout(function settle(tries = 0) {
        if (disposed || !aligned || !api.ready) return;
        let shot;
        try { shot = capture(); } catch (_) { error(); return; }
        if (!shot) {
          if (tries >= 1500) { error(); return; }
          timer = setTimeout(() => settle(tries + 1), 40); return;
        }
        timer = null;
        // Interruption of the simulated sound never earns a listening mark.
        if (action === 'listen' && shot.state.attempts.length === before.state.attempts.length) {
          pending = false; return;
        }
        let work;
        try { work = project(shot); } catch (_) { error(); return; }
        void api.send({name: 'act', action, work}).then(() => {
          pending = false;
          window.dispatchEvent(new CustomEvent('mira-activity-state-changed'));
        }).catch(error);
      }, 0);
    }
    ['click', 'keydown'].forEach(name => document.addEventListener(name, handle, true));
    return {restore(server) {
      try {
        const work = project(capture());
        aligned = server?.kind === 'science-sensory' && server.validator === 'science-sensory-p' + page + '.v1'
          && (server.lastWork === null ? !work.started && !work.firstGuess && !work.clues.length
            : stable(work) === stable(server.lastWork));
      } catch (_) { aligned = false; }
      api.restoreConfirmed(aligned);
    }, dispose() {
      disposed = true; clearTimeout(timer);
      if (window.miraActivityCheckpoint === guarded) window.miraActivityCheckpoint = checkpoint;
      ['click', 'keydown'].forEach(name => document.removeEventListener(name, handle, true));
    }};
  };
})();
