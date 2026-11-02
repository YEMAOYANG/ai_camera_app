/* Bound by the authenticated release HTML hash. Submit mathematical artifacts,
 * never checkpoint completion flags. Audio-only and replay events earn no credit. */
(function () {
  'use strict';
  window.installMathCourseAdapter = function (sceneId, kind) {
    const page = Number(sceneId.replace('scene-p', ''));
    const api = window.miraCourseOperation;
    let aligned = false, previous = null, disposed = false;
    const stable = value => JSON.stringify((function sort(v){return Array.isArray(v) ? v.map(sort) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k=>[k,sort(v[k])])) : v;})(value));
    const pick = (s, keys) => Object.fromEntries(keys.map(k => [k, s[k]]));
    function work() {
      const s = window.miraActivityCheckpoint.capture();
      if (kind === 'math-compare') {
        if (page === 2) return {preset:s.snapshot.state.presetIndex, assignments:s.snapshot.state.cups.map(c=>c.assignedTo)};
        if (page === 3) return {pairs:s.pairs};
        if (page === 4) return {leftCount:s.leftCount,rightCount:s.rightCount,openSide:s.signOpenDirection};
        if (page === 5) return pick(s,['round','left','right']);
        if (page === 6) return pick(s,['index','strokes']);
        if (page === 7) return {round:s.round,marked:[...s.marked].sort(),sign:s.sign};
        return {relation:s.currentRelation,left:s.leftItems.map(x=>pick(x,['uid','type'])),right:s.rightItems.map(x=>pick(x,['uid','type']))};
      }
      if (page === 2) return {phase:s.world.phase,inside:s.world.inside};
      if (page === 3) return pick(s.state,['mode','task','atDoor']);
      if (page === 4) return {round:s.state.round,left:s.state.predicted.left,right:s.state.predicted.right};
      if (page === 5) return pick(s,['phase','order']);
      if (page === 6) return {direction:s.direction,answer:s.chosen||s.wrong};
      if (page === 7) return {round:s.round,opened:s.opened,direction:s.dir,rank:s.rank};
      return {phase:s.phase,departure:s.departure||s.wrongId,docked:s.docked};
    }
    const compareSubmit = {2:'#btn-check',3:'#checkPairBtn',4:'#comparisonSign,#confirmDirectionBtn',5:'#check',6:'#check',7:'#check',8:'#btnSave'};
    const ordinalSubmit = {2:'#door',3:'#door',4:'#ranks button',5:'#check',6:'.actor',7:'.window,#check',8:'.ship,#check'};
    const help = '#btn-hint,#hint,#help,#btnHelp,#pairViewBtn';
    function handle(event) {
      if (!event.isTrusted || disposed || !aligned || !api.ready) return;
      const target = event.target instanceof Element ? event.target : null;
      setTimeout(() => {
        const before = previous;
        if (disposed || !aligned || !api.ready) return;
        let value;
        try { value = work(); } catch (_) { aligned = false; return; }
        const encoded = stable(value), changed = encoded !== before;
        const click = event.type === 'click';
        let submit = click && !!target?.closest((kind === 'math-compare' ? compareSubmit : ordinalSubmit)[page]);
        // Dragging directly through the door has the same outcome as its button.
        if (kind === 'math-ordinal' && [2,3].includes(page) && changed && !click && event.type === 'pointerup') submit = true;
        if (kind === 'math-ordinal' && page === 3 && value.mode !== 'practice') submit = false;
        if (kind === 'math-ordinal' && page === 6 && !value.direction) submit = false;
        if (kind === 'math-ordinal' && page === 7 && value.round >= 2 && !target?.closest('#check')) submit = false;
        if (kind === 'math-ordinal' && page === 8 && value.phase === 'quantity' && !target?.closest('#check')) submit = false;
        // A disabled/no-op choice does not manufacture a new response.
        if (submit && !changed && !target?.closest('button[id*="check"],#checkPairBtn,#btnSave,#confirmDirectionBtn')) submit = false;
        const assistance = click && !!target?.closest(help);
        if (!changed && !submit && !assistance) return;
        previous = encoded;
        void api.send({name: assistance ? 'help' : submit ? 'submit' : 'work', work:value}).catch(()=>{aligned=false;});
      }, 0);
    }
    const events = ['click','pointerup','drop'];
    events.forEach(name=>document.addEventListener(name,handle,true));
    return {restore(server) {
      try {
        const value = work(); previous = stable(value);
        aligned = !!server && server.kind === kind && server.validator === 'math-'+kind.replace('math-','')+'-p'+page+'.v1'
          && (server.lastWork === null || previous === stable(server.lastWork));
      } catch (_) {aligned=false;}
      api.restoreConfirmed(aligned);
    },dispose(){disposed=true;events.forEach(name=>document.removeEventListener(name,handle,true));}};
  };
})();
