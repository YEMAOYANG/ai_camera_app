/* Captures real inputs only; completion is computed by the server. */
(function installAutumnP4P7() {
  'use strict';
  let scene = null, aligned = false, drag = null, stroke = null, keyboardMove = null;
  const api = () => window.miraCourseOperation;
  const ready = () => !!(scene && aligned && api()?.ready);
  const emit = value => { if (ready()) void api().send(value).catch(() => {}); };
  const closest = (event, selector) => event.target instanceof Element ? event.target.closest(selector) : null;
  const block = event => {
    if (ready()) return false;
    event.preventDefault(); event.stopImmediatePropagation(); return true;
  };
  const capture = () => { try { return window.miraActivityCheckpoint?.capture(); } catch (_) { return null; } };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  // Keep both endpoints and evenly sample long pointer paths. The same function
  // is used for checkpoint comparison, never to generate an operation on restore.
  const compact = points => points.length <= 256 ? points : Array.from({length:256}, (_, i) => points[Math.round(i * (points.length - 1) / 255)]);
  const normalizedStrokes = paths => paths.map(points => compact(points.map(p => Array.isArray(p) ? {x:p[0],y:p[1]} : p)));
  function compare(id, server) {
    const shot = capture(), d = shot?.domainState;
    if (!d || !server || typeof server.completed !== 'boolean') return false;
    if (id === 'scene-p4') return same(d.slots, server.slots) && !!d.started === (server.phase !== 'ready') && !!d.completed === server.completed;
    if (id === 'scene-p5') return d.index === server.index && same(d.placedChars, server.placed) &&
      same([...d.heardCharacters].sort(), [...server.listenRequested].sort()) && !!d.compareDone === server.compared &&
      same([...d.compareHeard].sort(), [...server.compareRequested].sort()) && (shot.feedbackPhase !== 'ready') === (server.phase !== 'ready') &&
      (shot.feedbackPhase === 'level_complete') === server.completed;
    if (id === 'scene-p6') {
      const chars = [['了','Liao'], ['子','Zi']];
      for (const [key, suffix] of chars) {
        const mode = d['versionModeFor' + suffix];
        const page = d['strokes' + suffix + (mode === 'redo' ? 'Redo' : 'Try')];
        const remote = server.strokes?.[key];
        if (!Array.isArray(page) || !Array.isArray(remote) || !same(normalizedStrokes(page), normalizedStrokes(remote))) return false;
        const otherMode = mode === 'redo' ? 'try' : 'redo';
        const other = d['strokes' + suffix + (otherMode === 'redo' ? 'Redo' : 'Try')];
        if (!Array.isArray(other) || !Array.isArray(server.versions?.[otherMode]?.[key]) ||
            !same(normalizedStrokes(other), normalizedStrokes(server.versions[otherMode][key]))) return false;
      }
      return d.versionModeForLiao === d.versionModeForZi && d.versionModeForLiao === server.versionMode &&
        !!d.started === (server.phase !== 'ready') && (!!d.completedChars?.liao && !!d.completedChars?.zi) === server.completed;
    }
    if (id === 'scene-p7') return shot.level === server.level && Math.abs(d.blue - server.blue) < 1e-7 &&
      Math.abs(d.horizonHeight - server.horizon) < 1e-7 && same(d.expressionChoices, server.choices) &&
      !!d.startDone === (server.phase !== 'ready');
    return false;
  }
  window.addEventListener('mira-course-operation-restore', event => {
    if (!['scene-p4','scene-p5','scene-p6','scene-p7'].includes(event.detail?.sceneId)) return;
    scene = event.detail.sceneId;
    try { aligned = compare(scene, event.detail.serverState); } catch (_) { aligned = false; }
    api()?.restoreConfirmed(aligned);
  });
  document.addEventListener('pointerdown', event => {
    if (!event.isTrusted || !scene) return;
    if (scene === 'scene-p4') {
      const token = closest(event, '.token[data-token-id]');
      if (token && !block(event) && capture()?.domainState?.completed) {
        event.preventDefault(); event.stopImmediatePropagation(); return;
      }
      if (token && ready() && capture()?.domainState?.started)
        drag = {id: event.pointerId, token: token.dataset.tokenId, element: token,
          wasPlaced: Object.values(capture()?.domainState?.slots || {}).includes(token.dataset.tokenId)};
    } else if (scene === 'scene-p5' && closest(event, '#target')) {
      if (!block(event)) drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
    } else if (scene === 'scene-p6') {
      const canvas = closest(event, '#canvasLiao,#canvasZi');
      if (!canvas || block(event) || !capture()?.domainState?.started) return;
      const box = canvas.getBoundingClientRect();
      const point = e => ({x: (e.clientX-box.left)*180/box.width, y: (e.clientY-box.top)*180/box.height});
      stroke = {id:event.pointerId, character:canvas.id === 'canvasLiao' ? '了' : '子', point,
        before: capture(), points:[point(event)]};
    }
  }, true);
  document.addEventListener('pointermove', event => {
    if (event.isTrusted && stroke && stroke.id === event.pointerId && ready() && stroke.points.length < 10000) stroke.points.push(stroke.point(event));
  }, true);
  document.addEventListener('pointercancel', () => { drag = null; stroke = null; }, true);
  document.addEventListener('pointerup', event => {
    if (!event.isTrusted || !scene || !ready()) return;
    if (scene === 'scene-p4' && drag && drag.id === event.pointerId) {
      const rect = drag.element.getBoundingClientRect(), x = rect.left + rect.width/2, y = rect.top + rect.height/2;
      const slot = [...document.querySelectorAll('.slot[data-slot-id]')].find(el => {
        const r=el.getBoundingClientRect(); return x>=r.left && x<=r.right && y>=r.top && y<=r.bottom;
      });
      if (slot) emit({name:'place',token:drag.token,slot:slot.dataset.slotId});
      else if (drag.wasPlaced) emit({name:'return',token:drag.token});
      drag = null;
    } else if (scene === 'scene-p5' && drag && drag.id === event.pointerId) {
      if (Math.hypot(event.clientX-drag.x,event.clientY-drag.y) >= 12) {
        const item = document.elementsFromPoint(event.clientX,event.clientY).find(el => el.matches?.('[data-object]'));
        const shot = capture(), d = shot?.domainState;
        if (item && d && !['ready','compare','level_complete'].includes(shot.feedbackPhase) &&
            d.heardCharacters.includes(d.index) && !d.placedChars[d.index]) emit({name:'choose',object:item.dataset.object});
      }
      drag = null;
    }
  }, true);
  // Bubble phase runs after the native canvas pointerup handler has stored its
  // attempt, but still before any subsequent click or new user input.
  document.addEventListener('pointerup', event => {
    if (!event.isTrusted || scene !== 'scene-p6' || !ready() || !stroke || stroke.id !== event.pointerId) return;
    const completedStroke = stroke; stroke = null;
    const after = capture(), before = completedStroke.before;
    if (!after || !before) return;
    const suffix = completedStroke.character === '了' ? 'Liao' : 'Zi';
    const mode = after.domainState['versionModeFor' + suffix] === 'redo' ? 'Redo' : 'Try';
    const previous = before.domainState['strokes' + suffix + mode], current = after.domainState['strokes' + suffix + mode];
    if (Array.isArray(previous) && Array.isArray(current) &&
        (!same(previous, current) || !same(before.revisionHistory, after.revisionHistory)))
      emit({name:'stroke',character:completedStroke.character,points:compact(completedStroke.points)});
  });
  document.addEventListener('click', event => {
    if (!event.isTrusted || !scene) return;
    let item;
    if (scene === 'scene-p4') {
      item=closest(event,'#startOverlay,#startFootprint,#btnGuide,#btnReset,.slot[data-slot-id]');
      if (!item || block(event)) return;
      const started = !!capture()?.domainState?.started;
      if (!started && (item.id === 'startOverlay' || item.id === 'startFootprint')) emit({name:'start'});
      else if (started && item.id === 'btnGuide') emit({name:'hint'});
      else if (started && item.id === 'btnReset') emit({name:'reset'});
      else if (started && item.dataset.slotId) {
        if (capture()?.domainState?.completed) { event.preventDefault(); event.stopImmediatePropagation(); return; }
        const token=document.querySelector('.token.selected[data-token-id]');
        if (token) emit({name:'place',token:token.dataset.tokenId,slot:item.dataset.slotId});
      }
    } else if (scene === 'scene-p5') {
      item=closest(event,'#startBtn,#target,#replay,#reset,#next,#qiu,#hui,#compareDone,[data-object]');
      if (!item || block(event)) return;
      const shot=capture();
      if (item.id === 'startBtn' && shot?.feedbackPhase === 'ready') emit({name:'start'});
      else if (shot?.feedbackPhase !== 'ready') {
        const d=shot.domainState;
        if (shot.feedbackPhase === 'level_complete') return;
        if ((item.id === 'target' || item.id === 'replay') && shot.feedbackPhase !== 'compare') emit({name:'listen'});
        else if (item.id === 'reset' && shot.feedbackPhase !== 'compare') emit({name:'reset'});
        else if (item.id === 'next' && d.placedChars[d.index]) emit({name:'next'});
        else if ((item.id === 'qiu' || item.id === 'hui') && shot.feedbackPhase === 'compare') emit({name:'compareListen',value:item.id});
        else if (item.id === 'compareDone' && shot.feedbackPhase === 'compare' && d.compareHeard.includes('qiu') && d.compareHeard.includes('hui')) emit({name:'compareDone'});
        else if (item.dataset.object && shot.feedbackPhase !== 'compare' && d.heardCharacters.includes(d.index) && !d.placedChars[d.index]) emit({name:'choose',object:item.dataset.object});
      }
    } else if (scene === 'scene-p6') {
      item=closest(event,'#startPencilBtn,#undoBtn,#demoBtn,#retryBtn,#versionTryBtn,#versionRedoBtn');
      if (!item || block(event)) return;
      const d=capture()?.domainState;
      if (item.id === 'startPencilBtn' && !d?.started) emit({name:'start'});
      else if (d?.started && item.id === 'demoBtn') emit({name:'hint'});
      else if (d?.started && item.id === 'retryBtn') emit({name:'retry'});
      else if (d?.started && item.id === 'versionTryBtn') emit({name:'version',mode:'try'});
      else if (d?.started && item.id === 'versionRedoBtn') emit({name:'version',mode:'redo'});
      else if (d?.started && item.id === 'undoBtn' && ['了','子'].includes(d.currentChar)) emit({name:'undo',character:d.currentChar});
    } else {
      item=closest(event,'#startAction,#blueKnob,#heightKnob,#expressionSo,#expressionBoth,#nextSky,#resetBtn,#helpBtn');
      if (!item || block(event)) return;
      const d=capture()?.domainState;
      if (item.id === 'startAction' && !d?.startDone) emit({name:'start'});
      else if (d?.startDone) {
        const names={blueKnob:'blue',heightKnob:'height',nextSky:'nextSky',resetBtn:'reset',helpBtn:'hint'};
        if (names[item.id]) emit({name:names[item.id]});
        else if (item.id === 'expressionSo' || item.id === 'expressionBoth') emit({name:'choose',value:item.id === 'expressionSo' ? 'so' : 'both'});
      }
    }
  }, true);
  document.addEventListener('keydown', event => {
    if (!event.isTrusted || scene !== 'scene-p4') return;
    if ((event.key === 'Enter' || event.key === ' ') && closest(event, '#startOverlay')) {
      if (!block(event) && !capture()?.domainState?.started) emit({name:'start'});
      return;
    }
    const token = closest(event, '.token[data-token-id]');
    if (!token || !['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key) || block(event)) return;
    keyboardMove = {before: capture()?.domainState?.slots, id: token.dataset.tokenId};
  }, true);
  document.addEventListener('keydown', event => {
    if (!event.isTrusted || scene !== 'scene-p4' || !keyboardMove) return;
    const {before, id} = keyboardMove; keyboardMove = null;
    const after = capture()?.domainState?.slots;
    if (!before || !after || same(before, after)) return;
    const slot = Object.keys(after).find(k => after[k] === id);
    if (slot) emit({name:'place',token:id,slot});
  });
})();
