/* The authenticated host supplies the release/scene identity. Project work, not
 * local completed flags. Each page is also bound to its reviewed HTML hash. */
(function () {
  'use strict';
  window.installSplitAddCourseAdapter = function (sceneId, kind) {
    const page = Number(sceneId.replace('scene-p', ''));
    if (!/^math-(split|add)$/.test(kind) || !Number.isInteger(page) || page < 2 || page > 11) throw new Error('math_scene_unsupported');
    const api = window.miraCourseOperation;
    let aligned = false, disposed = false, pending = false, timer = null, previous = null;
    const checkpoint=window.miraActivityCheckpoint;
    const originalCapture=checkpoint.capture;
    const capture=()=>originalCapture.call(checkpoint);
    const guardedCapture=()=>pending||timer!==null?null:capture();
    checkpoint.capture=guardedCapture;
    const stable = value => JSON.stringify((function sort(v) {
      return Array.isArray(v) ? v.map(sort) : v && typeof v === 'object'
        ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v;
    })(value));
    const pick = (s, names) => Object.fromEntries(names.split(' ').map(k => [k, s[k]]));
    const ids = values => values.map(v => typeof v === 'object' ? v.id : v);
    function project() {
      const s = capture();
      if (!s || typeof s !== 'object') throw new Error('math_checkpoint_unavailable');
      if (kind === 'math-split') {
        if (page === 2) return {phase:s.phase, left:s.leftDock, right:s.rightDock, unsent:s.unsentBalls};
        if (page === 3) return pick(s.currentAllocation, 'left right');
        if (page === 4) return {left:s.left,right:s.right,beforeLeft:s.previousLeft,beforeRight:s.previousRight,
          predictionLeft:s.predictionLeft,predictionTotal:s.predictionTotal};
        if (page === 5) return pick(s, 'round left right prediction swaps');
        if (page === 6) return {round:s.round,left:s.leftBalls,right:s.rightBalls,prediction:s.predictedTotal,gateOpen:s.gateOpen};
        if (page === 7) return {photo:s.selectedPhotoId,whole:s.wholeValue,left:s.leftValue,right:s.rightValue};
        if (page === 8) return {round:s.currentRound,prediction:s.predictedCount,revealed:s.isRevealed};
        if (page === 9) return pick(s, 'total left right supply');
        if (page === 10) {
          const level = s.currentLevel, w = s.levelObjects[level];
          if (level === 0) return {level,left:w.filter(x=>x.dock==='left').map(x=>x.id),right:w.filter(x=>x.dock==='right').map(x=>x.id),prediction:null,revealed:false};
          if (level === 1) return {level,left:ids(w.left),right:ids(w.right),prediction:w.predictedTotal,revealed:w.gateOpen};
          return {level,left:ids(w.visible),right:ids(w.hidden),prediction:w.predictedHidden,revealed:w.revealed};
        }
        return {total:s.total,left:s.left,right:s.right,hiddenSide:s.hiddenDock,partnerGuess:s.partnerGuess,
          revealed:s.revealed,saved:s.savedPuzzles.at(-1)||null};
      }
      if (page === 2) return pick(s, 'round prediction gates');
      if (page === 3) return pick(s.slots, 'A B C');
      if (page === 4) return {strokes:s.strokes.map(x=>x.points.map(p=>[p.x,p.y])),a:ids(s.groups.a.lanterns),b:ids(s.groups.b.lanterns)};
      if (page === 5) return {original:s.markedOriginalIds,new:s.markedNewIds,total:s.selectedTotal};
      if (page === 6) return {method:s.currentMethod,original:s.countedOriginal,new:s.countedNew,order:s.countingOrder,left:s.partitionLeft,right:s.partitionRight};
      if (page === 7) return pick(s, 'left right plan');
      if (page === 8) return {order:s.state.order,prediction:s.state.guess};
      if (page === 9) return pick(s, 'leftDots rightDots eqLeft eqRight eqTotal');
      if (page === 10) return {level:s.currentLevel,answer:s.responses[s.currentLevel]??null};
      return {part1:s.part1.map(x=>pick(x,'id prop')),part2:s.part2.map(x=>pick(x,'id prop')),equation:s.equation};
    }
    function fresh(w) {
      if (kind === 'math-split') {
        if (page === 2) return w.phase===1&&!w.left.length&&!w.right.length;
        if (page === 3) return !w.left.length&&!w.right.length;
        if (page === 4) return w.predictionLeft===null&&w.predictionTotal===null&&stable(w.left)===stable(w.beforeLeft)&&stable(w.right)===stable(w.beforeRight);
        if (page === 5) return w.round===0&&w.swaps===0&&w.prediction===null;
        if (page === 6) return w.round===0&&w.prediction===null&&!w.gateOpen;
        if (page === 7) return w.whole===null&&w.left===null&&w.right===null;
        if (page === 8) return w.round===0&&w.prediction===null&&!w.revealed;
        if (page === 9) return !w.left.length&&!w.right.length;
        if (page === 10) return w.level===0&&!w.left.length&&!w.right.length;
        return !w.left.length&&!w.right.length&&w.saved===null&&!w.revealed;
      }
      if (page === 2) return w.round===0&&w.prediction===null&&!w.gates.some(Boolean);
      if (page === 3) return Object.values(w).every(v=>v===null);
      if (page === 4) return !w.strokes.length&&!w.a.length&&!w.b.length;
      if (page === 5) return !w.original.length&&!w.new.length&&w.total===null;
      if (page === 6) return w.method===null&&!w.order.length&&!w.left.length&&!w.right.length;
      if (page === 7) return w.left.length===1&&w.right.length===4&&!w.plan.length;
      if (page === 8) return w.order==='AB'&&w.prediction===null;
      if (page === 9) return stable(w)===stable({leftDots:1,rightDots:2,eqLeft:2,eqRight:2,eqTotal:4});
      if (page === 10) return w.level===0&&w.answer===null;
      return !w.part1.length&&!w.part2.length&&Object.values(w.equation).every(v=>v===null);
    }
    const splitSubmit = {2:'#sendBtn',3:'#takePhoto',5:'#sameBtn,#differentBtn',6:'#btnOpenGate',7:'#checkBtn',8:'#confirmBtn',9:'#btnVerdict',10:'[aria-label="验证总数"],[aria-label="掀开验证"]',11:'#btnReveal,[id$="Cover"]'};
    const addSubmit = {3:'#submitBtn',5:'#checkBtn',8:'.guess-number-btn',10:'.primary-action',11:'#saveBtn'};
    function automaticallyChecked() {
      const s=capture();
      if(kind==='math-split')return page===4?s.moveDone===true:page===10&&s.levelStatus[s.currentLevel]==='passed';
      if(page===2)return s.gates.every(Boolean);
      if(page===4)return s.combinedConfirmed===true;
      if(page===6)return s.roundCompleted===true;
      if(page===7)return s.phase==='equal';
      if(page===9)return s.completed===true;
      return false;
    }
    const helpSelector = 'button[id*="help" i],button[id*="hint" i],#btn-view-guide';
    function error() {aligned=false;pending=false;window.dispatchEvent(new Event('mira-course-operation-error'));}
    function handle(event) {
      if (!event.isTrusted || disposed) return;
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (!aligned || !api.ready || pending) {event.preventDefault();event.stopImmediatePropagation();return;}
      if (event.type==='keydown'&&!['Enter',' ','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
      const selector = (kind==='math-split'?splitSubmit:addSubmit)[page];
      const click = event.type==='click';
      let submit = click&&!!selector&&!!target.closest(selector);
      if(submit&&kind==='math-split'&&page===2)submit=capture().unsentBalls.length===1;
      if(submit&&kind==='math-split'&&page===11)submit=capture().phase==='guess';
      const help = click&&!!target.closest(helpSelector);
      clearTimeout(timer);
      timer=setTimeout(function settle(tries=0){
        if(disposed||!aligned||!api.ready)return;
        let snapshot;try{snapshot=capture();}catch(_){timer=null;error();return;}
        if(snapshot===null){
          if(tries>=250){timer=null;error();return;}
          timer=setTimeout(()=>settle(tries+1),40);return;
        }
        timer=null;
        let work;try{work=project();}catch(_){error();return;}
        const encoded=stable(work), changed=encoded!==previous;
        if(!changed&&!submit&&!help)return;
        pending=true;
        // Local feedback tells us when the page checked an attempt, not whether
        // it is correct. The server independently evaluates the projected work.
        const name=help?'help':submit||(changed&&automaticallyChecked())?'submit':'work';
        void api.send({name,work}).then(()=>{previous=encoded;pending=false;window.dispatchEvent(new CustomEvent('mira-activity-state-changed'));}).catch(error);
      },0);
    }
    const events=['click','pointerup','keydown','drop'];
    events.forEach(name=>document.addEventListener(name,handle,true));
    return {restore(server){
      try{const work=project();previous=stable(work);aligned=server?.kind===kind&&server.validator===kind+'-p'+page+'.v1'&&(server.lastWork===null?fresh(work):previous===stable(server.lastWork));}catch(_){aligned=false;}
      api.restoreConfirmed(aligned);
    },dispose(){disposed=true;clearTimeout(timer);if(checkpoint.capture===guardedCapture)checkpoint.capture=originalCapture;events.forEach(name=>document.removeEventListener(name,handle,true));}};
  };
})();
