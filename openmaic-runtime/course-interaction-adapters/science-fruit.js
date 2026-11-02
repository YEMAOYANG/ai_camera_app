/* Fruit observation: report bounded semantic inputs; never local completion flags. */
(function () {
  'use strict';
  window.installScienceFruitAdapter = function (sceneId) {
    const page = Number(sceneId.replace('scene-p', ''));
    const api = window.miraCourseOperation, checkpoint = window.miraActivityCheckpoint;
    let aligned = false, disposed = false, pending = false, timer = null, committed = null, queuedAction = 'picture', recovery = false;
    const recoveryReset = page===8 ? 'btnReset' : 'resetBtn';
    const capture = () => checkpoint.capture();
    const stable = x => JSON.stringify((function sort(v) {
      return Array.isArray(v) ? v.map(sort) : v && typeof v === 'object'
        ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v;
    })(x));
    // Historical attempt metadata is durable assessment evidence, but several
    // authored checkpoints intentionally restore only the visible world.  It
    // must not reject an otherwise exact decision/domain recovery.
    const restoreComparable = x => x && typeof x === 'object' && !Array.isArray(x)
      ? Object.fromEntries(Object.entries(x).filter(([key]) => key !== 'response')) : x;
    function project(s) {
      if (s?.version !== 1 || !s.domainState) throw new Error('fruit_checkpoint_unavailable');
      const x = s.domainState;
      let decision = s.childDecision, domain = {};
      if (page === 3) decision = decision.map(e => ({label:e.label, region:e.region, rotation:e.rotation}));
      if (page === 4) {decision=decision.map(e=>({text:e.text,kind:e.kind}));domain={force:x.currentForce};}
      if (page === 6) domain={swaps:x.swapCount,fruits:Object.fromEntries(['apple','tomato'].map(k=>[k,{angle:x.fruits[k].angle,force:x.fruits[k].probeForce}]))};
      if (page === 8) domain={standard:x.currentStandard};
      if (page === 9) domain={standard:x.selectedStandard};
      if (page === 10) {decision=x.currentJudgment;domain={phase:x.phase,tool:x.selectedTool,top:x.measuredTop,bottom:x.measuredBottom,count:x.judgementCount};}
      if (page === 11) {decision=Object.fromEntries(decision.map(f=>[f.id,f.currentGroup]));
        domain={phase:x.phase,senses:x.selectedSenses,force:x.force,view:x.view,probes:x.probeRound,exchanged:x.exchanged,standard:x.classificationStandard};}
      return JSON.parse(JSON.stringify({started:page===6?s.started:x.started,decision,domain,help:s.helpCount,first:s.firstAnswer??null,response:x.lastAttempt??x.firstCheck??s.undoHistory?.at(-1)??null}));
    }
    const guarded=Object.freeze({...checkpoint,capture(){return pending || timer!==null ? null : capture();}});
    window.miraActivityCheckpoint=guarded;
    function error(){aligned=false;pending=false;clearTimeout(timer);timer=null;window.dispatchEvent(new Event('mira-course-operation-error'));}
    function handle(event){
      if (!event.isTrusted || disposed) return;
      if (event.type==='keydown' && !['Enter',' ','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
      const target=event.target instanceof Element ? event.target : null;
      const control=target?.closest('button,[role="button"],[tabindex],input,[draggable],svg,#loupe,#labCanvas,#gameStage');
      // Pointer release outside a draggable still commits its final domain state.
      if (!control && !['pointerup','mouseup','touchend','drop'].includes(event.type)) return;
      if (event.type==='keydown' && control?.tagName==='BUTTON' && ['Enter',' '].includes(event.key)) return;
      if (!aligned || !api.ready || pending || (recovery && control?.id !== recoveryReset)){
        event.preventDefault();event.stopImmediatePropagation();return;
      }
      if (event.type==='pointerdown') return;
      queuedAction=(control?.id || target?.closest('[id]')?.id || 'picture').slice(0,120);
      if(timer!==null)return;
      const before=committed;
      timer=setTimeout(function settle(tries=0){
        if (disposed || !aligned || !api.ready) {error();return;}
        let shot;
        try {shot=capture();}catch(_){error();return;}
        if (!shot){if(tries>=1500){error();return;}timer=setTimeout(()=>settle(tries+1),40);return;}
        timer=null;
        // Page 7/8 local-only work was never accepted by the server. On the
        // explicit retry, start a fresh evidence history instead of importing
        // those unverified answers from the visual checkpoint.
        if(recovery && page!==6 && queuedAction===recoveryReset){
          shot={...shot,firstAnswer:null,helpCount:0,undoHistory:[]};
          if(checkpoint.restore(shot)!==true){error();return;}
          shot=capture();
        }
        let work;
        try {work=project(shot);}catch(_){error();return;}
        const action=queuedAction;
        const explicit=(page===9 && action==='shakeBtn') || (page===10 && action==='applyReviseBtn');
        if (stable(before)===stable(work) && !explicit){pending=false;return;}
        const name=recovery?'work':work.help>before.help?'help':!before.started || (page===6 && action==='resetBtn')?'work':'submit';
        pending=true;
        void api.send({name,action,work}).then(()=>{
          committed=work;pending=false;recovery=false;window.dispatchEvent(new CustomEvent('mira-activity-state-changed'));
        }).catch(error);
      },0);
    }
    const events=['click','keydown','pointerdown','pointerup','mouseup','touchend','drop'];
    events.forEach(n=>document.addEventListener(n,handle,true));
    return {restore(server){
      try {
        const work=project(capture());
        committed=work;
        aligned=server?.kind==='science-fruit' && server.validator==='science-fruit-p'+page+'.v1' &&
          (server.lastWork===null ? !work.started && work.help===0
            : stable(restoreComparable(work))===stable(restoreComparable(server.lastWork)));
        // A legacy page-six start could leave visible work beyond the first
        // server-accepted action. Do not turn the local snapshot into graded
        // events: allow only the child's explicit reset and then a real retry.
        recovery=!aligned && work.started===true && server?.completed===false &&
          Array.isArray(server.attempts) && server.attempts.length===0 &&
          Array.isArray(server.milestones) && server.milestones.length===0 &&
          (page===6 && server?.lastWork?.started===true || [7,8].includes(page) && server?.lastWork===null);
        if(recovery){
          aligned=true;
          const notice=document.getElementById?.(page===8?'feedbackBubble':page===7?'zoneFeedback':'feedbackLine');
          if(notice)notice.textContent=page===8?'刚才的分类需要重新记录，请点重排，再试一次。':'刚才的比较需要重新记录，请点重置，再试一次。';
        }
      }catch(_){aligned=false;recovery=false;}
      api.restoreConfirmed(aligned);
    },dispose(){disposed=true;clearTimeout(timer);if(window.miraActivityCheckpoint===guarded)window.miraActivityCheckpoint=checkpoint;
      events.forEach(n=>document.removeEventListener(n,handle,true));}};
  };
})();
