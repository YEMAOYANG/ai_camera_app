/* Development adapter, not integrated into the runtime or play-accepted.
 * Projections are added only after inspecting the saved authored checkpoint.
 * The host binds the exact release HTML and supplies scene identity. A local
 * success flag, help counter, default answer, or timer never earns evidence.
 * The 26 projections follow inspected reviewed sources. Object identities,
 * explicit predictions, screen ink, links and saved stories remain distinct.
 * This adapter does not certify content, narration, restoration or real play.
 * Final release integration requires comparing these projections with the
 * frozen saved HTML. Unmapped pages fail closed.
 */
(function () {
  'use strict';
  const stable = value => JSON.stringify((function sort(v) {
    return Array.isArray(v) ? v.map(sort) : v && typeof v === 'object'
      ? Object.fromEntries(Object.keys(v).sort().map(key => [key, sort(v[key])])) : v;
  })(value));
  const checkpointHandoffs=new WeakMap();
  function holdCheckpointInput(checkpoint){
    const types=['click','keydown','keyup','pointerdown','pointerup','pointercancel','input','change'];
    const stop=event=>{event.preventDefault();event.stopImmediatePropagation();};
    const message=event=>{if(event.source===window.parent&&(event.data?.type==='SET_WIDGET_STATE'
      ||event.data?.type==='MIRA_INTERACTIVE_AUDIO_CONTROL'&&event.data?.command==='play'))stop(event);};
    types.forEach(type=>document.addEventListener(type,stop,true));window.addEventListener('message',message,true);
    return {checkpoint,released:false,release(){if(this.released)return;this.released=true;
      types.forEach(type=>document.removeEventListener(type,stop,true));window.removeEventListener('message',message,true);}};
  }
  const crateIds = Object.freeze(['crate_1', 'crate_2', 'crate_3', 'crate_4', 'crate_5']);
  const requireValue = value => { if (!value) throw new Error('math_checkpoint_unavailable'); };
  function subtractOne(shot) {
    requireValue(shot && typeof shot === 'object' && shot.version === 1 && shot.domainState
      && ['ready', 'playing', 'feedback', 'success'].includes(shot.phase));
    const crates = shot.domainState.crates, ids = shot.stableObjectIds;
    requireValue(Array.isArray(ids) && ids.length === 5 && new Set(ids).size === 5
      && ids.every(id => crateIds.includes(id)) && Array.isArray(crates) && crates.length === 5
      && new Set(crates.map(crate => crate.id)).size === 5);
    const removed = [], remaining = [];
    for (const crate of crates) {
      requireValue(crate && crateIds.includes(crate.id) && ['warehouse', 'truck'].includes(crate.state));
      (crate.state === 'truck' ? removed : remaining).push(crateIds.indexOf(crate.id) + 1);
    }
    const prediction = shot.domainState.prediction;
    requireValue((prediction === null || Number.isInteger(prediction) && prediction >= 0 && prediction <= 5)
      && prediction === shot.prediction);
    return {removed: removed.sort((a, b) => a-b), remaining: remaining.sort((a, b) => a-b), prediction};
  }
  function freshSubtractOne(shot, work) {
    return ['ready', 'playing'].includes(shot.phase) && work.removed.length === 0
      && work.prediction === null && shot.firstAttempt === null
      && Array.isArray(shot.revisionHistory) && shot.revisionHistory.length === 0
      && shot.currentWorkVersion === 1;
  }
  function subtractOneAction(event, target) {
    const control = target.closest('#predMinusBtn,#predPlusBtn,#sendTruckBtn,#replayBtn,#hintBtn,#resetBtn');
    const crate = target.closest('[data-crate-id]');
    if (event.type === 'pointerdown' || event.type === 'pointercancel')
      return crate ? {name: 'gesture', crate} : null;
    if (event.type === 'pointerup') return crate ? {name: 'work', crate} : null;
    if (event.type === 'keydown') {
      // The authored page has an explicit document-level number-key handler.
      if (/^[0-5]$/.test(event.key)) return {name: 'predict', control: target};
      // Native buttons generate their own click; do not count Enter twice.
      if (crate && ['Enter', ' '].includes(event.key)) return {name: 'work', crate};
      return null;
    }
    // The authored tap-place handler acts only on the truck zone itself,
    // never on its descendant crates. Selection alone changes no work.
    if (event.type === 'click' && target.id === 'truckZone') return {name: 'work', control: target};
    if (event.type !== 'click' || !control) return null;
    const names = {predMinusBtn: 'predict', predPlusBtn: 'predict', sendTruckBtn: 'submit',
      replayBtn: 'replay', hintBtn: 'hint', resetBtn: 'retry'};
    return {name: names[control.id], control};
  }
  const connectionRoles = ['original', 'removed', 'remaining'];
  function subtractThree(shot) {
    requireValue(shot?.version === 1 && shot.sceneId === 'scene-p3' && shot.domainState
      && stable(shot.stableObjectIds) === stable(['b1', 'b2', 'b3', 'b4']));
    const links = shot.domainState.connections;
    requireValue(links && Object.keys(links).length === 3
      && connectionRoles.every(role => links[role] === null || connectionRoles.includes(links[role]))
      && (shot.domainState.selected === null || connectionRoles.includes(shot.domainState.selected)));
    const destination = value => value === 'original' ? 'before' : value;
    // The inspected scene fixes b1 as the transported object. The frozen
    // activity computes the displayed quantities; only links are child input.
    return {total: 4, removed: [1], remaining: [2, 3, 4],
      equation: {whole: 4, change: 1, result: 3},
      links: {whole: destination(links.original), change: destination(links.removed), result: destination(links.remaining)}};
  }
  function freshSubtractThree(shot, work) {
    return shot.firstAttempt === null && shot.currentWorkVersion === 0
      && Array.isArray(shot.revisionHistory) && shot.revisionHistory.length === 0
      && Object.values(work.links).every(value => value === null);
  }
  function subtractThreeAction(event, target) {
    if (event.type !== 'click') return null; // Native buttons own keyboard activation.
    const control = target.closest('#replay,#hint,#reset,#num-original,#num-removed,#num-remaining,#zone-original,#zone-removed,#zone-remaining');
    if (!control) return null;
    return {name: ({replay: 'replay', hint: 'hint', reset: 'retry'})[control.id]
      || (control.id.startsWith('zone-') ? 'connection' : 'work'), control};
  }
  const leftToolIds = ['L1', 'L2', 'L3', 'L4', 'L5'], rightToolIds = ['R1', 'R2', 'R3'];
  function subtractFive(shot) {
    requireValue(shot?.version === 1 && shot.sceneId === 'scene-p5' && shot.domainState
      && stable(shot.stableObjectIds) === stable(leftToolIds.concat(rightToolIds)));
    const d = shot.domainState;
    requireValue(Array.isArray(d.leftItems) && Array.isArray(d.removedLeft) && d.leftItems.length >= 1
      && d.leftItems.length + d.removedLeft.length === 5
      && new Set(d.leftItems.concat(d.removedLeft)).size === 5
      && d.leftItems.concat(d.removedLeft).every(id => leftToolIds.includes(id))
      && stable(d.rightItems) === stable(rightToolIds));
    // These are the visible system-drawn row pairs from the actual checkpoint,
    // not a claim that the child manually connected them or knew the answer.
    const displayedPairs = d.leftItems.slice(0, 3).map((id, i) => [id, rightToolIds[i]]);
    requireValue(stable(d.pairs) === stable(displayedPairs));
    return {removed: d.removedLeft.map(id => leftToolIds.indexOf(id) + 1).sort((a,b) => a-b),
      remaining: d.leftItems.map(id => leftToolIds.indexOf(id) + 1).sort((a,b) => a-b),
      pairs: d.pairs.map(([left, right]) => [leftToolIds.indexOf(left) + 1, rightToolIds.indexOf(right) + 1])};
  }
  function freshSubtractFive(shot, work) {
    return shot.firstAttempt === null && shot.currentWorkVersion === 0 && work.removed.length === 0
      && shot.domainState.checked === null && Array.isArray(shot.revisionHistory) && shot.revisionHistory.length === 0;
  }
  function subtractFiveAction(event, target) {
    if (event.type !== 'click') return null;
    const control = target.closest('#replay,#hint,#reset,#check,.toolbutton');
    return control ? {name: ({replay: 'replay', hint: 'hint', reset: 'retry', check: 'submit'})[control.id] || 'work', control} : null;
  }
  const subtractionProfiles = {
    1: {project: subtractOne, fresh: freshSubtractOne, action: subtractOneAction},
    3: {project: subtractThree, fresh: freshSubtractThree, action: subtractThreeAction},
    5: {project: subtractFive, fresh: freshSubtractFive, action: subtractFiveAction},
  };
  const zeroFields = {1: 'removed remaining answer', 2: 'context objects position meaning',
    3: 'order quantities', 4: 'mode strokes', 5: 'removed remaining equation links',
    6:'total removed remaining prediction',7:'incoming remaining gateOpen prediction',
    8:'removed remaining executed equation',9:'context total changed remaining executed operator equation',
    10:'operator changed remaining executed equation',11:'total operator changed remaining executed equation',
    12:'context objects position meaning',13:'story saved',14:'story saved zeroRole sourceWorkSha256 storyVersion recordVersion'};
  const exactKeys = (value, fields) => value && typeof value === 'object' && !Array.isArray(value)
    && stable(Object.keys(value).sort()) === stable(fields ? fields.split(' ').sort() : []);
  const ids = (values, maximum) => Array.isArray(values) && values.length <= maximum
    && values.every(value => Number.isInteger(value) && value >= 1 && value <= maximum)
    && new Set(values).size === values.length;
  const nullableNumber = (value, maximum = 5) => value === null || Number.isInteger(value) && value >= 0 && value <= maximum;
  const partition = (removed, remaining, total) => ids(removed, total) && ids(remaining, total)
    && removed.length + remaining.length === total && new Set([...removed, ...remaining]).size === total;
  const equationShape = value => exactKeys(value, 'whole change result') && Object.values(value).every(n => nullableNumber(n));
  const linksShape = value => exactKeys(value, 'whole change result')
    && Object.values(value).every(v => v === null || ['before','removed','remaining'].includes(v));
  const subtractStory = value => exactKeys(value, 'total removed remaining equation')
    && Number.isInteger(value.total) && value.total >= 2 && value.total <= 5
    && partition(value.removed, value.remaining, value.total) && equationShape(value.equation);
  // Flask JSON may reorder object keys. The reviewed pages compare equations
  // and stories using JSON.stringify, so reconstruct only their original key
  // order without changing a value, array order, attempt, history, or digest.
  function orderedSubtractStory(value,allowEmpty) {
    requireValue(subtractStory(value) && value.remaining.length>=1 && (allowEmpty||value.removed.length>=1)
      && value.equation.whole===value.total && value.equation.change===value.removed.length
      && value.equation.result===value.remaining.length);
    return {total:value.total,removed:value.removed,remaining:value.remaining,
      equation:{whole:value.equation.whole,change:value.equation.change,result:value.equation.result}};
  }
  window.prepareMathSubtractZeroCheckpoint = function(sceneId,contentSha256,shot) {
    const m=/^scene-p(6|11|12)$/.exec(sceneId),page=m?Number(m[1]):0;
    if(!page || openingHashes['math-subtract'][page]!==contentSha256)return shot;
    requireValue(shot && shot.version===1 && shot.sceneId===sceneId && shot.domainState
      && typeof shot.domainState==='object' && !Array.isArray(shot.domainState));
    const d=shot.domainState, result={...shot,domainState:{...d}};
    if(page===6){
      requireValue(exactKeys(d.equation,'whole change result')
        && Object.values(d.equation).every(v=>Number.isInteger(v)&&v>=1&&v<=5));
      result.domainState.equation={whole:d.equation.whole,change:d.equation.change,result:d.equation.result};
    } else if(page===11){
      result.domainState.story=orderedSubtractStory(d.story,true);
      result.domainState.saved=d.saved===null?null:orderedSubtractStory(d.saved,false);
      requireValue(Array.isArray(d.previousWorks)&&d.previousWorks.length<=12);
      result.domainState.previousWorks=d.previousWorks.map(s=>orderedSubtractStory(s,false));
      if(shot.firstAttempt!==null){
        requireValue(exactKeys(shot.firstAttempt,'story helped')&&typeof shot.firstAttempt.helped==='boolean');
        result.firstAttempt={...shot.firstAttempt,story:orderedSubtractStory(shot.firstAttempt.story,false)};
      }
    } else if(d.story!==null || d.saved!==null){
      requireValue(d.story!==null&&d.saved!==null&&stable(d.story)===stable(d.saved));
      result.domainState.story=orderedSubtractStory(d.story,false);
      result.domainState.saved=orderedSubtractStory(d.saved,false);
    }
    return result;
  };
  const zeroEventShape=value=>Number.isInteger(value.total)&&value.total>=0&&value.total<=5
    &&['add','subtract'].includes(value.operator)&&ids(value.changed,10)&&ids(value.remaining,10)
    &&(value.operator==='subtract'?partition(value.changed,value.remaining,value.total):
      value.changed.every(id=>id>value.total)&&stable([...value.remaining].sort((a,b)=>a-b))===stable([...Array.from({length:value.total},(_,i)=>i+1),...value.changed].sort((a,b)=>a-b)))
    &&equationShape(value.equation);
  const zeroStory=value=>exactKeys(value,'type total operator changed remaining equation')
    &&['empty','all-left','no-arrivals','no-departures'].includes(value.type)&&zeroEventShape(value);
  const subtractionFields = {2:'removed remaining answer',4:'total removed remaining symbol strokes mode',6:'removed remaining equation evidence',
    7:'removed remaining method counted countdown answer',8:'groupA groupB removed remaining answer',
    9:'removedA remainingA removedB remainingB prediction',10:'removed remaining answer',11:'story saved',
    12:'story saved links sourceWorkSha256 storyVersion recordVersion'};
  function subtractionInitial(page) {
    if(page===2)return {removed:[],remaining:[1,2,3,4],answer:null};
    if(page===4)return {total:4,removed:[],remaining:[1,2,3,4],symbol:null,strokes:[],mode:'trace'};
    if(page===6)return {removed:[1,2],remaining:[3,4,5],equation:{whole:3,change:2,result:3},evidence:null};
    if(page===7)return {removed:[4],remaining:[1,2,3],method:'count-remaining',counted:[],countdown:[],answer:null};
    if(page===8)return {groupA:[1,2,3],groupB:[4,5],removed:[],remaining:[1,2,3,4,5],answer:null};
    if(page===9)return {removedA:[],remainingA:[1,2,3,4,5],removedB:[],remainingB:[1,2,3,4,5],prediction:null};
    if(page===10)return {removed:[],remaining:[1,2,3],answer:null};
    return {story:{total:3,removed:[],remaining:[1,2,3],equation:{whole:3,change:0,result:3}},saved:null};
  }
  function subtractCanonical(shot,page) {
    requireValue(shot?.version===1 && shot.sceneId==='scene-p'+page && shot.domainState);
    const expectedIds=page===9?['A1','A2','A3','A4','A5','B1','B2','B3','B4','B5']
      :Array.from({length:[2,4,7].includes(page)?4:page===10?3:5},(_,i)=>i+1);
    requireValue(stable(shot.stableObjectIds)===stable(expectedIds));
    const d=shot.domainState,w=Object.fromEntries(subtractionFields[page].split(' ').map(key=>[key,d[key]]));
    if(page===2){requireValue(partition(w.removed,w.remaining,4)&&nullableNumber(w.answer,4));
    }else if(page===4){requireValue(w.total===4&&partition(w.removed,w.remaining,4)&&[null,'subtract','add'].includes(w.symbol)
      &&['trace','point'].includes(w.mode)&&Array.isArray(w.strokes)&&w.strokes.length<=12
      &&w.strokes.every(stroke=>Array.isArray(stroke)&&stroke.length>=2&&stroke.length<=600
        &&stroke.every(point=>Array.isArray(point)&&point.length===2&&point.every(n=>Number.isFinite(n)&&n>=0&&n<=1))));
    }else if(page===6){requireValue(partition(w.removed,w.remaining,5)&&equationShape(w.equation)&&[null,'before','removed','remaining'].includes(w.evidence));
    }else if(page===7){
      requireValue(partition(w.removed,w.remaining,4)&&['count-remaining','count-back'].includes(w.method)
        &&ids(w.counted,4)&&Array.isArray(w.countdown)&&w.countdown.length<=6
        &&w.countdown.every(n=>Number.isInteger(n)&&n>=0&&n<=5)&&nullableNumber(w.answer));
    }else if(page===8){
      requireValue(partition(w.groupA,w.groupB,5)&&partition(w.removed,w.remaining,5)&&nullableNumber(w.answer));
    }else if(page===9){
      requireValue(partition(w.removedA,w.remainingA,5)&&partition(w.removedB,w.remainingB,5)
        &&[null,'A','B','same'].includes(w.prediction)&&shot.prediction===w.prediction);
    }else if(page===10){requireValue(partition(w.removed,w.remaining,3)&&nullableNumber(w.answer));
    }else{
      requireValue(subtractStory(w.story)&&(w.saved===null||subtractStory(w.saved)));
      if(page===12)requireValue(linksShape(w.links)&&/^[a-f0-9]{64}$/.test(w.sourceWorkSha256)
        &&Number.isInteger(w.storyVersion)&&w.storyVersion>=1&&w.storyVersion<=128
        &&Number.isInteger(w.recordVersion)&&w.recordVersion>=1&&w.recordVersion<=128);
    }
    return JSON.parse(JSON.stringify(w));
  }
  function subtractionCanonicalAction(event,target,page){
    if(page===4&&event.type==='pointerdown'&&target.id==='pad')return {name:'gesture',control:target};
    if(event.type!=='click')return null;
    const control=target.closest('#replay,#hint,#moveHelp,#reset,#check,#countMethod,#backMethod,#depart,#groupA,#groupB,#predictA,#predictB,#predictsame,#answer1,#answer2,#answer3,#answer4,#pointMinus,#clear,#evidence-before,#evidence-removed,#evidence-remaining,#field-whole,#field-change,#field-result,#value1,#value2,#value3,#value4,#value5,#minus,#plus,#save,#num-whole,#num-change,#num-result,#zone-before,#zone-removed,#zone-remaining')
      ||target.closest('[data-object-id]')?.closest('button')||target.closest('[data-object-id]');
    if(!control)return null;
    let name=({replay:'replay',hint:'hint',moveHelp:'hint',reset:'retry',clear:'undo',check:'subtract-check',save:'save'})[control.id]||'work';
    if(page===9&&['predictA','predictB','predictsame'].includes(control.id))name='predict';
    if(page===7&&(control.id==='depart'||control.closest('[data-object-id]')))name='count-process';
    return {name,control};
  }
  for(const page of [2,4,6,7,8,9,10,11,12])subtractionProfiles[page]={
    project:shot=>subtractCanonical(shot,page),source:page===12,
    fresh:(shot,work)=>shot.firstAttempt===null&&shot.currentWorkVersion===0
      &&Array.isArray(shot.revisionHistory)&&shot.revisionHistory.length===0&&stable(work)===stable(subtractionInitial(page)),
    action:(event,target)=>subtractionCanonicalAction(event,target,page),
  };
  function zeroInitial(page) {
    if (page === 1) return {removed: [], remaining: [1,2], answer: null};
    if (page === 2) return {context: 'harbour', objects: [], position: 0, meaning: null};
    if (page === 3) return {order: [1,2,3,4,5,0], quantities: [[],[1],[1,2],[1,2,3],[1,2,3,4],[1,2,3,4,5]]};
    if (page === 4) return {mode: 'trace', strokes: []};
    return {removed: [], remaining: [1,2,3,4], equation: {whole:null,change:null,result:null}, links: {whole:null,change:null,result:null}};
  }
  function zeroWork(shot, page) {
    requireValue(shot?.version === 1 && shot.page === page
      && ['ready','playing','feedback','linking','link-feedback','complete'].includes(shot.phase)
      && exactKeys(shot.work, zeroFields[page]));
    const w = shot.work;
    if (page === 1 || page === 5) {
      const count = page === 1 ? 2 : 4;
      requireValue(ids(w.removed, count) && ids(w.remaining, count)
        && w.removed.length + w.remaining.length === count
        && new Set([...w.removed, ...w.remaining]).size === count);
      if (page === 1) requireValue(nullableNumber(w.answer, 2));
      else requireValue(exactKeys(w.equation, 'whole change result') && exactKeys(w.links, 'whole change result')
        && Object.values(w.equation).every(value => nullableNumber(value, 4))
        && Object.values(w.links).every(value => value === null || ['before','removed','remaining'].includes(value)));
    } else if (page === 2) {
      requireValue(['harbour','ruler'].includes(w.context) && Number.isInteger(w.position) && w.position >= 0 && w.position <= 1
        && stable(w.objects) === stable(w.context === 'harbour' ? [] : [1]) && [null,'empty','origin'].includes(w.meaning));
    } else if (page === 3) {
      requireValue(Array.isArray(w.order) && w.order.length === 6 && new Set(w.order).size === 6
        && w.order.every(value => Number.isInteger(value) && value >= 0 && value <= 5)
        && stable(w.quantities) === stable(zeroInitial(3).quantities));
    } else {
      requireValue(['trace','free'].includes(w.mode) && Array.isArray(w.strokes) && w.strokes.length <= 12
        && w.strokes.reduce((sum, stroke) => sum + (Array.isArray(stroke) ? stroke.length : 1201), 0) <= 1200
        && w.strokes.every(stroke => Array.isArray(stroke) && stroke.length >= 2 && stroke.length <= 600
          && stroke.every(point => Array.isArray(point) && point.length === 2
            && point.every(value => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1))));
    }
    return JSON.parse(JSON.stringify(w));
  }
  function zeroAction(event, target, page) {
    const picture = target.closest('[data-boat],[data-zone],[data-context],[data-meaning],[data-insert],[data-role],[data-zero=true]');
    if (event.type === 'pointerdown') {
      const source = target.closest('[data-boat]') || (page === 3 && target.closest('[data-zero=true]'))
        || (page === 4 && target.id === 'inkSurface' && target);
      return source ? {name: 'gesture', control: source} : null;
    }
    // The authored SVG keyboard path calls click() itself. Attribute that
    // mutation to this genuine keydown; the resulting synthetic click is ignored.
    if(event.type==='keydown'&&page===4&&target.id==='inkSurface'&&event.key===' ')
      return {name:'keyboard-gesture',control:target};
    if (event.type === 'keydown') return picture && target.matches('[role=button]') && ['Enter',' '].includes(event.key)
      ? {name: 'work', control: target} : null;
    if (event.type !== 'click') return null;
    const control = target.closest('#replayBtn,#hintBtn,#undoBtn,#checkBtn,#nextStepBtn,#nextContextBtn,#number-0,#number-1,#number-2,#number-3,#number-4');
    if (control) return {name: ({replayBtn:'replay',hintBtn:'hint',undoBtn:'undo',checkBtn:'zero-check'})[control.id] || 'work', control};
    return picture ? {name: 'work', control: picture} : null;
  }
  const zeroProfiles = Object.fromEntries([1,2,3,4,5].map(page => [page, {
    project: shot => zeroWork(shot, page),
    fresh: (shot, work) => stable(work) === stable(zeroInitial(page)) && shot.workVersion === 1
      && Array.isArray(shot.history) && shot.history.length === 0
      && Array.isArray(shot.attempts) && shot.attempts.length === 0
      && exactKeys(shot.firstAttempts, ''),
    action: (event, target) => zeroAction(event, target, page),
  }]));
  function zeroLaterInitial(page){
    if(page===6)return {total:3,removed:[],remaining:[1,2,3],prediction:null};
    if(page===7)return {incoming:[],remaining:[1,2,3],gateOpen:false,prediction:null};
    if(page===8)return {removed:[],remaining:[1,2],executed:false,equation:{whole:2,change:0,result:null}};
    if(page===9)return {context:'incoming',total:2,changed:[],remaining:[1,2],executed:false,operator:'add',equation:{whole:2,change:0,result:null}};
    return {operator:'add',changed:[],remaining:[],executed:false,equation:{whole:0,change:0,result:null}};
  }
  function zeroLaterWork(shot,page){
    const w=shot?.domainState?.work;
    requireValue(shot?.version===1&&exactKeys(w,zeroFields[page]));
    const total=page===6?w.total:page===7?3:page===8?2:page===9?w.total:0;
    requireValue(Number.isInteger(total)&&total>=0&&total<=5
      &&stable(shot.stableObjectIds)===stable(Array.from({length:total},(_,i)=>i+1)));
    if(page===6){requireValue(total>=1&&partition(w.removed,w.remaining,total)&&nullableNumber(w.prediction)
      &&shot.prediction===w.prediction);
    }else if(page===7){requireValue(ids(w.incoming,10)&&ids(w.remaining,10)
      &&typeof w.gateOpen==='boolean'&&nullableNumber(w.prediction)&&shot.prediction===w.prediction);
    }else if(page===8){requireValue(partition(w.removed,w.remaining,2)&&typeof w.executed==='boolean'&&equationShape(w.equation));
    }else{requireValue((page!==9||['incoming','departing'].includes(w.context))&&['add','subtract'].includes(w.operator)
      &&ids(w.changed,10)&&ids(w.remaining,10)&&typeof w.executed==='boolean'&&equationShape(w.equation));}
    return JSON.parse(JSON.stringify(w));
  }
  function zeroLaterAction(event,target,page){
    // P7's SVG gate explicitly handles a real keydown; native buttons rely on
    // their one native click, avoiding duplicate keyboard evidence.
    if(event.type==='keydown')return page===7&&target.id==='gate-click-zone'&&['Enter',' '].includes(event.key)
      ?{name:'work',control:target}:null;
    if(event.type!=='click')return null;
    const control=target.closest('#confirmBtn,#continue-btn,#checkRecordBtn,#replayBtn,#hintBtn,#resetBtn,#replay-btn,#reset-btn,#replayVoiceBtn,#resetShipsBtn,#replayCurrentCueBtn,#showHintBtn,#resetActivityBtn,#replayAudioBtn,#gate-click-zone,#executeRequestBtn,#arrivalGateBtn,#departureGateBtn,.prediction-chip,.number-chip,[data-predict],.boat-container,.result-choice,.execute-context,.symbol-token');
    if(!control)return null;
    const name=({confirmBtn:'zero-later-check','continue-btn':'zero-later-check',checkRecordBtn:'zero-later-check',
      replayBtn:'replay','replay-btn':'replay',replayVoiceBtn:'replay',replayCurrentCueBtn:'replay',replayAudioBtn:'replay',
      hintBtn:'hint',showHintBtn:'hint',resetBtn:'retry','reset-btn':'retry',resetShipsBtn:'retry',resetActivityBtn:'retry'})[control.id]
      ||(control.matches('.prediction-chip,[data-predict]')?'predict':'work');
    return {name,control};
  }
  for(const page of [6,7,8,9,10])zeroProfiles[page]={
    project:shot=>zeroLaterWork(shot,page),
    fresh:(shot,work)=>stable(work)===stable(zeroLaterInitial(page))&&shot.firstAttempt===null
      &&shot.currentWorkVersion===1&&Array.isArray(shot.revisionHistory)&&shot.revisionHistory.length===0,
    action:(event,target)=>zeroLaterAction(event,target,page),
  };
  function zeroTailInitial(page){
    if(page===11)return {total:2,operator:'add',changed:[],remaining:[1,2],executed:false,equation:{whole:null,change:null,result:null}};
    if(page===12)return {context:'tools',objects:[],position:0,meaning:null};
    return {story:{type:'all-left',total:3,operator:'subtract',changed:[],remaining:[1,2,3],equation:{whole:null,change:null,result:null}},saved:null};
  }
  function zeroTailWork(shot,page){
    const w=shot?.work;
    requireValue(shot?.version===1&&shot.page===page&&exactKeys(w,zeroFields[page]));
    if(page===11)requireValue(zeroEventShape(w)&&typeof w.executed==='boolean');
    else if(page===12)requireValue(['tools','path'].includes(w.context)&&stable(w.objects)===stable(w.context==='tools'?[]:[1])
      &&Number.isInteger(w.position)&&w.position>=0&&w.position<=1&&[null,'empty','origin'].includes(w.meaning));
    else{
      requireValue(zeroStory(w.story)&&(w.saved===null||zeroStory(w.saved)));
      if(page===14)requireValue([null,'whole','change','result','origin'].includes(w.zeroRole)&&/^[a-f0-9]{64}$/.test(w.sourceWorkSha256)
        &&Number.isInteger(w.storyVersion)&&w.storyVersion>=1&&w.storyVersion<=128
        &&Number.isInteger(w.recordVersion)&&w.recordVersion>=1&&w.recordVersion<=128);
    }
    return JSON.parse(JSON.stringify(w));
  }
  function zeroTailAction(event,target,page){
    const picture=target.closest('[data-boat],[data-story],[data-context],[data-meaning],[data-role]');
    if(event.type==='pointerdown')return [11,13].includes(page)&&target.closest('[data-boat]')?{name:'gesture',control:target.closest('[data-boat]')}:null;
    if(event.type==='keydown')return picture&&target.matches('[role=button]')&&['Enter',' '].includes(event.key)?{name:'work',control:target}:null;
    if(event.type!=='click')return null;
    const control=target.closest('#replayBtn,#hintBtn,#undoBtn,#checkBtn,#increaseN,#decreaseN,#opPlusZero,#opMinusZero,#runTrialBtn,#nextContextBtn,#editSourceBtn')||picture;
    return control?{name:({replayBtn:'replay',hintBtn:'hint',editSourceBtn:'hint',undoBtn:'undo',checkBtn:'submit',runTrialBtn:'submit'})[control.id]||'work',control}:null;
  }
  for(const page of [11,12,13,14])zeroProfiles[page]={
    project:shot=>zeroTailWork(shot,page),source:page===14,
    fresh:(shot,work)=>stable(work)===stable(zeroTailInitial(page))&&shot.workVersion===1
      &&Array.isArray(shot.history)&&shot.history.length===0&&Array.isArray(shot.attempts)&&shot.attempts.length===0&&exactKeys(shot.firstAttempts,''),
    action:(event,target)=>zeroTailAction(event,target,page),
  };
  // The private host supplies this hash, which must match the exact frozen
  // HTML whose opening handler/cue was reviewed. Other revisions keep normal
  // operation and recovery behavior, but never acquire this automatic intro.
  const openingHashes = {
    'math-subtract': [null,
      'c3658ace3692b348da052e2e12b1bbb014826eb2270073a186ece85f826e04a1',
      'dcb3eff73babf75f1c8f0f26d85a7bbaa7744a4da198d474a0d636b3107b6442',
      '6aadf65236367ecda91882b440d6de53c19d50b16a71c923e208785ee12c3200',
      'ea61b80906395abeb8a23c42bd76aa42e6940405035351aa3db1558772266ecd',
      '7b8d681c51aacec70d96a042c544dfb08cfc74a799897148b7456055016d4780',
      'b9d5e30d69d7f6383ffcbb4a65361e20acda77e3139119e9a753f55b1d61fbc2',
      '3eab53909193227a064ca84b167539a94aa80931518071539e519c4ec483aeac',
      '30cf944486eeefd63c5e3e3318200580351cf99f2b8baf21f4c3057c5d0807d4',
      '884519d00c8074f9b3c53bacbfb5b3897477464c43ac33c0425e3ccaeed457a7',
      '148ffdb6c2cae7369a369afc9edcf200a8e03aef7981f849907ef6609d197f9d',
      'e3fa57882036c537fe11a8b2592dd77e78a183384cc944e7f30c29861e5736a6',
      '66b8dc605e3d29878e3c6a4ddc8ac098f53217099363b06c8cdc3f857173ef4e'],
    'math-zero': [null,
      'ad0d1b151727b614e9d9474fabe3182e5e201f763f14f2ad64ed4956b389e111',
      'b68e23aac59dc38fa931cb3ddfb4d6fea7abfa788b8e70497325a11817f1c42f',
      'b9980821ed4bd71df6e03e23d0c2593d5c0edb4b910a5230e73d73a16be772c5',
      '09d2bc3f7772fc9574a2edbba5c976c1dff3e6300bdea2733fd42e9524e06d81',
      '753c6e89f9b657a8600b64eac60c059d09b5d2325849b10b60c57ae283a09733',
      'cf178dcd63a9f7125c4da8eb8279925c60a239663b3ee451e4161d28df8b60f9',
      '3a260295a1ff44f7d1310905a621667072fc004d333a752a6e680532989bfc68',
      '76641e70c480dfd385329117601f2b3f072cee73b7339196c1c4780f7b015f9b',
      'f600c87188dd2de800016c78310972eb3f955066ba0335d84b0ee1d0c2d7a284',
      '2b5633cb500b35498de2bf81c511735843e6883d3297c902342f147dfb696d64',
      '52ffe3ad14431425758a4377d8285625bfdbd1a87533256d7a06eae9d25c7327',
      '716aac6f446ac1048e6dd04d39286c6b7297469ed1453ceef1468a47235a247d',
      '0684203491a872f26b4eebcecaac7df5f1f2144b42a782d301ac8082b623fb95',
      'fed847b2c0c73d7c9eaf8d0fef7044c32eb5ce68c75f35ac9c9cd65c5e06080d'],
  };
  // Never fall back to replay: on some pages it records help. Subtraction p1
  // has a private two-cue queue and no callable opening handler, so it stays
  // unsupported until a separately reviewed entry point exists.
  function openingControl(kind, page, contentSha256) {
    if (openingHashes[kind]?.[page] !== contentSha256) return null;
    if (kind === 'math-subtract' && page >= 2 && page <= 12) return {id:'start'};
    if (kind === 'math-zero' && ([1,2,3,4,5,11,12,13].includes(page))) return {id:'startBtn'};
    if (kind === 'math-zero' && page >= 6 && page <= 10) return {cue:'p'+page+'-a1'};
    if (kind === 'math-zero' && page === 14) return {sourceCue:true};
    return null;
  }
  function svgKeyboardClick() {
    // The authored delegated click handler needs only a bubbling event and
    // its target. Browser-created events remain untrusted; only the original
    // genuine keydown is attributed to the child by the operation adapter.
    try {
      if (typeof MouseEvent==='function') {
        const event=new MouseEvent('click',{bubbles:true,cancelable:true,view:window});
        if (event.isTrusted!==true) return event;
      }
    } catch (_) { /* Older browsers expose only createEvent. */ }
    if(typeof document.createEvent!=='function')return null;
    try {
      const event=document.createEvent('MouseEvents');
      event.initMouseEvent('click',true,true,window,1,0,0,0,0,false,false,false,false,0,null);
      if(event.isTrusted!==true)return event;
    } catch (_) { /* Use a basic bubbling Event on older engines. */ }
    try {
      const event=document.createEvent('Event');event.initEvent('click',true,true);
      if(event.isTrusted!==true)return event;
    } catch (_) { /* Leave the original scene available to pointer input. */ }
    return null;
  }
  function zeroThreePristine(shot,phase) {
    // Exact p3 starts with no spoken cue. Its reviewed teacher state message
    // may change only phase from ready to playing before the deferred intro;
    // the audio visibility helper may subsequently mark that empty cue hidden.
    if(!shot || (phase==='ready' ? shot.audioStatus!=='idle'
      : phase!=='playing' || !['idle','hidden'].includes(shot.audioStatus)))return false;
    return stable(shot)===stable({version:1,page:3,phase,work:zeroInitial(3),selected:null,activeRole:'whole',answer:null,
      firstAttempts:{},attempts:[],help:{replay:0,hint:0,demonstration:0},history:[],workVersion:1,
      completedContexts:[],tracePassed:false,traceWork:null,currentCue:null,audioStatus:shot.audioStatus,
      pen:[0.5,0.1],penDown:false,teacherDemo:null});
  }
  function zeroFourPristine(shot) {
    return stable(shot)===stable({version:1,page:4,phase:'playing',work:zeroInitial(4),selected:null,activeRole:'whole',answer:null,
      firstAttempts:{},attempts:[],help:{replay:0,hint:0,demonstration:0},history:[],workVersion:1,
      completedContexts:[],tracePassed:false,traceWork:null,currentCue:'zero-p4-repair-trace',audioStatus:'playing',
      pen:[0.5,0.1],penDown:false,teacherDemo:null});
  }
  // Only a complete replay-only history can release the current instruction
  // again on explicit page selection. This does not infer listening, create an
  // operation, or equate an unacknowledged local action with server evidence.
  function zeroReplayOpeningShot(shot,page) {
    if(!shot || ![3,4].includes(page))return false;
    const n=shot.help?.replay,history=shot.history,work=zeroInitial(page);
    if(!Number.isInteger(n)||n<1||n>512||!Array.isArray(history)||history.length!==Math.min(n,160)
        ||!['requested','playing','ready','error','missing','cancelled','hidden'].includes(shot.audioStatus))return false;
    const expectedHistory=Array.from({length:history.length},(_,i)=>{
      const version=n-history.length+i+1;
      return {name:'replay',version,before:work,after:work,help:{replay:version,hint:0,demonstration:0}};
    });
    return stable(shot)===stable({version:1,page,phase:'playing',work,selected:null,activeRole:'whole',answer:null,
      firstAttempts:{},attempts:[],help:{replay:n,hint:0,demonstration:0},history:expectedHistory,workVersion:n+1,
      completedContexts:[],tracePassed:false,traceWork:null,currentCue:page===3?'zero-p3-repair-start':'zero-p4-repair-trace',
      audioStatus:shot.audioStatus,pen:[0.5,0.1],penDown:false,teacherDemo:null});
  }
  function zeroReplayOpening(shot,server,page) {
    if(!zeroReplayOpeningShot(shot,page))return false;
    const n=shot.help.replay,work=zeroInitial(page);
    return stable(server)===stable({kind:'math-zero',validator:'math-zero-p'+page+'.v1',phase:'playing',completed:false,
      lastWork:work,workVersion:1,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],
      support:{hint:0,replay:n,demonstration:0},undoCount:0,retryCount:0,exposureCount:0,
      history:Array.from({length:n},(_,i)=>({name:'replay',task:page===3?'task':'trace',workVersion:1,work,
        support:{hint:0,replay:i+1,demonstration:0}})),
      evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'});
  }
  function zeroInitialServer(server,page) {
    return stable(server)===stable({kind:'math-zero',validator:'math-zero-p'+page+'.v1',phase:'playing',completed:false,
      lastWork:null,workVersion:0,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},
      passedTasks:[],support:{hint:0,replay:0,demonstration:0},undoCount:0,retryCount:0,exposureCount:0,history:[],
      evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'});
  }
  // The exact frozen p6 records an unchanged quantity click in local history
  // even though no mathematical work reaches the server. Restore only that
  // recognizable initial-world history; never manufacture an operation.
  function zeroSixNoopRecovery(shot,server,contentSha256) {
    if(contentSha256!==openingHashes['math-zero'][6]||!zeroInitialServer(server,6)||!shot)return false;
    const work=zeroLaterInitial(6), history=shot.revisionHistory;
    if(!Array.isArray(history)||history.length<1||history.length>239
        ||!history.every(item=>exactKeys(item,'name work')&&item.name==='change-quantity'
          &&stable(item.work)===stable(work)))return false;
    const version=shot.currentWorkVersion;
    if(!Number.isInteger(version)||version<1||version>history.length+1
        ||shot.phase!==(version===1?'ready':'playing'))return false;
    const expected={version:1,phase:shot.phase,domainState:{work,n:3,boats:[1,2,3].map(id=>({id:String(id),departed:false}))},
      prediction:null,stableObjectIds:[1,2,3],firstAttempt:null,firstPrediction:null,helpFlags:{hint:0,replay:0},
      revisionHistory:history,currentWorkVersion:version,uiState:{passed:[],trials:{},
        message:'换一个数量，再猜一次。以前的尝试仍保留。',cue:'p6-a1',extra:null}};
    return stable(shot)===stable(expected);
  }
  // For an initial mathematical world, neither an old local replay nor an
  // independent server replay identifies a tab. Validate both histories but
  // never equate them: require a new, genuinely initiated replay and its ACK.
  function zeroOneRecovery(shot,server,contentSha256) {
    if(contentSha256!==openingHashes['math-zero'][1])return null;
    const work={removed:[],remaining:[1,2],answer:null};
    if(!shot || stable(shot.work)!==stable(work)
        || !(server?.lastWork===null || stable(server?.lastWork)===stable(work)))return null;
    const count=shot.help?.replay, history=shot.history;
    const validCount=Number.isInteger(count)&&count>=0&&count<=9999&&Array.isArray(history)
      && history.length===Math.min(count,160);
    const expectedHistory=validCount?Array.from({length:history.length},(_,i)=>{
      const version=count-history.length+i+1,help={replay:version,hint:0,demonstration:0};
      return {name:'replay',version,before:work,after:work,help};
    }):null;
    const expectedShot=validCount?{version:1,page:1,phase:shot.phase,work,selected:null,activeRole:'whole',answer:null,
      firstAttempts:{},attempts:[],help:{replay:count,hint:0,demonstration:0},history:expectedHistory,
      workVersion:count+1,completedContexts:[],tracePassed:false,traceWork:null,currentCue:shot.currentCue,
      audioStatus:shot.audioStatus,pen:[0.5,0.1],penDown:false,teacherDemo:null}:null;
    const validShot=validCount&&stable(shot)===stable(expectedShot)
      // The authored narration helper emits hidden with a null cue when the
      // classroom start overlay conceals this untouched page. The page's
      // listener records that visibility state even before any cue is played.
      && (shot.phase==='ready'&&count===0&&shot.currentCue===null&&['idle','hidden'].includes(shot.audioStatus)
        || shot.phase==='playing'&&shot.currentCue==='zero-p1-repair-start'
          && ['idle','requested','playing','ready','error','missing','cancelled','hidden'].includes(shot.audioStatus));
    const initial={kind:'math-zero',validator:'math-zero-p1.v1',phase:'playing',completed:false,lastWork:null,
      workVersion:0,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],
      support:{hint:0,replay:0,demonstration:0},undoCount:0,retryCount:0,exposureCount:0,history:[],
      evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'};
    const serverCount=Array.isArray(server?.history)?server.history.length:-1;
    if(serverCount<0||serverCount>512)return {mode:'mismatch',original:shot};
    const support={hint:0,replay:serverCount,demonstration:0};
    const expectedServer={...initial,lastWork:serverCount?work:null,workVersion:serverCount?1:0,support,
      history:Array.from({length:serverCount},(_,i)=>({name:'replay',task:'task',workVersion:1,work,
        support:{hint:0,replay:i+1,demonstration:0}}))};
    if(!validShot || stable(server)!==stable(expectedServer))return {mode:'mismatch',original:shot};
    if(count===0&&serverCount===0)return null;
    if(shot.phase!=='playing')return {mode:'mismatch',original:shot};
    return {mode:'support',original:JSON.parse(JSON.stringify(shot))};
  }
  function zeroOneReplayed(original,audioStatus) {
    const next=JSON.parse(JSON.stringify(original));
    next.help.replay++;
    next.history.push({name:'replay',version:next.workVersion,before:next.work,after:next.work,
      help:JSON.parse(JSON.stringify(next.help))});
    if(next.history.length>160)next.history.shift();
    next.workVersion++;
    next.audioStatus=audioStatus;
    return next;
  }
  // This exact p2 records each supported action in a deterministic way. A
  // checkpoint may lag one acknowledged answer when its write loses a race
  // with the operation ACK. Reconstruct the entire confirmed history first;
  // a projected work match alone is ambiguous when an old answer recurs.
  function subtractTwoAcknowledgedRepair(shot, server, contentSha256) {
    if (contentSha256 !== openingHashes['math-subtract'][2]) return null;
    if (server?.kind!=='math-subtract' || server.validator!=='math-subtract-p2.v1'
        || !Array.isArray(server.history) || server.history.length<2 || server.history.length>512) return null;
    const copy=value=>JSON.parse(JSON.stringify(value)), same=(a,b)=>stable(a)===stable(b);
    const range=[1,2,3,4], initial=()=>({removed:[],remaining:[...range],answer:null});
    const projection=d=>({removed:copy(d.removed),remaining:copy(d.remaining),answer:d.answer});
    function validWork(work) {
      if(!exactKeys(work,'removed remaining answer') || !Array.isArray(work.removed) || work.removed.length>1
          || work.removed.some(id=>!Number.isInteger(id)||id<1||id>4)
          || !same(work.remaining,range.filter(id=>!work.removed.includes(id)))) return false;
      return work.answer===null || Number.isInteger(work.answer)&&work.answer>=1&&work.answer<=4;
    }
    const world={version:1,sceneId:'scene-p2',phase:'playing',prediction:null,instructionsComplete:true,
      stableObjectIds:[...range],domainState:{...initial(),checked:false},firstAttempt:null,helpFlags:{hint:false},
      revisionHistory:[],currentWorkVersion:0};
    let lastWork=null, workVersion=0, undoCount=0, retryCount=0, passed=false;
    const support={hint:0,replay:0,demonstration:0}, attempts=[];
    const record=(action,details)=>{
      world.currentWorkVersion++;
      world.revisionHistory.push({version:world.currentWorkVersion,action,details:copy(details)});
      world.revisionHistory=world.revisionHistory.slice(-60);
    };
    for(let i=0;i<server.history.length;i++) {
      const event=server.history[i], before=projection(world.domainState), last=i===server.history.length-1;
      if(!exactKeys(event,'name task workVersion work support') || event.task!=='task' || !validWork(event.work)) return null;
      if(last) {
        // Compare the entire reconstructed authored checkpoint, not just its
        // projection, before applying the one acknowledged answer change.
        if(!same(shot,world) || event.name!=='work' || !same(before.removed,event.work.removed)
            || !same(before.remaining,event.work.remaining) || event.work.answer===null
            || event.work.answer===before.answer) return null;
      }
      const changedServer=lastWork===null || !same(lastWork,event.work);
      if(changedServer){workVersion++;passed=false;}
      if(event.workVersion!==workVersion) return null;
      if(event.name==='replay' || event.name==='hint') {
        if(!same(before,event.work)) return null;
        support[event.name]++;
        if(event.name==='hint'){world.helpFlags.hint=true;record('hint',{});}
      } else if(event.name==='submit') {
        if(!same(before,event.work) || before.removed.length!==1 || before.answer===null) return null;
        if(world.firstAttempt===null)world.firstAttempt={...copy(before),helped:world.helpFlags.hint};
        record('check',world.domainState);world.domainState.checked=true;
        const correct=before.answer===before.remaining.length;
        attempts.push({task:'task',work:copy(before),correct,workVersion,support:copy(support),retryCount,undoCount,
          priorAttempts:attempts.length,priorPageAttempts:attempts.length,priorReveals:0,
          pictureSupport:true,assistanceOutsideApp:'unobserved'});
        if(correct)passed=true;
      } else if(event.name==='retry') {
        if(!same(event.work,initial())) return null;
        record('reset',world.domainState);world.domainState={...initial(),checked:false};retryCount++;
      } else if(event.name==='work' || event.name==='undo') {
        const d=world.domainState;
        if(event.name==='work' && same(before.removed,event.work.removed) && same(before.remaining,event.work.remaining)
            && event.work.answer!==null && event.work.answer!==before.answer) {
          d.answer=event.work.answer;d.checked=false;record('answer',{answer:d.answer});
        } else if(event.name==='work' && before.removed.length===0 && event.work.removed.length===1
            && event.work.answer===before.answer) {
          d.removed=copy(event.work.removed);d.remaining=copy(event.work.remaining);
          record('move',{id:d.removed[0]});d.checked=false;
        } else if(event.name==='undo' && before.removed.length===1 && event.work.removed.length===0
            && event.work.answer===before.answer) {
          const id=before.removed[0];d.removed=[];d.remaining=[...range];record('return',{id});d.checked=false;undoCount++;
        } else return null;
      } else return null;
      if(!same(event.support,support) || !same(projection(world.domainState),event.work)) return null;
      world.phase=world.domainState.checked && world.domainState.removed.length===1
        && world.domainState.answer===world.domainState.remaining.length ? 'complete' : 'playing';
      lastWork=copy(event.work);
    }
    if(!same(server.lastWork,lastWork) || server.workVersion!==workVersion || !same(server.support,support)
        || !same(server.attempts,attempts) || !same(server.firstAttempts,attempts.length?{task:attempts[0]}:{})
        || !same(server.firstPredictions,{}) || !same(server.latestPredictions,{}) || server.exposureCount!==0
        || server.undoCount!==undoCount || server.retryCount!==retryCount
        || !same(server.passedTasks,passed?['task']:[]) || server.completed!==passed
        || server.phase!==(passed?'complete':'playing')) return null;
    return world;
  }
  window.installMathSubtractZeroCourseAdapter = function (sceneId, kind, contentSha256) {
    const match = /^scene-p([1-9]|1[0-4])$/.exec(sceneId);
    const page = match ? Number(match[1]) : 0;
    const profile = kind === 'math-subtract' ? subtractionProfiles[page] : kind === 'math-zero' ? zeroProfiles[page] : null;
    if (!profile) throw new Error('math_scene_projection_not_reviewed');
    const api = window.miraCourseOperation, incomingCheckpoint = window.miraActivityCheckpoint;
    let handoff=checkpointHandoffs.get(incomingCheckpoint);
    const checkpoint=handoff?.checkpoint || incomingCheckpoint;
    if (!api || !checkpoint || typeof checkpoint.capture !== 'function')
      throw new Error('math_checkpoint_unavailable');
    const capture = () => checkpoint.capture.call(checkpoint);
    let aligned = false, disposed = false, pending = false, timer = null, gesture = null, previous = null, epoch = 0;
    let parentReplays = [], sourceUnavailable = false;
    let freshOperation = false, introDisarmed = false, introStarted = false, zeroOpeningServerPristine = false;
    let replayOpeningEvidence = null, subtractionOpeningEvidence = null, subtractionSourceEvidence = null;
    let zeroCompletedEvidence = null, zeroCompletedSource = null;
    let recoveryOnlySupport=false, recoveryOriginal=null, recoveryNotice=null, recoveryGuide=null, recoveryTarget=null, recoveryTargetStyle=null;
    let recoveryRollbackFailed=false;
    const svgKeyboardEnabled=kind==='math-zero' && [1,2,3,4,5,11,12,13,14].includes(page)
      && contentSha256===openingHashes['math-zero'][page];
    const heldSvgKeys=new Set();
    const subtractOneKeyboardEnabled=kind==='math-subtract'&&page===1
      &&contentSha256===openingHashes['math-subtract'][1];
    // Keep the truck zone's original semantics and its crate descendants.
    // A separate native button follows the scene in normal layout, so it does
    // not cover a touch target. Only this exact reviewed page gets the control.
    let truckZone=null, truckKeyboardTarget=null, authorizedTruckClick=null;
    if(subtractOneKeyboardEnabled){
      const zone=document.getElementById('truckZone'), scene=document.getElementById('sceneArea');
      if(zone instanceof Element&&zone.tagName==='DIV'&&zone.getAttribute('aria-label')==='货车区'
          &&zone.getAttribute('role')===null&&zone.getAttribute('tabindex')===null
          &&scene instanceof Element&&zone.parentNode===scene&&scene.parentNode
          &&typeof scene.parentNode.insertBefore==='function'){
        const button=document.createElement('button');
        button.setAttribute('type','button');button.textContent='把选中的箱子装上车';
        button.style.cssText='display:block;margin:8px auto;min-height:44px;padding:8px 18px;font-size:18px;cursor:pointer';
        scene.parentNode.insertBefore(button,scene.nextSibling);truckZone=zone;truckKeyboardTarget=button;
      }
    }
    const truckKeyboardEnabled=truckKeyboardTarget!==null;
    const opening = openingControl(kind, page, contentSha256);
    const p9FeedbackEnabled=kind==='math-zero' && page===9 && contentSha256===openingHashes['math-zero'][9];
    let p9PassedTasks=null, p9FeedbackObserver=null, p9FeedbackTarget=null;
    // These are authored outcome cues from the exact reviewed pages. Do not
    // automatically play a hint or the replay control: both can add support.
    const zeroCompletedCues={2:['zero-p2-repair-goodEmpty','zero-p2-repair-goodOrigin','zero-p2-repair-finish'],
      3:['zero-p3-repair-success'],4:['zero-p4-repair-successFree'],
      5:['zero-p5-repair-success'],6:['p6-a4'],7:['p7-a4'],8:['p8-a4'],9:['p9-a4'],10:['p10-a4'],
      11:['p11-a4'],12:['p12-a4'],13:['zero-p13-repair-saved'],14:['p14-a4']};
    function zeroCompletedVerified(shot,server) {
      if(kind!=='math-zero'||page<2||page>14||!opening||!shot||!server
          ||shot.version!==1||shot.phase!=='complete'||(page<=5||page>=11)&&shot.page!==page
          ||server.kind!==kind||server.validator!=='math-zero-p'+page+'.v1'||server.phase!=='complete'||server.completed!==true
          ||server.evidenceBoundary!=='client_reported_picture_supported_practice'||server.oralSkill!=='unobserved'||server.paperHandwriting!=='unobserved'
          ||!Array.isArray(server.passedTasks)||!Array.isArray(server.attempts)||!Array.isArray(server.history))return false;
      const expected=({2:['harbour','ruler'],4:['trace','free'],9:['incoming','departing'],10:['add','subtract'],
        11:['add','subtract','different-n'],12:['tools','path']})[page]||['task'];
      const unique=new Set(server.passedTasks);
      if(unique.size!==server.passedTasks.length||stable([...unique].sort())!==stable([...expected].sort()))return false;
      if(!exactKeys(server.support,'hint replay demonstration')
          ||Object.values(server.support).some(n=>!Number.isInteger(n)||n<0))return false;
      if(page<=5||page>=11){
        if(stable(shot.help)!==stable(server.support))return false;
      } else if(!exactKeys(shot.helpFlags,'hint replay')||server.support.demonstration!==0
          ||shot.helpFlags.hint!==server.support.hint||shot.helpFlags.replay!==server.support.replay)return false;
      const work=profile.project(shot),cue=page>=6&&page<=10?shot.uiState?.cue:shot.currentCue;
      if(stable(work)!==stable(server.lastWork)||!zeroCompletedCues[page]?.includes(cue))return false;
      if(page===2&&((cue==='zero-p2-repair-goodEmpty'&&work.context!=='harbour')
          ||(cue==='zero-p2-repair-goodOrigin'&&work.context!=='ruler')))return false;
      if(page===4&&work.mode!=='free')return false;
      if(page===14&&(!zeroCompletedSource||zeroCompletedSource.available!==true
          ||work.sourceWorkSha256!==zeroCompletedSource.sourceWorkSha256
          ||stable(work.story)!==stable(zeroCompletedSource.saved)||stable(work.saved)!==stable(zeroCompletedSource.saved)))return false;
      return true;
    }
    // These exact completed pages have an authored replay handler that only
    // restarts the private voice queue. Its render recomputes phase, so check
    // that this would leave the current authored state unchanged as well.
    function subtractFinishedVerified(shot,server) {
      if(kind!=='math-subtract'||![2,3,5,7,9,10,11,12].includes(page)||!opening||!shot||!server
          ||!exactKeys(shot,'version sceneId phase prediction instructionsComplete stableObjectIds domainState firstAttempt helpFlags revisionHistory currentWorkVersion')
          ||shot.version!==1||shot.sceneId!==sceneId||shot.phase!=='complete'||shot.instructionsComplete!==true
          ||!exactKeys(shot.helpFlags,'hint')||typeof shot.helpFlags.hint!=='boolean'
          ||!Array.isArray(shot.revisionHistory)||shot.revisionHistory.length>60
          ||!Number.isInteger(shot.currentWorkVersion)||shot.currentWorkVersion<0
          ||!exactKeys(server,'kind validator phase completed lastWork workVersion attempts firstAttempts firstPredictions latestPredictions passedTasks support undoCount retryCount exposureCount history evidenceBoundary oralSkill paperHandwriting')
          ||server.kind!==kind||server.validator!=='math-subtract-p'+page+'.v1'||server.phase!=='complete'||server.completed!==true
          ||server.evidenceBoundary!=='client_reported_picture_supported_practice'||server.oralSkill!=='unobserved'||server.paperHandwriting!=='unobserved')return false;
      const w=profile.project(shot),d=shot.domainState,same=(a,b)=>stable(a)===stable(b);
      if(!same(w,server.lastWork))return false;
      if(page===2)return d.checked===true&&w.removed.length===1&&w.answer===w.remaining.length;
      if(page===3)return ['original','removed','remaining'].every(role=>d.connections[role]===role);
      if(page===5)return d.checked==='equal'&&d.leftItems.length===3;
      if(page===7)return w.method==='count-remaining'?w.counted.length===3&&w.answer===3
        :same(w.countdown,[4,3])&&w.answer===3;
      if(page===9)return d.checked===true&&w.prediction==='A'&&w.removedA.length===1&&w.removedB.length===3;
      if(page===10)return d.checked===true&&w.removed.length===1&&w.answer===2;
      if(page===11){
        if(d.saved===null||JSON.stringify(d.saved)!==JSON.stringify(d.story))return false;
        try {orderedSubtractStory(d.saved,false);}catch(_){return false;}
        return true;
      }
      if(!subtractionSourceEvidence||subtractionSourceEvidence.available!==true
          ||d.sourceWorkSha256!==subtractionSourceEvidence.sourceWorkSha256
          ||!same(d.story,subtractionSourceEvidence.saved)||!same(d.saved,subtractionSourceEvidence.saved))return false;
      return d.story!==null&&d.checked===true&&d.links.whole==='before'&&d.links.change==='removed'
        &&d.links.result==='remaining'&&d.storyVersion===d.recordVersion;
    }
    // The p4/p6/p8 frozen replay handler only resumes its private voice queue;
    // it records neither help nor work. Accept only an authenticated server
    // history which matches this checkpoint and its authored transitions.
    function subtractResumeVerified(shot,server) {
      if([2,3,5,7,9,10,11,12].includes(page))return subtractFinishedVerified(shot,server);
      if(kind!=='math-subtract'||![4,6,8].includes(page)||!opening||!shot||!server
          ||!exactKeys(shot,'version sceneId phase prediction instructionsComplete stableObjectIds domainState firstAttempt helpFlags revisionHistory currentWorkVersion')
          ||shot.version!==1||shot.sceneId!==sceneId||shot.prediction!==null||typeof shot.instructionsComplete!=='boolean'
          ||!exactKeys(shot.helpFlags,'hint')||typeof shot.helpFlags.hint!=='boolean'
          ||!Array.isArray(shot.revisionHistory)||shot.revisionHistory.length>60||!Number.isInteger(shot.currentWorkVersion)||shot.currentWorkVersion<0
          ||!exactKeys(server,'kind validator phase completed lastWork workVersion attempts firstAttempts firstPredictions latestPredictions passedTasks support undoCount retryCount exposureCount history evidenceBoundary oralSkill paperHandwriting')
          ||server.kind!==kind||server.validator!=='math-subtract-p'+page+'.v1'
          ||server.evidenceBoundary!=='client_reported_picture_supported_practice'||server.oralSkill!=='unobserved'||server.paperHandwriting!=='unobserved'
          ||!exactKeys(server.firstPredictions,'')||!exactKeys(server.latestPredictions,'')||server.exposureCount!==0
          ||!Array.isArray(server.history)||server.history.length>512||!Array.isArray(server.attempts)||server.attempts.length>128)return false;
      const work=profile.project(shot),same=(a,b)=>stable(a)===stable(b),support={hint:0,replay:0,demonstration:0};
      let last=null,version=0,passed=false,retries=0,undos=0,submitCount=0;const local=[];
      for(const event of server.history){
        if(!exactKeys(event,'name task workVersion work support')||event.task!=='task'
            ||!['work','undo','retry','submit','hint','replay'].includes(event.name))return false;
        const projected=profile.project({...shot,domainState:{...shot.domainState,...event.work}});
        if(!same(projected,event.work))return false;
        const changed=last===null||!same(last,event.work);
        if((event.name==='hint'||event.name==='replay')&&last!==null&&changed)return false;
        if(changed){version++;passed=false;}
        if(event.name==='hint'||event.name==='replay')support[event.name]++;
        if(event.name==='undo')undos++;if(event.name==='retry')retries++;
        if(event.workVersion!==version||!same(event.support,support))return false;
        if(event.name==='submit'){
          const a=server.attempts[submitCount];
          if(!a||a.task!=='task'||typeof a.correct!=='boolean'||!same(a.work,event.work)||a.workVersion!==version
              ||!same(a.support,support)||a.undoCount!==undos||a.retryCount!==retries||a.priorReveals!==0
              ||a.priorAttempts!==submitCount||a.priorPageAttempts!==submitCount||a.pictureSupport!==true
              ||a.assistanceOutsideApp!=='unobserved')return false;
          if(a.correct)passed=true;submitCount++;
        }
        if(event.name!=='replay')local.push(event);
        last=event.work;
      }
      if(submitCount!==server.attempts.length||!same(server.lastWork,last)||server.workVersion!==version
          ||!same(server.support,support)||server.undoCount!==undos||server.retryCount!==retries
          ||server.completed!==passed||server.phase!==(passed?'complete':'playing')
          ||!same(server.passedTasks,passed?['task']:[])||!same(server.firstAttempts,submitCount?{task:server.attempts[0]}:{})
          ||shot.helpFlags.hint!==(support.hint>0)||shot.currentWorkVersion!==local.length
          ||shot.revisionHistory.length!==Math.min(local.length,60))return false;
      if(last===null){if(!profile.fresh(shot,work))return false;}else if(!same(last,work))return false;
      const allowed={4:{work:['move','point','stroke','clear'],undo:['return'],retry:['reset'],submit:['bind'],hint:['hint']},
        6:{work:['evidence','edit'],retry:['reset'],submit:['check'],hint:['hint']},
        8:{work:['move-group','answer'],undo:['return-group'],retry:['reset'],submit:['check'],hint:['hint']}}[page];
      const tail=local.slice(-shot.revisionHistory.length);let p6First=null;
      for(let i=0;i<tail.length;i++){
        const event=tail[i],h=shot.revisionHistory[i];
        if(!exactKeys(h,'version action details')||h.version!==local.length-tail.length+i+1
            ||!allowed[event.name]?.includes(h.action)||!h.details||typeof h.details!=='object'||Array.isArray(h.details))return false;
        if(page===4&&h.action==='move'&&(!Number.isInteger(h.details.id)||!event.work.removed.includes(h.details.id)))return false;
        if(page===4&&h.action==='point'&&(h.details.symbol!=='subtract'||event.work.mode!=='point'||event.work.symbol!=='subtract'||event.work.strokes.length))return false;
        if(page===4&&h.action==='bind'&&!same(Object.fromEntries(subtractionFields[4].split(' ').map(k=>[k,h.details[k]])),event.work))return false;
        if(page===6&&['edit','check'].includes(h.action)&&(!same(h.details.equation,event.work.equation)||h.details.evidence!==event.work.evidence))return false;
        if(page===6&&h.action==='evidence'&&h.details.evidence!==event.work.evidence)return false;
        if(page===6&&p6First===null&&h.action==='edit')p6First={field:h.details.field,value:h.details.value,evidence:h.details.evidence,helped:event.support.hint>0};
        if(page===6&&p6First===null&&h.action==='check')p6First={field:null,value:null,evidence:h.details.evidence,equation:h.details.equation,helped:event.support.hint>0};
        if(page===8&&h.action==='check'&&(!same(h.details.removed,event.work.removed)||!same(h.details.remaining,event.work.remaining)||h.details.answer!==event.work.answer))return false;
      }
      const d=shot.domainState,trace=strokes=>{
        if(strokes.length!==1||strokes[0].length<2)return false;
        const p=strokes[0],a=p[0],b=p[p.length-1];
        return b[0]-a[0]>=.25&&Math.abs(b[1]-a[1])<=.12
          &&p.every(q=>Math.abs(q[1]-(a[1]+b[1])/2)<=.12)&&p.every((q,i)=>!i||q[0]>=p[i-1][0]-.08);
      };
      const localComplete=page===4?d.bound===true&&work.removed.length===1&&work.symbol==='subtract'
        &&(work.mode==='point'||trace(work.strokes))
        :page===6?d.checked===true&&work.evidence==='before'&&same(work.equation,{whole:5,change:2,result:3})
        :d.checked===true&&same(work.removed,work.groupA)&&work.answer===work.remaining.length;
      if(localComplete!==passed||shot.phase!==(shot.instructionsComplete?(passed?'complete':'playing'):'idle'))return false;
      if(!shot.instructionsComplete&&(local.length!==0||shot.firstAttempt!==null||!profile.fresh(shot,work)))return false;
      if(page===4&&submitCount){const a=server.attempts[0],w=a.work;
        if(!same(shot.firstAttempt,{removed:w.removed,symbol:w.symbol,strokes:w.strokes,mode:w.mode,helped:a.support.hint>0}))return false;
      } else if(page===8&&submitCount){const a=server.attempts[0],w=a.work;
        if(!same(shot.firstAttempt,{removed:w.removed,remaining:w.remaining,answer:w.answer,helped:a.support.hint>0}))return false;
      } else if(page===6){
        if(local.length>60&&shot.firstAttempt!==null)return false;
        if(!same(shot.firstAttempt,p6First))return false;
      } else if(!submitCount&&shot.firstAttempt!==null)return false;
      return true;
    }
    // The checkpoint bridge owns the private fresh/visibility/navigation
    // decision. Calling the authored handler directly creates no input event
    // and consequently cannot be recorded as a child's work or support.
    function begin() {
      const missingZeroSource = kind === 'math-zero' && page === 14 && sourceUnavailable;
      if (disposed || introDisarmed || introStarted || recoveryOnlySupport || (!freshOperation && !replayOpeningEvidence && !subtractionOpeningEvidence && !zeroCompletedEvidence) || !api.ready
          || (!aligned && !missingZeroSource) || pending || timer !== null || gesture !== null || parentReplays.length) return false;
      let shot, work, resetTeacherPhase=false, resumeCue=null, resumeSubtract=false;
      try {
        shot = capture();
        if (shot === null) return false;
        if (missingZeroSource) {
          if (shot.version !== 1 || shot.page !== 14 || shot.phase !== 'playing' || shot.sourceAvailable !== false
              || shot.work !== null || shot.currentCue !== 'zero-p14-repair-missing' || shot.audioStatus !== 'idle'
              || shot.workVersion !== 1 || !Array.isArray(shot.history) || shot.history.length !== 0
              || !Array.isArray(shot.attempts) || shot.attempts.length !== 0 || !exactKeys(shot.firstAttempts, '')
              || stable(shot.help) !== stable({replay:0,hint:0,demonstration:0})) return false;
        } else {
          work = profile.project(shot);
          if (stable(work) !== previous) return false;
        }
        if(zeroCompletedEvidence){
          if(!zeroCompletedVerified(shot,zeroCompletedEvidence))return false;
          resumeCue=page>=6&&page<=10?shot.uiState.cue:shot.currentCue;
        } else if(subtractionOpeningEvidence){
          if(!subtractResumeVerified(shot,subtractionOpeningEvidence))return false;
          resumeSubtract=shot.instructionsComplete;
        } else if(replayOpeningEvidence){
          if(!zeroReplayOpening(shot,replayOpeningEvidence,page))return false;
          resumeCue=page===3?'zero-p3-repair-start':'zero-p4-repair-trace';
        } else if (kind === 'math-subtract') {
          const d = shot.domainState;
          const untouched = page===2 ? d.checked===false : page===3 ? d.selected===null
            : page===4 ? d.bound===false : page===5 ? d.checked===null
            : page===6 ? d.editing===null&&d.checked===false
            : page===7 ? Array.isArray(d.visited)&&d.visited.length===0
            : page===8 ? d.selected===null&&d.checked===false
            : page===9||page===10 ? d.checked===false
            : page===11 ? d.storyVersion===1&&Array.isArray(d.previousWorks)&&d.previousWorks.length===0
            : page===12 ? d.selected===null&&d.checked===false&&d.storyVersion===1&&d.recordVersion===1 : false;
          if (!untouched || shot.phase !== 'idle' || stable(shot.helpFlags)!==stable({hint:false})
              || shot.instructionsComplete !== false || shot.firstAttempt !== null
              || shot.currentWorkVersion !== 0 || !Array.isArray(shot.revisionHistory)
              || shot.revisionHistory.length !== 0
              || (!profile.source && !profile.fresh(shot, work))) return false;
        } else if (page === 14 && !missingZeroSource) {
          if (shot.phase !== 'playing' || shot.sourceAvailable !== true || shot.currentCue !== 'zero-p14-repair-instruction'
              || shot.audioStatus !== 'idle' || shot.workVersion !== 2 || !Array.isArray(shot.history)
              || shot.history.length !== 0 || !Array.isArray(shot.attempts) || shot.attempts.length !== 0
              || !exactKeys(shot.firstAttempts, '') || stable(shot.help) !== stable({replay:0,hint:0,demonstration:0})) return false;
        } else if (page !== 14) {
          if (!profile.fresh(shot, work)) return false;
          if (kind==='math-zero'&&page===3){
            if(!zeroOpeningServerPristine||!zeroThreePristine(shot,'ready')&&!zeroThreePristine(shot,'playing'))return false;
            resetTeacherPhase=shot.phase==='playing';
          } else if(kind==='math-zero'&&page===4&&zeroFourPristine(shot)){
            if(!zeroOpeningServerPristine)return false;
            resumeCue='zero-p4-repair-trace';
          } else if(shot.phase!=='ready')return false;
          if (opening.cue && (shot.uiState?.cue !== opening.cue || shot.firstPrediction !== null
              || stable(shot.helpFlags) !== stable({hint:0,replay:0}))) return false;
        }
      } catch (_) { return false; }
      let start, rollbackOpening=null;
      if(resumeSubtract){
        let button=null,usable=false;
        try {button=document.getElementById('replay');usable=button instanceof Element&&button.tagName==='BUTTON'
          &&!button.disabled&&!button.hidden&&button.getAttribute('aria-disabled')!=='true'&&typeof button.onclick==='function';}catch(_){}
        if(!usable)return false;
        start=()=>button.onclick.call(button);
      } else if (opening.id && !resumeCue) {
        // Only this exact pristine p3 can have been advanced by its authored
        // teacher message without a cue. Restore its ready presentation, then
        // run the original start handler; no input or support is manufactured.
        const rollback=()=>{try{return checkpoint.restore.call(checkpoint,shot)===true&&stable(capture())===stable(shot);}catch(_){return false;}};
        if(resetTeacherPhase){
          rollbackOpening=rollback;
          const readyShot=JSON.parse(JSON.stringify(shot));readyShot.phase='ready';
          let restored=false;
          try {restored=checkpoint.restore.call(checkpoint,readyShot)===true&&stable(capture())===stable(readyShot);} catch (_) {}
          if(!restored){if(!rollback())error();return false;}
        }
        let button=null, usable=false;
        try {button=document.getElementById(opening.id);
          usable=button instanceof Element&&button.tagName==='BUTTON'&&!button.disabled&&!button.hidden
            &&button.getAttribute('aria-disabled')!=='true'&&typeof button.onclick==='function';
        } catch (_) {}
        if (!usable) {
          if(resetTeacherPhase&&!rollback())error();return false;
        }
        start = () => button.onclick.call(button);
      } else {
        // p6–p10 initialize S.cue to this same intro and their original say()
        // only assigns that cue and calls miraNarrate. p14 importSource sets
        // its cue/caption itself. The page's real playing event updates it.
        if (typeof window.miraNarrate !== 'function') return false;
        const cue = resumeCue || opening.cue || (missingZeroSource ? 'zero-p14-repair-missing' : 'zero-p14-repair-instruction');
        start = () => { const result = window.miraNarrate(cue); if (result && typeof result.catch === 'function') result.catch(() => {}); };
      }
      introStarted = true;
      try { start(); return true; } catch (_) {
        if(rollbackOpening){
          try{if(typeof window.miraCancelNarration==='function')window.miraCancelNarration();}catch(_){}
          rollbackOpening();introDisarmed=true;error();
        }
        return false;
      }
    }
    function showRecoveryNotice(message='点游戏里的喇叭，继续上课。') {
      if(recoveryNotice){recoveryNotice.textContent=message;return true;}
      const button=document.getElementById('replayBtn');
      if(!(button instanceof Element) || button.tagName!=='BUTTON' || button.disabled || button.hidden
          || button.getAttribute('aria-disabled')==='true' || !document.body || typeof document.createElement!=='function')return false;
      try {
        const notice=document.createElement('div');notice.setAttribute('role','status');
        notice.setAttribute('data-mira-recovery-notice','');
        notice.style.cssText='position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:2147483646;padding:7px 12px;border-radius:10px;background:#fff;color:#334155;font:14px system-ui;box-shadow:0 1px 6px #0002;pointer-events:none;';
        const guide=document.createElement('span');guide.setAttribute('aria-hidden','true');
        guide.setAttribute('data-mira-recovery-guide','');guide.textContent='▼';
        guide.style.cssText='position:absolute;top:-22px;left:50%;transform:translateX(-50%);color:#d64b20;font:900 20px system-ui;line-height:20px;pointer-events:none;';
        const previousStyle=button.getAttribute('style');
        button.style.setProperty('outline','4px solid #d64b20','important');
        button.style.setProperty('outline-offset','3px','important');
        button.appendChild(guide);recoveryTarget=button;recoveryTargetStyle=previousStyle;recoveryGuide=guide;
        notice.textContent=message;document.body.appendChild(notice);recoveryNotice=notice;return true;
      } catch (_) {clearRecoveryNotice();return false;}
    }
    function clearRecoveryNotice(){
      try {
        for(const node of [recoveryGuide,recoveryNotice])if(node){
          if(typeof node.remove==='function')node.remove();
          else if(node.parentNode)node.parentNode.removeChild(node);
        }
        if(recoveryTarget){
          if(recoveryTargetStyle===null)recoveryTarget.removeAttribute('style');
          else recoveryTarget.setAttribute('style',recoveryTargetStyle);
        }
      } catch (_) { /* ACK and learning state do not depend on notice cleanup. */ }
      recoveryNotice=null;recoveryGuide=null;recoveryTarget=null;recoveryTargetStyle=null;
    }
    function rollbackRecovery(){
      if(!recoveryOriginal||typeof checkpoint.restore!=='function')return false;
      try {
        if(typeof window.miraCancelNarration==='function')window.miraCancelNarration();
        return checkpoint.restore.call(checkpoint,recoveryOriginal)===true&&stable(capture())===stable(recoveryOriginal);
      } catch (_) {return false;}
    }
    const guarded = Object.freeze({...checkpoint, ...(opening ? {begin, beginRequiresSelectedSceneIntent:true,
      ...((kind==='math-zero' && page>=2 && page<=14 || kind==='math-subtract' && page>=2 && page<=12)
        ? {beginMayResumeSelectedSceneIntent:true} : {}),
      ...(typeof checkpoint.restore === 'function' ? {restore(...args) {
        // Preserve a pending selected-page intro across reviewed hydration;
        // the begin path still rechecks completed work and the private intent.
        // User disarming stays sticky.
        if(!(kind==='math-zero' && (page===3 && zeroThreePristine(args[0],'playing')
            || page===4 && zeroFourPristine(args[0]) || zeroReplayOpeningShot(args[0],page)
            || page>=2&&page<=14&&args[0]?.phase==='complete')
          || kind==='math-subtract' && args[0]?.sceneId===sceneId
             && ([4,6,8].includes(page) || [2,3,5,7,9,10,11,12].includes(page)
               && args[0]?.phase==='complete' && args[0]?.instructionsComplete===true)))introDisarmed = true;
        return checkpoint.restore.apply(checkpoint, args);
      }} : {}),
    } : {}), capture() {
      return disposed || recoveryOnlySupport || !aligned || !api.ready || pending || timer !== null || gesture !== null || parentReplays.length ? null : capture();
    }});
    window.miraActivityCheckpoint = guarded;
    function error() {
      if (disposed) return;
      epoch += 1; aligned = false; freshOperation = false; pending = false; gesture = null; parentReplays = [];
      clearTimeout(timer); timer = null;
      if(recoveryOnlySupport){
        recoveryRollbackFailed=!rollbackRecovery();clearRecoveryNotice();
        showRecoveryNotice('进度暂时无法保存，请重新进入课堂。');
      }
      window.dispatchEvent(new Event('mira-course-operation-error'));
    }
    // Display-only correction for the reviewed p9: the authored completion
    // message says to check another segment even after both have passed.
    // Never change the page checkpoint, the operation, or its narration.
    function p9CorrectWork(work,context) {
      const n=context==='incoming'?2:context==='departing'?3:0;
      if(!n)return false;
      return stable(work)===stable({context,total:n,changed:[],remaining:Array.from({length:n},(_,i)=>i+1),
        executed:true,operator:context==='incoming'?'add':'subtract',equation:{whole:n,change:0,result:n}});
    }
    function observeP9Feedback() {
      if(!p9FeedbackEnabled || disposed || typeof MutationObserver!=='function')return;
      const node=document.getElementById('feedbackMessage');
      if(node===p9FeedbackTarget)return;
      if(p9FeedbackObserver)p9FeedbackObserver.disconnect();
      p9FeedbackTarget=node; p9FeedbackObserver=null;
      if(node){
        p9FeedbackObserver=new MutationObserver(showP9Completion);
        p9FeedbackObserver.observe(node,{childList:true,characterData:true,subtree:true});
      }
    }
    function showP9Completion() {
      if(!p9FeedbackEnabled||!p9PassedTasks||p9PassedTasks.size!==2||!aligned||!api.ready
          ||disposed||pending||timer!==null||gesture!==null||parentReplays.length)return;
      try {
        const shot=capture(),d=shot?.domainState,ui=shot?.uiState,current=d?.work,context=current?.context;
        const other=context==='incoming'?'departing':context==='departing'?'incoming':null,prior=ui?.trials?.[other];
        if(!other||shot.phase!=='complete'||stable(ui?.passed?.slice().sort())!==stable(['departing','incoming'])
            ||ui.message!=='这一段的方向和数量都对上了。再检查另一段。'||ui.extra?.chosen!==true
            ||d.operatorChosen!==true||d.context!==context||stable(d.panels)!==stable(ui.trials)
            ||!p9CorrectWork(current,context)||!prior||prior.chosen!==true||!p9CorrectWork(prior.work,other))return;
        const message=document.getElementById('feedbackMessage');
        if(message&&message.textContent===ui.message)message.textContent='两段都检查好了。到港加0，离港减0。';
      } catch (_) { /* keep the original feedback when anything is unclear */ }
    }
    function recordP9Acknowledged(name,work,changed) {
      if(!p9PassedTasks||!['incoming','departing'].includes(work.context))return;
      if(changed)p9PassedTasks.delete(work.context);
      if(name==='submit'&&p9CorrectWork(work,work.context))p9PassedTasks.add(work.context);
    }
    function finishSaved(encoded) {
      previous = encoded; pending = false; drainParentReplays();
      showP9Completion();
      window.dispatchEvent(new CustomEvent('mira-activity-state-changed'));
    }
    function drainParentReplays() {
      if (!parentReplays.length || disposed || !aligned || !api.ready || pending || timer !== null || gesture !== null) return;
      pending = true;
      const token = epoch;
      timer = setTimeout(function settle(tries = 0) {
        if (disposed || token !== epoch) return;
        let shot, work;
        try { shot = capture(); } catch (_) { error(); return; }
        if (shot === null) {
          if (tries >= 1500) { error(); return; }
          timer = setTimeout(() => settle(tries + 1), 40); return;
        }
        timer = null;
        try { work = profile.project(shot); } catch (_) { error(); return; }
        const encoded = stable(work);
        if (!aligned || !api.ready || encoded !== previous) { error(); return; }
        const request=parentReplays[0];
        if(request.work&&encoded!==stable(request.work)){error();return;}
        if(request.demo&&shot.teacherDemo!==request.demo){error();return;}
        // This records a requested replay, never that audio played or was heard.
        // Playback is independent and must not wait for this network ACK.
        void api.send({name:request.name, work},request.id?{operationId:request.id}:undefined).then(() => {
          if (!disposed && token === epoch){parentReplays.shift();finishSaved(encoded);}
        }).catch(() => { if (!disposed && token === epoch) error(); });
      }, 0);
    }
    function block(event) { event.preventDefault(); event.stopImmediatePropagation(); }
    function handle(event) {
      // Programmatic toolbar clicks must not mutate authored replay/history
      // while the discrepancy remains unresolved.
      if(event.type==='click' && !event.isTrusted && (recoveryOnlySupport||!aligned||!api.ready)){block(event);return;}
      if(subtractOneKeyboardEnabled && event.type==='click' && !event.isTrusted
          && event.target===document.getElementById('truckZone')){
        if(event!==authorizedTruckClick){block(event);return;}
        authorizedTruckClick=null; // Consume the one event derived from real input.
      }
      if(subtractOneKeyboardEnabled && event.type==='click' && !event.isTrusted
          && event.target===truckKeyboardTarget){block(event);return;}
      const inkKey=kind==='math-zero'&&page===4&&event.type==='keydown'&&event.target?.id==='inkSurface';
      if(inkKey&&(!event.isTrusted||event.repeat&&event.key===' ')){block(event);return;}
      const crateKey=subtractOneKeyboardEnabled && event.type==='keydown' && ['Enter',' '].includes(event.key)
        && event.target instanceof Element && !!event.target.closest('[data-crate-id]');
      const predictionKey=subtractOneKeyboardEnabled && event.type==='keydown' && /^[1-5]$/.test(event.key);
      const zeroPredictionKey=subtractOneKeyboardEnabled && event.type==='keydown' && event.key==='0';
      // The frozen crate and digit handlers do not check isTrusted. Block
      // synthetic keys before they can mutate selection or prediction.
      if((crateKey || predictionKey) && !event.isTrusted){block(event);return;}
      if (!event.isTrusted || disposed || !(event.target instanceof Element)) return;
      // Any genuine activity in the frame wins over a queued automatic intro.
      introDisarmed = true;
      const svgKey=svgKeyboardEnabled && event.type==='keydown' && ['Enter',' '].includes(event.key)
        && !inkKey && typeof SVGElement==='function' && event.target instanceof SVGElement
        && event.target.matches('[role=button]') && document.getElementById('scene')?.contains(event.target);
      const truckKey=truckKeyboardEnabled&&event.type==='keydown'&&event.target===truckKeyboardTarget
        &&['Enter',' '].includes(event.key);
      const truckActivation=truckKey || truckKeyboardEnabled&&event.type==='click'&&event.target===truckKeyboardTarget;
      if(svgKey || truckKey || crateKey){
        if(event.repeat || heldSvgKeys.has(event.key)){heldSvgKeys.add(event.key);block(event);return;}
        heldSvgKeys.add(event.key);
      }
      if(inkKey&&gesture?.keyboard&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(event.key))return;
      const endingKeyboard=inkKey&&gesture?.keyboard&&event.key===' ';
      const action = zeroPredictionKey?null:truckActivation?{name:'work',control:truckKeyboardTarget}:endingKeyboard?{name:'work',control:gesture.control}:gesture && ['pointerup','pointercancel'].includes(event.type)
        ? {name: 'work', control: gesture.control} : profile.action(event, event.target);
      if(recoveryOnlySupport){
        const replay=event.type==='click' && event.target.closest('#replayBtn');
        if(!(replay && replay===document.getElementById('replayBtn') && action?.name==='replay')){
          if(action || event.type==='click')block(event);
          return;
        }
      }
      if (!action) { if(svgKey)block(event); return; }
      // An unavailable predecessor has no mathematical work to report, but
      // its spoken back-navigation explanation must remain reachable.
      if(sourceUnavailable){if(!['replay','hint'].includes(action.name))block(event);return;}
      if (!aligned || !api.ready || pending || timer !== null) { block(event); return; }
      if (gesture !== null && !endingKeyboard && !['pointerup', 'pointercancel'].includes(event.type)) { block(event); return; }
      const control = action.control || action.crate;
      if (control?.disabled || control?.getAttribute('aria-disabled') === 'true') { if(svgKey || truckActivation)block(event); return; }
      const dispatchKeyClick=truckActivation || svgKey && typeof event.target.click!=='function';
      const dispatchTarget=truckActivation?truckZone:event.target;
      const click=dispatchKeyClick ? svgKeyboardClick() : null;
      if(dispatchKeyClick && (!click || typeof dispatchTarget?.dispatchEvent!=='function')){
        block(event);return;
      }
      let before, beforeShot;
      if (endingKeyboard || event.type === 'pointerup' || event.type === 'pointercancel') {
        if (gesture === null || !endingKeyboard&&gesture.id !== event.pointerId) return;
        // Some authored checkpoints intentionally return null during a drag.
        // Use the real pre-gesture world, then wait for the pointer handler to
        // settle; never force-capture an intermediate drag snapshot.
        before = gesture.before; beforeShot = gesture.snapshot; gesture = null;
      } else {
        try {
          const shot = capture();
          if (shot === null) { block(event); return; }
          before = profile.project(shot); beforeShot = shot;
        } catch (_) { block(event); error(); return; }
      }
      if (event.type === 'pointerdown'||action.name==='keyboard-gesture') { gesture = {id: event.pointerId, keyboard:action.name==='keyboard-gesture', before, snapshot: beforeShot, control}; return; }
      pending = true;
      const token = epoch;
      timer = setTimeout(function settle(tries = 0) {
        if (disposed || token !== epoch) return;
        if (!aligned || !api.ready) { error(); return; }
        let shot;
        try { shot = capture(); } catch (_) { error(); return; }
        if (shot === null) {
          if (tries >= 1500) { error(); return; }
          timer = setTimeout(() => settle(tries + 1), 40); return;
        }
        timer = null;
        let work;
        try { work = profile.project(shot); } catch (_) { error(); return; }
        const encoded = stable(work), changed = encoded !== previous;
        // A completed flag or automatic animation is never a submit. A real
        // prediction event is not synthesized from the page's default value.
        let name = action.name === 'gesture' ? 'work' : action.name;
        if(name==='subtract-check')name=(page===2&&(work.answer===null||work.removed.length!==1)||page===8&&work.answer===null||page===9&&(work.prediction===null||work.removedA.length!==1||work.removedB.length!==3)
          ||page===10&&(work.answer===null||work.removed.length!==1))?'work':'submit';
        if(name==='save')name=work.saved!==null&&stable(work.saved)===stable(work.story)?'submit':'work';
        if(name==='count-process')name=changed&&work.answer!==null&&(work.method==='count-remaining'
          ?stable([...work.counted].sort())===stable([...work.remaining].sort()):stable(work.countdown)===stable([4,3]))?'submit':'work';
        if (name === 'zero-check') name = beforeShot.phase !== 'ready'
          && (page !== 5 || ['linking','link-feedback','complete'].includes(beforeShot.phase)) ? 'submit' : 'work';
        if(name==='zero-later-check')name=(page===6?work.prediction!==null:page===7?work.gateOpen&&work.prediction!==null
          :work.executed&&work.equation.result!==null&&(page!==9||shot.domainState.operatorChosen===true))?'submit':'work';
        // Each actual connection is saved. A full set is an explicit response;
        // partially filled links are not misgraded as a failed whole task.
        if (name === 'connection') name = changed && Object.values(work.links).every(value => value !== null) ? 'submit' : 'work';
        if (name === 'work' && !changed) { pending = false; drainParentReplays(); return; }
        if (name === 'work' && Array.isArray(before.removed) && Array.isArray(work.removed)
            && before.total===work.total && before.removed.some(id => !work.removed.includes(id))) name = 'undo';
        if(name==='work'&&kind==='math-subtract'&&page===9
          &&(['A','B'].some(side=>before['removed'+side].some(id=>!work['removed'+side].includes(id)))))name='undo';
        if(name==='work'&&kind==='math-zero'&&page===7&&before.gateOpen&&!work.gateOpen)name='undo';
        if(name==='work'&&kind==='math-zero'&&[11,13].includes(page)&&control?.closest('[data-boat]')){
          const a=page===13?before.story:before,b=page===13?work.story:work;
          if(a.changed.some(id=>!b.changed.includes(id)))name='undo';
        }
        if(recoveryOnlySupport && (name!=='replay' || !['requested','playing','ready','error','missing','cancelled','hidden'].includes(shot.audioStatus)
            || stable(shot)!==stable(zeroOneReplayed(recoveryOriginal,shot.audioStatus)))){error();return;}
        // Support controls must not secretly modify the mathematical work.
        if (['replay', 'hint', 'demonstration'].includes(name) && stable(before) !== encoded) { error(); return; }
        let saving=api.send({name, work});
        // This specific visible hint includes an actual separate pen demo.
        // Preserve both support types; no child stroke is manufactured.
        if(kind==='math-zero'&&page===4&&name==='hint'){
          if(shot.teacherDemo!=='zero-trace'){error();return;}
          saving=saving.then(()=>api.send({name:'demonstration',work}));
        }
        void saving.then(() => {
          if (disposed || token !== epoch) return;
          if(recoveryOnlySupport){recoveryOnlySupport=false;recoveryOriginal=null;clearRecoveryNotice();}
          if(p9FeedbackEnabled)recordP9Acknowledged(name,work,changed);
          finishSaved(encoded);
        }).catch(() => { if (!disposed && token === epoch) error(); });
      }, 0);
      if(click){
        // Invoke the authored click path only for this real activation.
        // The private event identity is consumed by the capture guard above.
        block(event);
        try {
          if(truckActivation)authorizedTruckClick=click;
          dispatchTarget.dispatchEvent(click);
        } catch (_) { error(); } finally { authorizedTruckClick=null; }
      }
    }
    const events = ['click', 'keydown', 'pointerdown', 'pointerup', 'pointercancel'];
    events.forEach(name => document.addEventListener(name, handle, true));
    function svgKeyUp(event){if(event.isTrusted)heldSvgKeys.delete(event.key);}
    function svgBlur(event){if(event.isTrusted)heldSvgKeys.clear();}
    if(svgKeyboardEnabled || subtractOneKeyboardEnabled){
      document.addEventListener('keyup',svgKeyUp,true);
      window.addEventListener('blur',svgBlur);
    }
    function narrationStarted(event) {
      if (!introStarted && event.detail?.status === 'playing') introDisarmed = true;
    }
    window.addEventListener('mira-narration-state', narrationStarted);
    function p9OperationReady(){observeP9Feedback();showP9Completion();}
    if(p9FeedbackEnabled)window.addEventListener('mira-course-operation-ready',p9OperationReady);
    function teacherDemonstration(event){
      // A script can forge MessageEvent.source but cannot forge isTrusted.
      // Stop such a message before the authored page can mutate demo/help.
      if(event.data?.type==='SET_WIDGET_STATE' && event.source===window.parent && event.isTrusted!==true){block(event);return;}
      if((recoveryOnlySupport||!aligned||!api.ready) && event.source===window.parent && (event.data?.type==='SET_WIDGET_STATE'
          || event.data?.type==='MIRA_INTERACTIVE_AUDIO_CONTROL' && event.data?.command==='play')){block(event);return;}
      if(kind!=='math-zero'||![1,2,5].includes(page)||event.isTrusted!==true||event.source!==window.parent||event.data?.type!=='SET_WIDGET_STATE')return;
      const v=event.data.state||event.data.payload;let demo=null;
      if(page===1&&Array.isArray(v?.boats)&&v.boats.length===2&&v.boats[0].id==='boat1'&&v.boats[0].present===true
        &&v.boats[1].id==='boat2'&&v.boats[1].present===false)demo='one-left';
      if(page===2&&v?.boatStep===1&&v.selectedScene==='ruler')demo='ruler-step';
      if(page===5&&Array.isArray(v?.boats)&&v.boats.length===4&&v.boats.every((b,i)=>b.id===['boat-A','boat-B','boat-C','boat-D'][i]&&b.departed===(i<2)))demo='two-left';
      if(!demo)return;
      if(disposed||!aligned||!api.ready||parentReplays.length>=64){block(event);return;}
      parentReplays.push({name:'demonstration',demo});drainParentReplays();
    }
    window.addEventListener('message',teacherDemonstration,true);
    return {
      // Called only by the authenticated parent's private operation-port branch.
      // Do not bind this to a public DOM event or accept a synthetic click.
      requestParentReplay(id,work) {
        if(recoveryOnlySupport)return 'blocked';
        if(sourceUnavailable)return true; // No eligible story task exists yet.
        if (disposed || !aligned || !api.ready || parentReplays.length >= 64) return false;
        if(id!==undefined&&!/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(id))return false;
        if(id&&parentReplays.some(request=>request.id===id))return true;
        parentReplays.push({name:'replay',id,work});drainParentReplays();return true;
      },
      restore(server,sourceContext) {
      if(recoveryOnlySupport&&(pending||timer!==null||gesture!==null||parentReplays.length)){
        recoveryRollbackFailed=!rollbackRecovery();clearRecoveryNotice();
      }
      epoch += 1; clearTimeout(timer); timer = null; pending = false; gesture = null; parentReplays = [];
      freshOperation = false; zeroOpeningServerPristine = false; replayOpeningEvidence = null; subtractionOpeningEvidence = null; subtractionSourceEvidence = null; zeroCompletedEvidence = null; zeroCompletedSource = null; p9PassedTasks = null;
      if(recoveryRollbackFailed){aligned=false;api.restoreConfirmed(false);return;}
      try {
        sourceUnavailable=false;
        requireValue(server?.kind===kind&&server.validator===kind+'-p'+page+'.v1');
        if(kind==='math-zero'&&[3,4].includes(page))zeroOpeningServerPristine=zeroInitialServer(server,page);
        if(profile.source){
          requireValue(exactKeys(sourceContext,'schemaVersion sourceSceneId available sourceWorkSha256 saved')
            &&sourceContext.schemaVersion==='mira.math-story-source.v1'&&sourceContext.sourceSceneId===(kind==='math-subtract'?'scene-p11':'scene-p13')
            &&typeof sourceContext.available==='boolean'
            &&(sourceContext.available?/^[a-f0-9]{64}$/.test(sourceContext.sourceWorkSha256)&&(kind==='math-subtract'?subtractStory:zeroStory)(sourceContext.saved)
              :sourceContext.sourceWorkSha256===null&&sourceContext.saved===null)
            &&typeof checkpoint.importSource==='function');
          const sourceForPage=kind==='math-subtract'&&page===12&&opening&&sourceContext.available
            ? {...sourceContext,saved:orderedSubtractStory(sourceContext.saved,false)} : sourceContext;
          requireValue(checkpoint.importSource(sourceForPage)===true);
          if(!sourceContext.available){sourceUnavailable=true;aligned=false;
            freshOperation=kind==='math-zero'&&page===14&&server.lastWork===null;
            api.restoreConfirmed(true);if(handoff){handoff.release();handoff=null;}return;}
        }
        let shot = capture(), work = profile.project(shot);
        if(kind==='math-zero' && page===1){
          const recovery=zeroOneRecovery(shot,server,contentSha256);
          if(recovery){
            introDisarmed=true;recoveryOriginal=recovery.original;recoveryOnlySupport=true;
            if(recovery.mode==='support'){
              previous=stable(work);aligned=showRecoveryNotice();
              api.restoreConfirmed(aligned);if(aligned&&handoff){handoff.release();handoff=null;}return;
            }
            if(recovery.mode==='mismatch'){
              aligned=false;showRecoveryNotice('进度暂时无法恢复，请重新进入课堂。');api.restoreConfirmed(false);return;
            }
            recoveryOnlySupport=false;recoveryOriginal=null;clearRecoveryNotice();
          }
        }
        if (kind==='math-subtract' && page===2 && server.lastWork!==null && stable(work)!==stable(server.lastWork)) {
          const repaired=subtractTwoAcknowledgedRepair(shot,server,contentSha256);
          if (repaired && typeof checkpoint.restore==='function') {
            introDisarmed=true;
            let verified=false;
            try {
              if (checkpoint.restore.call(checkpoint,repaired)===true) {
                const recovered=capture();
                if (stable(recovered)===stable(repaired) && stable(profile.project(recovered))===stable(server.lastWork)) {
                  shot=recovered;work=profile.project(recovered);verified=true;
                }
              }
            } catch (_) { /* the unchanged snapshot remains the recovery source */ }
            if (!verified) {
              try { checkpoint.restore.call(checkpoint,shot); } catch (_) { /* fail closed */ }
            }
          }
        }
        previous = stable(work);
        const sourceChanged=profile.source&&(!server.lastWork||server.lastWork.sourceWorkSha256!==sourceContext.sourceWorkSha256);
        const imported=sourceChanged&&work.sourceWorkSha256===sourceContext.sourceWorkSha256
          &&stable(work.story)===stable(sourceContext.saved)&&stable(work.saved)===stable(sourceContext.saved)
          &&(kind==='math-subtract'?Object.values(work.links).every(value=>value===null):work.zeroRole===null);
        aligned = server?.kind === kind && server.validator === kind + '-p' + page + '.v1'
          && (profile.source?sourceChanged?imported:previous===stable(server.lastWork)
            :server.lastWork === null ? profile.fresh(shot, work) || kind==='math-zero' && page===6 && zeroSixNoopRecovery(shot,server,contentSha256) : previous === stable(server.lastWork));
      } catch (_) { aligned = false; }
      freshOperation = aligned && server?.lastWork === null;
      if(aligned&&kind==='math-zero'&&page===14&&sourceContext?.available===true){
        zeroCompletedSource=JSON.parse(JSON.stringify(sourceContext));
      }
      if(aligned&&kind==='math-zero'&&page>=2&&page<=14&&opening){
        try{if(zeroCompletedVerified(capture(),server))zeroCompletedEvidence=JSON.parse(JSON.stringify(server));}catch(_){zeroCompletedEvidence=null;}
      }
      if(aligned && kind==='math-zero' && [3,4].includes(page) && opening) {
        try {const shot=capture();if(zeroReplayOpening(shot,server,page))replayOpeningEvidence=JSON.parse(JSON.stringify(server));}
        catch (_) {replayOpeningEvidence=null;}
      }
      if(aligned&&kind==='math-subtract'&&page===12&&sourceContext?.available===true){
        subtractionSourceEvidence=JSON.parse(JSON.stringify(sourceContext));
      }
      if(aligned&&kind==='math-subtract'&&page>=2&&page<=12&&opening){
        try{if(subtractResumeVerified(capture(),server))subtractionOpeningEvidence=JSON.parse(JSON.stringify(server));}catch(_){subtractionOpeningEvidence=null;}
      }
      if(p9FeedbackEnabled&&aligned&&Array.isArray(server?.passedTasks)){
        const tasks=server.passedTasks,unique=new Set(tasks);
        if(tasks.length===unique.size&&tasks.every(task=>['incoming','departing'].includes(task))
            &&server.completed===(tasks.length===2)&&server.phase===(server.completed?'complete':'playing')
            &&(!tasks.length||server.lastWork!==null))p9PassedTasks=unique;
      }
      api.restoreConfirmed(aligned);
      if(aligned&&handoff){handoff.release();handoff=null;}
      observeP9Feedback();showP9Completion();
    }, dispose() {
      const unverified=pending||timer!==null||gesture!==null||parentReplays.length>0||!aligned;
      const unsafe=recoveryOnlySupport||unverified||!api.ready;
      disposed = true; epoch += 1; clearTimeout(timer);
      clearRecoveryNotice();
      if (window.miraActivityCheckpoint === guarded) {
        let safe=!recoveryOnlySupport;
        if(recoveryOnlySupport&&recoveryOriginal&&typeof checkpoint.restore==='function'){
          safe=rollbackRecovery();
        }
        // A failed rollback keeps this closed guard in place; a reconnect must
        // not expose the unacknowledged authored world to checkpoint capture.
        if(!safe || unsafe){
          const handoffCheckpoint=safe && (recoveryOnlySupport||!unverified) ? checkpoint : guarded;
          if(!handoff||handoff.released)handoff=holdCheckpointInput(handoffCheckpoint);
          checkpointHandoffs.set(guarded,handoff);
        }else window.miraActivityCheckpoint=checkpoint;
      }
      events.forEach(name => document.removeEventListener(name, handle, true));
      if(truckKeyboardTarget)truckKeyboardTarget.remove();
      if(svgKeyboardEnabled || subtractOneKeyboardEnabled){
        document.removeEventListener('keyup',svgKeyUp,true);
        window.removeEventListener('blur',svgBlur);
      }
      window.removeEventListener('mira-narration-state', narrationStarted);
      if(p9FeedbackEnabled)window.removeEventListener('mira-course-operation-ready',p9OperationReady);
      if(p9FeedbackObserver){p9FeedbackObserver.disconnect();p9FeedbackObserver=null;p9FeedbackTarget=null;}
      window.removeEventListener('message',teacherDemonstration,true);
    }};
  };
})();
