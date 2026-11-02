/* Install inside the authenticated, content-hash-bound Autumn iframe only. */
(function installAutumnP2P3() {
  'use strict';
  let sceneId = null;
  let drag = null;
  let aligned = false;
  const api = () => window.miraCourseOperation;
  const ready = () => !!(api() && api().ready && sceneId && aligned);
  const emit = operation => { if (ready()) void api().send(operation).catch(() => {}); };
  const key = event => event.key === 'Enter' || event.key === ' ';
  const target = (event, selector) => event.target instanceof Element ? event.target.closest(selector) : null;
  const blocked = event => {
    if (ready()) return false;
    event.preventDefault();
    event.stopImmediatePropagation();
    return true;
  };
  const p2Started = () => document.querySelector('#start-layer')?.classList.contains('hidden');
  const p2Complete = () => document.querySelector('#feedback-panel')?.classList.contains('success') &&
    [...document.querySelectorAll('.mirror-slot')].every(slot => slot.classList.contains('filled'));
  const p2Slot = slot => {
    if (!p2Started() || p2Complete()) return;
    const index = Number(slot.dataset.slot);
    if (!Number.isInteger(index) || index < 0 || index > 2) return;
    if (slot.classList.contains('filled')) emit({name: 'retract', slot: index});
    else if (document.querySelector('.evidence-card.selected')) {
      const filled = document.querySelectorAll('.mirror-slot.filled').length;
      emit({name: 'place', slot: index});
      if (filled === 2) emit({name: 'submit'}); // page submits automatically when the last slot fills
    }
  };
  const p3Started = () => document.querySelector('#startOverlay')?.classList.contains('hidden');
  const p3Count = () => document.querySelectorAll('#leafLayer .leaf').length;
  const p3Operation = name => {
    if (!p3Started()) return;
    if (name === 'add' && p3Count() >= 9) return;
    if ((name === 'remove' || name === 'submit') && p3Count() === 0) return;
    emit({name});
  };
  function compareServerState(id, server) {
    if (!server || typeof server !== 'object' || typeof server.completed !== 'boolean' || typeof server.phase !== 'string') return false;
    let snapshot;
    try { snapshot = window.miraActivityCheckpoint?.capture(); } catch (_) { return false; }
    if (!snapshot || snapshot.version !== 1 || !snapshot.domainState) return false;
    if (id === 'scene-p2') {
      const values = snapshot.childDecision;
      if (!Array.isArray(values) || values.length !== 3 || !Array.isArray(server.slots) || server.slots.length !== 3 ||
          !Object.prototype.hasOwnProperty.call(server, 'selected') || !Object.prototype.hasOwnProperty.call(snapshot.domainState, 'selectedEvidence') ||
          typeof snapshot.domainState.completed !== 'boolean') return false;
      return JSON.stringify(values) === JSON.stringify(server.slots) && snapshot.domainState.selectedEvidence === server.selected &&
        snapshot.domainState.completed === server.completed && (snapshot.feedbackPhase === 'ready') === (server.phase === 'ready');
    }
    const child = snapshot.childDecision;
    if (!child || !Number.isInteger(child.leafCount) || !['left','right'].includes(child.windDirection) ||
        !Number.isInteger(server.leafCount) || !['left','right'].includes(server.wind)) return false;
    return child.leafCount === server.leafCount && child.windDirection === server.wind &&
      (snapshot.feedbackPhase === 'ready') === (server.phase === 'ready') &&
      (!server.completed || (snapshot.feedbackPhase === 'complete' && snapshot.domainState.submittedCount === server.leafCount));
  }
  window.addEventListener('mira-course-operation-restore', event => {
    if (event.detail && ['scene-p2', 'scene-p3'].includes(event.detail.sceneId)) {
      sceneId = event.detail.sceneId;
      aligned = compareServerState(sceneId, event.detail.serverState);
      api()?.restoreConfirmed(aligned);
    }
  });
  document.addEventListener('pointerdown', event => {
    if (!event.isTrusted || sceneId !== 'scene-p2') return;
    const card = target(event, '.evidence-card');
    if (!card) return;
    if (blocked(event) || !p2Started() || p2Complete()) return;
    drag = {pointerId: event.pointerId};
    emit({name: 'select', value: card.dataset.evidence});
  }, true);
  document.addEventListener('pointerup', event => {
    if (!event.isTrusted || sceneId !== 'scene-p2' || !drag || drag.pointerId !== event.pointerId) return;
    drag = null;
    if (blocked(event)) return;
    const slot = document.elementFromPoint(event.clientX, event.clientY);
    // The native page places only when elementFromPoint is the slot itself.
    if (slot && slot.classList.contains('mirror-slot') && !slot.classList.contains('filled')) p2Slot(slot);
  }, true);
  document.addEventListener('pointercancel', () => { drag = null; }, true);
  document.addEventListener('click', event => {
    if (!event.isTrusted || !sceneId) return;
    if (sceneId === 'scene-p2') {
      const item = target(event, '#start-windchime,.mirror-slot,#btn-reset,#btn-hint');
      if (!item || blocked(event)) return;
      if (item.id === 'start-windchime' && !p2Started()) emit({name: 'start'});
      else if (item.classList.contains('mirror-slot')) p2Slot(item);
      else if (p2Started() && !p2Complete() && item.id === 'btn-reset') emit({name: 'reset'});
      else if (p2Started() && !p2Complete() && item.id === 'btn-hint') emit({name: 'hint'});
    } else {
      const item = target(event, '#startButton,#addLeafBtn,#removeLeafBtn,#windBtn,#submitBtn,#resetBtn');
      if (!item || blocked(event)) return;
      if (item.id === 'startButton' && !p3Started()) emit({name: 'start'});
      else {
        const names = {addLeafBtn:'add',removeLeafBtn:'remove',windBtn:'toggleWind',submitBtn:'submit',resetBtn:'reset'};
        if (names[item.id]) p3Operation(names[item.id]);
      }
    }
  }, true);
  document.addEventListener('keydown', event => {
    if (!event.isTrusted || !sceneId) return;
    if (sceneId === 'scene-p2' && key(event)) {
      const item = target(event, '#start-windchime,.evidence-card,.mirror-slot,#btn-reset,#btn-hint');
      if (!item || blocked(event)) return;
      if (item.id === 'start-windchime' && !p2Started()) emit({name: 'start'});
      else if (item.classList.contains('evidence-card') && p2Started() && !p2Complete()) emit({name:'select',value:item.dataset.evidence});
      else if (item.classList.contains('mirror-slot')) p2Slot(item);
      else if (p2Started() && !p2Complete() && item.id === 'btn-reset') emit({name:'reset'});
      else if (p2Started() && !p2Complete() && item.id === 'btn-hint') emit({name:'hint'});
    } else if (sceneId === 'scene-p3') {
      if (target(event, '#startButton') && key(event)) {
        if (!blocked(event) && !p3Started()) emit({name:'start'});
        return;
      }
      const names = {ArrowRight:'toggleWind','+':'add','=':'add','-':'remove','_':'remove',r:'reset',R:'reset'};
      const name = event.key === 'Enter' && !target(event, '#submitBtn,#startButton') ? 'submit' : names[event.key];
      if (name && !blocked(event)) p3Operation(name);
    }
  }, true);
})();
