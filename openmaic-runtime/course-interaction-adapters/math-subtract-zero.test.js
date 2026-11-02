const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, 'math-subtract-zero.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
// Digests of the two frozen releases; later revisions must opt in explicitly.
const hashes = {
  'math-subtract':[null,
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
  'math-zero':[null,
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
function initial(page = 1, kind = 'math-subtract') {
  if (kind === 'math-zero') {
    const work = {1: {removed: [], remaining: [1,2], answer: null},
      2: {context:'harbour',objects:[],position:0,meaning:null},
      3: {order:[1,2,3,4,5,0],quantities:[[],[1],[1,2],[1,2,3],[1,2,3,4],[1,2,3,4,5]]},
      4: {mode:'trace',strokes:[]},
      5: {removed:[],remaining:[1,2,3,4],equation:{whole:null,change:null,result:null},links:{whole:null,change:null,result:null}},
      6: {total:3,removed:[],remaining:[1,2,3],prediction:null},
      7: {incoming:[],remaining:[1,2,3],gateOpen:false,prediction:null},
      8: {removed:[],remaining:[1,2],executed:false,equation:{whole:2,change:0,result:null}},
      9: {context:'incoming',total:2,changed:[],remaining:[1,2],executed:false,operator:'add',equation:{whole:2,change:0,result:null}},
      10:{operator:'add',changed:[],remaining:[],executed:false,equation:{whole:0,change:0,result:null}},
      11:{total:2,operator:'add',changed:[],remaining:[1,2],executed:false,equation:{whole:null,change:null,result:null}},
      12:{context:'tools',objects:[],position:0,meaning:null},
      13:{story:{type:'all-left',total:3,operator:'subtract',changed:[],remaining:[1,2,3],equation:{whole:null,change:null,result:null}},saved:null},
      14:null}[page];
    if(page===1)return {version:1,page,phase:'ready',work,selected:null,activeRole:'whole',answer:null,
      firstAttempts:{},attempts:[],help:{replay:0,hint:0,demonstration:0},history:[],workVersion:1,
      completedContexts:[],tracePassed:false,traceWork:null,currentCue:null,audioStatus:'idle',pen:[0.5,0.1],penDown:false,teacherDemo:null};
    if(page===3)return {version:1,page,phase:'ready',work,selected:null,activeRole:'whole',answer:null,
      firstAttempts:{},attempts:[],help:{replay:0,hint:0,demonstration:0},history:[],workVersion:1,
      completedContexts:[],tracePassed:false,traceWork:null,currentCue:null,audioStatus:'idle',pen:[0.5,0.1],penDown:false,teacherDemo:null};
    if(page>=6&&page<=10)return {version:1,phase:'ready',domainState:{work},prediction:null,firstPrediction:null,
      stableObjectIds:Array.from({length:page===6||page===7?3:page===8||page===9?2:0},(_,i)=>i+1),
      firstAttempt:null,helpFlags:{hint:0,replay:0},revisionHistory:[],currentWorkVersion:1,uiState:{cue:'p'+page+'-a1'}};
    if(page===14)return {version:1,page,phase:'playing',work:null,sourceAvailable:false,currentCue:null,
      audioStatus:'idle',help:{replay:0,hint:0,demonstration:0},history:[],workVersion:1,attempts:[],firstAttempts:{}};
    return {version:1,page,phase:'ready',work,history:[],workVersion:1,attempts:[],firstAttempts:{}};
  }
  if([2,4,6,7,8,9,10,11,12].includes(page))return {
    version:1,sceneId:'scene-p'+page,phase:'idle',prediction:null,instructionsComplete:false,
    stableObjectIds:page===9?['A1','A2','A3','A4','A5','B1','B2','B3','B4','B5']:Array.from({length:[2,4,7].includes(page)?4:page===10?3:5},(_,i)=>i+1),
    domainState:{2:{removed:[],remaining:[1,2,3,4],answer:null,checked:false},
      4:{total:4,removed:[],remaining:[1,2,3,4],symbol:null,strokes:[],mode:'trace',bound:false},
      6:{removed:[1,2],remaining:[3,4,5],equation:{whole:3,change:2,result:3},evidence:null,editing:null,checked:false},
      7:{removed:[4],remaining:[1,2,3],method:'count-remaining',counted:[],countdown:[],answer:null,visited:[]},
      8:{groupA:[1,2,3],groupB:[4,5],removed:[],remaining:[1,2,3,4,5],answer:null,selected:null,checked:false},
      9:{removedA:[],remainingA:[1,2,3,4,5],removedB:[],remainingB:[1,2,3,4,5],prediction:null,checked:false},
      10:{removed:[],remaining:[1,2,3],answer:null,checked:false},
      11:{story:{total:3,removed:[],remaining:[1,2,3],equation:{whole:3,change:0,result:3}},saved:null,storyVersion:1,previousWorks:[]},
      12:{story:null,saved:null,links:{whole:null,change:null,result:null},sourceWorkSha256:null,storyVersion:1,recordVersion:1,selected:null,checked:false}}[page],
    firstAttempt:null,helpFlags:{hint:false},revisionHistory:[],currentWorkVersion:0};
  if (page === 3) return {version: 1, sceneId: 'scene-p3', phase:'idle', instructionsComplete: false,
    stableObjectIds: ['b1', 'b2', 'b3', 'b4'],
    domainState: {connections: {original: null, removed: null, remaining: null}, selected: null},
    firstAttempt: null, helpFlags: {hint: false}, revisionHistory: [], currentWorkVersion: 0};
  if (page === 5) return {version: 1, sceneId: 'scene-p5', phase:'idle', instructionsComplete: false,
    stableObjectIds: ['L1','L2','L3','L4','L5','R1','R2','R3'],
    domainState: {leftItems: ['L1','L2','L3','L4','L5'], rightItems: ['R1','R2','R3'], removedLeft: [],
      pairs: [['L1','R1'],['L2','R2'],['L3','R3']], checked: null},
    firstAttempt: null, helpFlags: {hint: false}, revisionHistory: [], currentWorkVersion: 0};
  return {version: 1, phase: 'ready', stableObjectIds: [1,2,3,4,5].map(n => 'crate_' + n),
    domainState: {crates: [1,2,3,4,5].map(n => ({id: 'crate_' + n, state: 'warehouse'})), prediction: null, currentWorkVersion: 1},
    prediction: null, firstAttempt: null, helpFlags: {replayUsed: false, hintUsed: false, seenDemo: false},
    revisionHistory: [], currentWorkVersion: 1};
}
function initialZeroThreeServer() {
  return {kind:'math-zero',validator:'math-zero-p3.v1',phase:'playing',completed:false,lastWork:null,
    workVersion:0,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],
    support:{hint:0,replay:0,demonstration:0},undoCount:0,retryCount:0,exposureCount:0,history:[],
    evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'};
}
function fixture(kind = 'math-subtract', page = 1, contentSha256 = hashes[kind]?.[page], options = {}) {
  const handlers = {}, sent = [], sendOptions=[], confirmations = [], notices = [], timers = new Map(), acknowledgements = [],windowHandlers={};
  const add=(table,name,fn)=>{(table[name]??=[]).push(fn);};
  const remove=(table,name,fn)=>{table[name]=(table[name]||[]).filter(value=>value!==fn);};
  const run=(table,name,event)=>{for(const fn of table[name]||[]){fn(event);if(event.stopped)break;}};
  let tid = 0, snapshot = initial(page, kind);
  class Element {
    constructor(id, disabled = false, selectors=[]) { this.id = id; this.disabled = disabled;this.selectors=selectors;
      this.style={setProperty(name,value){this[name]=value;}};this.attributes={};this.children=[]; }
    closest(selectors) {
      return selectors.split(',').some(selector => this.selectors.includes(selector)||selector === '#' + this.id
        || selector === '[data-crate-id]' && this.id.startsWith('crate_')
        || selector === '.toolbutton' && this.id.startsWith('tool-')
        || selector === '[data-zero=true]' && this.id === 'zeroChip'
        || /^\[data-(boat|zone|context|meaning|insert|role)\]$/.test(selector)
          && this.id.startsWith(selector.slice(6,-1) + '-')) ? this : null;
    }
    matches(selector) { return this.closest(selector)!==null||selector === '[role=button]' && /^(boat|zone|context|meaning|insert|role)-/.test(this.id); }
    getAttribute(name) { return this.attributes?.[name] ?? null; }
    setAttribute(name,value){this.attributes[name]=value;}
    removeAttribute(name){delete this.attributes[name];}
    appendChild(node){this.children.push(node);node.parentNode=this;}
    insertBefore(node,ref){const i=ref===null?-1:this.children.indexOf(ref);if(i<0)this.children.push(node);else this.children.splice(i,0,node);node.parentNode=this;}
    get nextSibling(){if(!this.parentNode)return null;const a=this.parentNode.children;return a[a.indexOf(this)+1]||null;}
    remove(){if(this.parentNode){const a=this.parentNode.children;const i=a.indexOf(this);if(i>=0)a.splice(i,1);this.parentNode=null;}}
  }
  let sceneClick=()=>{};
  const dispatched=[];
  class TestEvent {
    constructor(type, opts={}) { this.type=type;this.bubbles=!!opts.bubbles;this.cancelable=!!opts.cancelable;this.isTrusted=false; }
    preventDefault() { this.defaultPrevented=true; }
    stopImmediatePropagation() { this.stopped=true; }
    initMouseEvent(type,bubbles,cancelable) {this.type=type;this.bubbles=bubbles;this.cancelable=cancelable;}
    initEvent(type,bubbles,cancelable) {this.type=type;this.bubbles=bubbles;this.cancelable=cancelable;}
  }
  class SvgElement extends Element {
    dispatchEvent(event) {
      event.target=this;dispatched.push(event);
      run(handlers,event.type,event);
      if(!event.stopped && event.bubbles)sceneClick(event);
      return !event.defaultPrevented;
    }
  }
  const mutationObservers=[];
  class TestMutationObserver {
    constructor(callback){this.callback=callback;this.connected=false;mutationObservers.push(this);}
    observe(node){this.node=node;this.connected=true;}
    disconnect(){this.connected=false;}
  }
  const imports=[], restoredSnapshots=[];
  let importer=()=>false;
  let restorer=value=>{snapshot=plain(value);return true;};
  const checkpoint = Object.freeze({version: 1, capture: () => snapshot === null ? null : plain(snapshot),
    restore: value=>{restoredSnapshots.push(plain(value));return restorer(value);},
    importSource:ctx=>{imports.push(plain(ctx));return importer(ctx);}});
  const window = {miraActivityCheckpoint: checkpoint, parent:{},addEventListener:(name,fn)=>add(windowHandlers,name,fn),
    removeEventListener:(name,fn)=>remove(windowHandlers,name,fn),dispatchEvent: event => notices.push(event.type),
    miraCourseOperation: {ready: true, restoreConfirmed: matches => confirmations.push(matches),
      send: (op,options) => {sent.push(plain(op));sendOptions.push(options); return new Promise((resolve, reject) => acknowledgements.push({resolve, reject}));}}};
  const elements = new Map();
  let truckClick=()=>{};let truck=null,sceneArea=null,activityShell=null;
  if(options.truck){
    sceneArea=new Element('sceneArea');activityShell=new Element('activity-shell');activityShell.appendChild(sceneArea);
    activityShell.appendChild(new Element('prediction-panel'));elements.set('sceneArea',sceneArea);
    truck=new Element('truckZone');truck.tagName='DIV';truck.setAttribute('aria-label','货车区');sceneArea.appendChild(truck);
    if(options.truckRole)truck.setAttribute('role',options.truckRole);
    truck.dispatchEvent=event=>{event.target=truck;dispatched.push(event);run(handlers,event.type,event);
      if(!event.stopped&&event.type==='click')truckClick(event);return !event.defaultPrevented;};
    elements.set('truckZone',truck);
  }
  const statusNodes=[];
  elements.set('scene',{contains:target=>target.inScene!==false});
  const document = {addEventListener: (name, handler) => add(handlers,name,handler),
    removeEventListener: (name,handler) => remove(handlers,name,handler), getElementById: id => elements.get(id) || null,
    createElement:name=>name==='button'?Object.assign(new Element('mira-truck-assist'),{tagName:'BUTTON'}):({style:{},setAttribute(name,value){(this.attrs??={})[name]=value;},
      remove(){this.removed=true;}}),body:{appendChild(node){statusNodes.push(node);}}};
  if(!options.noLegacyEvent)document.createEvent=type=>{
    if(options.legacyGenericOnly && type==='MouseEvents')throw new Error('legacy mouse event unavailable');
    return new TestEvent('');
  };
  vm.runInNewContext(source, {window, document, Element, SVGElement:SvgElement,MutationObserver:TestMutationObserver,
    MouseEvent:options.noMouseEvent?undefined:TestEvent, Event: class {constructor(type) {this.type = type;}},
    CustomEvent: class {constructor(type) {this.type = type;}},
    setTimeout: fn => {timers.set(++tid, fn); return tid;}, clearTimeout: id => timers.delete(id)});
  const adapter = window.installMathSubtractZeroCourseAdapter('scene-p' + page, kind, contentSha256);
  const sendEvent = (id, type = 'click', extras = {}) => {
    let blocked = false;
    const event={type, isTrusted: true, pointerId: 1, target: new Element(id, extras.disabled, extras.selectors),
      preventDefault() {blocked = true;}, stopImmediatePropagation() {blocked=true;this.stopped=true;}, ...extras};
    run(handlers,type,event);
    if(type==='click'&&event.isTrusted&&event.target instanceof SvgElement&&!blocked)sceneClick(event);
    if(type==='click'&&!blocked&&typeof event.target.onclick==='function')event.target.onclick(event);
    return blocked;
  };
  return {window, adapter, sent, sendOptions,confirmations, notices, checkpoint,imports,restoredSnapshots,statusNodes,
    importer:fn=>importer=fn, restorer:fn=>restorer=fn,
    svg: (id, options={}) => Object.assign(new SvgElement(id,false,options.selectors||[]),options),
    nativeClick: target=>{target.click=()=>target.dispatchEvent(new TestEvent('click',{bubbles:true,cancelable:true}));},
    sceneClick: fn=>sceneClick=fn, truck, sceneArea, activityShell,
    truckButton:activityShell?.children.find(e=>e.id==='mira-truck-assist')||null, truckClick: fn=>truckClick=fn, dispatched,
    keyup: (key, trusted=true)=>run(handlers,'keyup',{key,isTrusted:trusted,preventDefault(){},stopImmediatePropagation(){this.stopped=true;}}),
    blur: (trusted=true)=>run(windowHandlers,'blur',{isTrusted:trusted}),
    start: (handler, options = {}) => {
      const id = kind === 'math-subtract' ? 'start' : 'startBtn';
      const button = new Element(id); Object.assign(button, {tagName:'BUTTON', hidden:false, onclick:handler,
        click(){throw new Error('must not synthesize an input event');}}, options);
      elements.set(id, button); return button;
    },
    feedback: value=>{const node=new Element('feedbackMessage');node.textContent=value;elements.set('feedbackMessage',node);return node;},
    operationReady: ()=>run(windowHandlers,'mira-course-operation-ready',{}),
    redraw: node=>mutationObservers.filter(o=>o.connected&&o.node===node).forEach(o=>o.callback()),
    observers:mutationObservers,
    replay: handler=>{const id=kind==='math-subtract'&&page!==1?'replay':'replayBtn';const button=new Element(id);Object.assign(button,{tagName:'BUTTON',hidden:false,onclick:handler});
      elements.set(id,button);return button;},
    message:(data,source=window.parent,isTrusted=true)=>{let blocked=false;
      run(windowHandlers,'message',{source,data,isTrusted,preventDefault(){},stopImmediatePropagation(){blocked=true;this.stopped=true;}});return blocked;},
    narration: detail => run(windowHandlers,'mira-narration-state',{detail}),
    set: value => snapshot = value, get: () => snapshot,
    changePrediction: value => {snapshot.prediction = value; snapshot.domainState.prediction = value;},
    move: (n, state = 'truck') => snapshot.domainState.crates.find(crate => crate.id === 'crate_' + n).state = state,
    restore: (lastWork = null,ctx) => adapter.restore(kind==='math-zero'&&page===1&&lastWork===null
      ? interruptedZeroOne().server : kind==='math-zero'&&page===3&&lastWork===null
        ? initialZeroThreeServer() : {kind, validator: kind + '-p' + page + '.v1', lastWork},ctx),
    event: sendEvent,
    flush: async () => {const active = [...timers.values()]; timers.clear(); active.forEach(fn => fn()); await Promise.resolve();},
    ack: async () => {acknowledgements.shift().resolve(); await Promise.resolve();},
    reject: async () => {acknowledgements.shift().reject(new Error('not_saved')); await Promise.resolve(); await Promise.resolve();},
  };
}
// Exact persisted p2 checkpoint and acknowledged server history observed at
// the interrupted connection. The correction is work, not another submit.
function interruptedSubtractTwo() {
  const before={removed:[1],remaining:[2,3,4],answer:4}, after={removed:[1],remaining:[2,3,4],answer:3};
  const support={hint:0,replay:1,demonstration:0};
  const attempt={task:'task',work:before,correct:false,workVersion:3,support,retryCount:0,undoCount:0,
    priorAttempts:0,priorPageAttempts:0,priorReveals:0,pictureSupport:true,assistanceOutsideApp:'unobserved'};
  const event=(name,workVersion,work)=>({name,task:'task',workVersion,work,support});
  return {shot:{version:1,sceneId:'scene-p2',phase:'playing',prediction:null,instructionsComplete:true,
    stableObjectIds:[1,2,3,4],domainState:{...before,checked:true},firstAttempt:{...before,helped:false},
    helpFlags:{hint:false},revisionHistory:[{version:1,action:'move',details:{id:1}},
      {version:2,action:'answer',details:{answer:4}},
      {version:3,action:'check',details:{...before,checked:false}}],currentWorkVersion:3},
  server:{kind:'math-subtract',validator:'math-subtract-p2.v1',phase:'playing',completed:false,lastWork:after,
    workVersion:4,attempts:[attempt],firstAttempts:{task:attempt},firstPredictions:{},latestPredictions:{},
    passedTasks:[],support,undoCount:0,retryCount:0,exposureCount:0,
    history:[event('replay',1,{removed:[],remaining:[1,2,3,4],answer:null}),
      event('work',2,{removed:[1],remaining:[2,3,4],answer:null}),event('work',3,before),
      event('submit',3,before),event('work',4,after)]}};
}
function interruptedZeroOne() {
  const work={removed:[],remaining:[1,2],answer:null},help={replay:1,hint:0,demonstration:0};
  const shot={version:1,page:1,phase:'playing',work,selected:null,activeRole:'whole',answer:null,
    firstAttempts:{},attempts:[],help,history:[{name:'replay',version:1,before:work,after:work,help}],
    workVersion:2,completedContexts:[],tracePassed:false,traceWork:null,currentCue:'zero-p1-repair-start',
    audioStatus:'ready',pen:[0.5,0.1],penDown:false,teacherDemo:null};
  const server={kind:'math-zero',validator:'math-zero-p1.v1',phase:'playing',completed:false,lastWork:null,
    workVersion:0,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],
    support:{hint:0,replay:0,demonstration:0},undoCount:0,retryCount:0,exposureCount:0,history:[],
    evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'};
  const support={hint:0,replay:1,demonstration:0};
  return {shot,server,acknowledged:{...server,lastWork:work,workVersion:1,support,
    history:[{name:'replay',task:'task',workVersion:1,work,support}]}};
}
function authoredZeroReplay(f) {
  const s=f.get(),before=plain(s.work);s.help.replay++;
  s.history.push({name:'replay',version:s.workVersion,before,after:plain(s.work),help:plain(s.help)});
  s.workVersion++;s.audioStatus='requested';
}
test('zero p1 accepts the untouched hidden audio state before first entry',()=>{
  for(const audioStatus of ['idle','hidden']){
    const f=fixture('math-zero',1),shot=initial(1,'math-zero');shot.audioStatus=audioStatus;f.set(shot);
    let starts=0;f.start(()=>starts++);f.replay(()=>{});f.restore();
    assert.equal(f.confirmations.at(-1),true);assert.equal(f.statusNodes.length,0);
    assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);
    assert.equal(f.window.miraActivityCheckpoint.begin(),true);assert.equal(starts,1);
  }
});
test('zero p1 still rejects noninitial audio and altered work under an initial server state',()=>{
  for(const mutate of [
    shot=>{shot.audioStatus='ready';},shot=>{shot.audioStatus='error';},
    shot=>{shot.audioStatus='hidden';shot.currentCue='unexpected';},
    shot=>{shot.audioStatus='hidden';shot.help.hint=1;},
    shot=>{shot.audioStatus='hidden';shot.history.push({name:'unknown'});},
  ]){
    const f=fixture('math-zero',1),shot=initial(1,'math-zero');mutate(shot);f.set(shot);f.replay(()=>{});f.restore();
    assert.equal(f.confirmations.at(-1),false);assert.equal(f.event('boat-1','pointerdown'),true);
    assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);
  }
});
test('zero p1 locks the discrepant snapshot until a new genuine replay is acknowledged',async()=>{
  const {shot,server}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));
  const replay=f.replay(()=>authoredZeroReplay(f));f.adapter.restore(plain(server));
  assert.equal(f.confirmations.at(-1),true);assert.equal(f.statusNodes.length,1);
  assert.match(f.statusNodes[0].textContent,/喇叭/);assert.match(f.statusNodes[0].style.cssText,/pointer-events:none/);
  assert.equal(replay.children.length,1);assert.equal(replay.children[0].textContent,'▼');
  assert.match(replay.style.outline,/solid/);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  assert.equal(f.event('boat-1','pointerdown'),true);assert.equal(f.event('number-0'),true);
  assert.equal(f.event('replayBtn','click',{target:replay,isTrusted:false}),true);
  assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);
  assert.equal(f.message({type:'MIRA_INTERACTIVE_AUDIO_CONTROL',command:'play',channel:'validchannel'}),true);
  assert.equal(f.message({type:'SET_WIDGET_STATE',state:{}}),true);
  assert.equal(f.adapter.requestParentReplay('12345678-1234-4123-8123-123456789abc'),'blocked');
  f.window.miraCourseOperation.ready=false;
  assert.equal(f.event('replayBtn','click',{target:replay}),true);assert.deepEqual(f.get(),shot);
  f.window.miraCourseOperation.ready=true;
  assert.equal(f.event('replayBtn','click',{target:replay}),false);await f.flush();
  assert.deepEqual(f.sent,[{name:'replay',work:{removed:[],remaining:[1,2],answer:null}}]);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.equal(f.event('number-0'),true);
  await f.ack();const recovered=f.window.miraActivityCheckpoint.capture();
  assert.equal(recovered.help.replay,2);assert.deepEqual(recovered.history[0],shot.history[0]);
  assert.equal(recovered.history[1].name,'replay');assert.equal(recovered.workVersion,3);
  assert.equal(f.statusNodes[0].removed,true);assert.equal(f.event('number-0'),false);
});
test('zero p1 keeps recovery locked when replay is rejected, unacknowledged, or locally changed',async()=>{
  const {shot,server}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));
  const replay=f.replay(()=>authoredZeroReplay(f));f.adapter.restore(plain(server));
  f.event('replayBtn','click',{target:replay});await f.flush();assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  await f.reject();assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  assert.match(f.statusNodes.at(-1).textContent,/无法保存/);assert.equal(f.event('number-0'),true);
  f.adapter.restore(plain(server));assert.equal(f.confirmations.at(-1),true);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  const tampered=fixture('math-zero',1);tampered.set(plain(shot));
  const corrupt=tampered.replay(()=>{authoredZeroReplay(tampered);tampered.get().work.answer=0;});
  tampered.adapter.restore(plain(server));tampered.event('replayBtn','click',{target:corrupt});await tampered.flush();
  assert.deepEqual(tampered.sent,[]);assert.equal(tampered.window.miraActivityCheckpoint.capture(),null);
});
test('zero p1 does not attribute a server replay from another tab to an older local checkpoint',()=>{
  const {shot,acknowledged}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));f.replay(()=>{});
  f.adapter.restore(plain(acknowledged));assert.equal(f.confirmations.at(-1),true);
  assert.deepEqual(f.get(),shot);assert.deepEqual(f.restoredSnapshots,[]);assert.deepEqual(f.sent,[]);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.match(f.statusNodes[0].textContent,/喇叭/);
  assert.equal(f.event('number-0'),true);
});
test('zero p1 re-entry preserves a persisted replay and requires a new real replay and ACK',async()=>{
  const {shot,server,acknowledged}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));
  const replay=f.replay(()=>authoredZeroReplay(f));f.adapter.restore(plain(server));
  f.event('replayBtn','click',{target:replay});await f.flush();await f.ack();
  const persisted=plain(f.window.miraActivityCheckpoint.capture()),again=fixture('math-zero',1);again.set(persisted);
  const againReplay=again.replay(()=>authoredZeroReplay(again));
  again.adapter.restore(plain(acknowledged));assert.equal(again.confirmations.at(-1),true);
  assert.deepEqual(again.get(),persisted);assert.equal(again.window.miraActivityCheckpoint.capture(),null);
  assert.deepEqual(again.restoredSnapshots,[]);assert.deepEqual(again.sent,[]);
  again.event('replayBtn','click',{target:againReplay});await again.flush();assert.equal(again.window.miraActivityCheckpoint.capture(),null);
  await again.ack();assert.equal(again.window.miraActivityCheckpoint.capture().help.replay,3);
});
test('zero p1 does not release a pending recovery merely because an unrelated server replay appears',async()=>{
  const {shot,server,acknowledged}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));
  const replay=f.replay(()=>authoredZeroReplay(f));f.adapter.restore(plain(server));
  f.event('replayBtn','click',{target:replay});await f.flush();f.adapter.restore(plain(acknowledged));
  assert.equal(f.confirmations.at(-1),true);await f.ack();
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.equal(f.event('number-0'),true);
});
test('zero p1 rejects changed snapshot or server evidence and never applies the lock across hashes',()=>{
  const mutations=[(shot)=>{shot.help.replay=2;},(shot)=>{shot.work.answer=0;},
    (shot)=>{shot.history=[];},(shot)=>{shot.teacherDemo='one-left';},
    (_shot,server)=>{server.support.hint=1;},(_shot,server)=>{server.history=[{name:'replay'}];},
    (_shot,server)=>{server.attempts=[{correct:true}];},(_shot,server)=>{server.completed=true;}];
  for(const mutate of mutations){const {shot,server}=interruptedZeroOne(),f=fixture('math-zero',1);
    const s=plain(shot),v=plain(server);mutate(s,v);f.set(s);f.replay(()=>{});f.adapter.restore(v);
    assert.equal(f.confirmations.at(-1),false);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
    assert.deepEqual(f.sent,[]);assert.deepEqual(f.restoredSnapshots,[]);
  }
  for(const hash of [null,'f'.repeat(64)]){const {shot,server}=interruptedZeroOne(),f=fixture('math-zero',1,hash);
    f.set(plain(shot));f.replay(()=>{});f.adapter.restore(server);assert.equal(f.confirmations.at(-1),false);
    assert.equal(f.statusNodes.length,0);assert.deepEqual(f.sent,[]);
  }
  const missing=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(missing.shot));
  f.adapter.restore(missing.server);assert.equal(f.confirmations.at(-1),false);
});
test('zero p1 validates replay-only history even when the server already has a replay',()=>{
  const changes=[(s)=>{s.history=[];},s=>{s.help.replay=0;},s=>{s.history[0].version=2;},
    s=>{s.selected=1;},s=>{s.currentCue='other';},s=>{s.firstAttempts.task={};}];
  for(const change of changes){const {shot,acknowledged}=interruptedZeroOne(),f=fixture('math-zero',1);
    const s=plain(shot);change(s);f.set(s);f.replay(()=>{});f.adapter.restore(plain(acknowledged));
    assert.equal(f.confirmations.at(-1),false);assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.deepEqual(f.sent,[]);
  }
  const {shot,acknowledged}=interruptedZeroOne(),f=fixture('math-zero',1);f.set({...plain(shot),audioStatus:'playing'});
  f.replay(()=>{});f.adapter.restore(plain(acknowledged));assert.equal(f.confirmations.at(-1),true);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.equal(f.event('number-0'),true);assert.deepEqual(f.sent,[]);
});
test('zero p1 rolls back unacknowledged replay and seals both snapshot and input through handoff',async()=>{
  const {shot,server}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));
  const replay=f.replay(()=>authoredZeroReplay(f));f.adapter.restore(plain(server));
  f.event('replayBtn','click',{target:replay});await f.flush();f.window.miraCourseOperation.ready=false;f.adapter.dispose();
  assert.deepEqual(f.checkpoint.capture(),shot);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  await f.reject();
  assert.equal(f.event('number-0'),true);assert.equal(f.event('replayBtn','click',{target:replay,isTrusted:false}),true);
  assert.equal(f.message({type:'MIRA_INTERACTIVE_AUDIO_CONTROL',command:'play',channel:'channel1'}),true);
  const next=f.window.installMathSubtractZeroCourseAdapter('scene-p1','math-zero',hashes['math-zero'][1]);
  next.restore(plain(server));assert.equal(f.confirmations.at(-1),true);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  assert.equal(f.event('number-0'),true);assert.equal(f.event('replayBtn','click',{target:replay}),true);
  f.window.miraCourseOperation.ready=true;assert.equal(f.event('number-0'),true);
  f.event('replayBtn','click',{target:replay});await f.flush();await f.ack();
  assert.equal(f.window.miraActivityCheckpoint.capture().help.replay,2);
});
test('failed rollback and unverified general work remain sealed through reconnect',async()=>{
  const {shot,server}=interruptedZeroOne(),f=fixture('math-zero',1);f.set(plain(shot));
  const replay=f.replay(()=>authoredZeroReplay(f));f.adapter.restore(plain(server));
  f.event('replayBtn','click',{target:replay});await f.flush();f.restorer(()=>false);
  f.window.miraCourseOperation.ready=false;f.adapter.dispose();assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  const next=f.window.installMathSubtractZeroCourseAdapter('scene-p1','math-zero',hashes['math-zero'][1]);next.restore(plain(server));
  assert.equal(f.confirmations.at(-1),false);f.window.miraCourseOperation.ready=true;
  assert.equal(f.event('replayBtn','click',{target:replay}),true);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  const g=fixture('math-zero',2);g.restore();g.get().phase='playing';g.event('meaning-origin');
  g.get().work.meaning='origin';await g.flush();g.window.miraCourseOperation.ready=false;g.adapter.dispose();
  assert.equal(g.window.miraActivityCheckpoint.capture(),null);assert.equal(g.event('meaning-empty'),true);
  const nextPage=g.window.installMathSubtractZeroCourseAdapter('scene-p2','math-zero',hashes['math-zero'][2]);
  nextPage.restore({kind:'math-zero',validator:'math-zero-p2.v1',lastWork:null});
  assert.equal(g.confirmations.at(-1),false);g.window.miraCourseOperation.ready=true;
  assert.equal(g.event('meaning-empty'),true);assert.equal(g.window.miraActivityCheckpoint.capture(),null);
});
test('p2 recovers only an acknowledged answer revision and preserves the first attempt and support',async()=>{
  const {shot,server}=interruptedSubtractTwo(),f=fixture('math-subtract',2);f.set(plain(shot));
  f.adapter.restore(plain(server));assert.equal(f.confirmations.at(-1),true);assert.equal(f.restoredSnapshots.length,1);
  const recovered=f.get();
  assert.deepEqual(recovered.domainState,{removed:[1],remaining:[2,3,4],answer:3,checked:false});
  assert.equal(recovered.currentWorkVersion,4);assert.deepEqual(recovered.firstAttempt,shot.firstAttempt);
  assert.deepEqual(recovered.helpFlags,shot.helpFlags);
  assert.deepEqual(recovered.revisionHistory,[...shot.revisionHistory,{version:4,action:'answer',details:{answer:3}}]);
  assert.equal(recovered.phase,'playing');assert.deepEqual(f.sent,[]);
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);
  // Re-entry of the same verified world does not reconstruct it twice.
  f.adapter.restore(plain(server));assert.equal(f.confirmations.at(-1),true);assert.equal(f.restoredSnapshots.length,1);
  assert.deepEqual(f.sent,[]);
  // A later actual check, not reconstruction, creates the next submit.
  f.event('check');f.get().domainState.checked=true;await f.flush();
  assert.deepEqual(f.sent,[{name:'submit',work:{removed:[1],remaining:[2,3,4],answer:3}}]);
});
test('p2 recovery supports other pictures and answers with actual hint and replay history',()=>{
  const initialWork={removed:[],remaining:[1,2,3,4],answer:null};
  const moved={removed:[4],remaining:[1,2,3],answer:null};
  const first={removed:[4],remaining:[1,2,3],answer:1},after={...first,answer:2};
  const zero={hint:0,replay:1,demonstration:0},helped={hint:1,replay:1,demonstration:0},later={hint:1,replay:2,demonstration:0};
  const entry=(name,workVersion,work,support)=>({name,task:'task',workVersion,work,support});
  const attempt={task:'task',work:first,correct:false,workVersion:3,support:helped,retryCount:0,undoCount:0,
    priorAttempts:0,priorPageAttempts:0,priorReveals:0,pictureSupport:true,assistanceOutsideApp:'unobserved'};
  const server={kind:'math-subtract',validator:'math-subtract-p2.v1',phase:'playing',completed:false,lastWork:after,
    workVersion:4,attempts:[attempt],firstAttempts:{task:attempt},firstPredictions:{},latestPredictions:{},
    passedTasks:[],support:later,undoCount:0,retryCount:0,exposureCount:0,
    history:[entry('replay',1,initialWork,zero),entry('hint',1,initialWork,helped),entry('work',2,moved,helped),
      entry('work',3,first,helped),entry('submit',3,first,helped),entry('replay',3,first,later),entry('work',4,after,later)]};
  const shot={version:1,sceneId:'scene-p2',phase:'playing',prediction:null,instructionsComplete:true,stableObjectIds:[1,2,3,4],
    domainState:{...first,checked:true},firstAttempt:{...first,helped:true},helpFlags:{hint:true},currentWorkVersion:4,
    revisionHistory:[{version:1,action:'hint',details:{}},{version:2,action:'move',details:{id:4}},
      {version:3,action:'answer',details:{answer:1}},{version:4,action:'check',details:{...first,checked:false}}]};
  const f=fixture('math-subtract',2);f.set(plain(shot));f.adapter.restore(plain(server));
  assert.equal(f.confirmations.at(-1),true);assert.deepEqual(f.get().firstAttempt,shot.firstAttempt);
  assert.deepEqual(f.get().helpFlags,{hint:true});assert.deepEqual(f.get().domainState,{...after,checked:false});
  assert.deepEqual(f.get().revisionHistory.at(-1),{version:5,action:'answer',details:{answer:2}});
  assert.deepEqual(f.sent,[]);
});
test('p2 recovery handles changing a formerly correct checked answer without retaining completion',()=>{
  const moved={removed:[2],remaining:[1,3,4],answer:null}, first={...moved,answer:3},after={...moved,answer:4};
  const support={hint:0,replay:0,demonstration:0},entry=(name,workVersion,work)=>({name,task:'task',workVersion,work,support});
  const attempt={task:'task',work:first,correct:true,workVersion:2,support,retryCount:0,undoCount:0,
    priorAttempts:0,priorPageAttempts:0,priorReveals:0,pictureSupport:true,assistanceOutsideApp:'unobserved'};
  const server={kind:'math-subtract',validator:'math-subtract-p2.v1',phase:'playing',completed:false,lastWork:after,
    workVersion:3,attempts:[attempt],firstAttempts:{task:attempt},firstPredictions:{},latestPredictions:{},
    passedTasks:[],support,undoCount:0,retryCount:0,exposureCount:0,
    history:[entry('work',1,moved),entry('work',2,first),entry('submit',2,first),entry('work',3,after)]};
  const shot={version:1,sceneId:'scene-p2',phase:'complete',prediction:null,instructionsComplete:true,stableObjectIds:[1,2,3,4],
    domainState:{...first,checked:true},firstAttempt:{...first,helped:false},helpFlags:{hint:false},currentWorkVersion:3,
    revisionHistory:[{version:1,action:'move',details:{id:2}},{version:2,action:'answer',details:{answer:3}},
      {version:3,action:'check',details:{...first,checked:false}}]};
  const f=fixture('math-subtract',2);f.set(plain(shot));f.adapter.restore(plain(server));
  assert.equal(f.confirmations.at(-1),true);assert.equal(f.get().phase,'playing');
  assert.deepEqual(f.get().domainState,{...after,checked:false});assert.deepEqual(f.get().firstAttempt,shot.firstAttempt);
  assert.deepEqual(f.sent,[]);
});
test('p2 recovery reconstructs confirmed undo and retry without erasing prior history',()=>{
  const empty={removed:[],remaining:[1,2,3,4],answer:null},moved2={removed:[2],remaining:[1,3,4],answer:null};
  const moved4={removed:[4],remaining:[1,2,3],answer:null},ans2={...moved4,answer:2};
  const moved3={removed:[3],remaining:[1,2,4],answer:null},ans4={...moved3,answer:4},ans1={...moved3,answer:1};
  const support={hint:0,replay:0,demonstration:0},entry=(name,workVersion,work)=>({name,task:'task',workVersion,work,support});
  const server={kind:'math-subtract',validator:'math-subtract-p2.v1',phase:'playing',completed:false,lastWork:ans1,
    workVersion:8,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],support,
    undoCount:1,retryCount:1,exposureCount:0,history:[entry('work',1,moved2),entry('undo',2,empty),
      entry('work',3,moved4),entry('work',4,ans2),entry('retry',5,empty),entry('work',6,moved3),
      entry('work',7,ans4),entry('work',8,ans1)]};
  const shot={version:1,sceneId:'scene-p2',phase:'playing',prediction:null,instructionsComplete:true,stableObjectIds:[1,2,3,4],
    domainState:{...ans4,checked:false},firstAttempt:null,helpFlags:{hint:false},currentWorkVersion:7,
    revisionHistory:[{version:1,action:'move',details:{id:2}},{version:2,action:'return',details:{id:2}},
      {version:3,action:'move',details:{id:4}},{version:4,action:'answer',details:{answer:2}},
      {version:5,action:'reset',details:{...ans2,checked:false}},{version:6,action:'move',details:{id:3}},
      {version:7,action:'answer',details:{answer:4}}]};
  const f=fixture('math-subtract',2);f.set(plain(shot));f.adapter.restore(plain(server));
  assert.equal(f.confirmations.at(-1),true);assert.deepEqual(f.get().domainState,{...ans1,checked:false});
  assert.deepEqual(f.get().revisionHistory,[...shot.revisionHistory,{version:8,action:'answer',details:{answer:1}}]);
  assert.deepEqual(f.sent,[]);
});
test('p2 recovery preserves the authored 60-entry history bound',()=>{
  const empty={removed:[],remaining:[1,2,3,4],answer:null},after={...empty,answer:1};
  const history=Array.from({length:63},(_,i)=>({name:'hint',task:'task',workVersion:1,work:empty,
    support:{hint:i+1,replay:0,demonstration:0}}));
  const support={hint:63,replay:0,demonstration:0};
  history.push({name:'work',task:'task',workVersion:2,work:after,support});
  const server={kind:'math-subtract',validator:'math-subtract-p2.v1',phase:'playing',completed:false,lastWork:after,
    workVersion:2,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],support,
    undoCount:0,retryCount:0,exposureCount:0,history};
  const shot={version:1,sceneId:'scene-p2',phase:'playing',prediction:null,instructionsComplete:true,stableObjectIds:[1,2,3,4],
    domainState:{...empty,checked:false},firstAttempt:null,helpFlags:{hint:true},currentWorkVersion:63,
    revisionHistory:Array.from({length:60},(_,i)=>({version:i+4,action:'hint',details:{}}))};
  const f=fixture('math-subtract',2);f.set(plain(shot));f.adapter.restore(plain(server));
  assert.equal(f.confirmations.at(-1),true);assert.equal(f.get().revisionHistory.length,60);
  assert.equal(f.get().revisionHistory[0].version,5);assert.deepEqual(f.get().revisionHistory.at(-1),
    {version:64,action:'answer',details:{answer:1}});assert.deepEqual(f.sent,[]);
});
test('p2 does not confuse a repeated projected answer with the immediately preceding checkpoint',()=>{
  const {shot,server}=interruptedSubtractTwo(), support=plain(server.support), previous=plain(server.history[3].work),latest=plain(server.lastWork);
  server.history.push({name:'work',task:'task',workVersion:5,work:previous,support},
    {name:'work',task:'task',workVersion:6,work:latest,support});server.workVersion=6;
  const f=fixture('math-subtract',2);f.set(plain(shot));f.adapter.restore(plain(server));
  assert.equal(f.confirmations.at(-1),false);assert.deepEqual(f.get(),shot);assert.deepEqual(f.restoredSnapshots,[]);
});
test('p2 rejects missing, changed or forged history and never invents a recovery operation',()=>{
  const changes=[
    (_s,v)=>{delete v.history;}, (_s,v)=>{v.history.pop();},
    (_s,v)=>{v.history[4].name='submit';}, (_s,v)=>{v.history[4].workVersion=3;},
    (_s,v)=>{v.history[3].work.answer=3;}, (_s,v)=>{v.history[0].support.replay=0;},
    (_s,v)=>{v.lastWork.answer=2;}, (_s,v)=>{v.workVersion=5;},
    (_s,v)=>{v.firstAttempts.task.correct=true;}, (_s,v)=>{v.attempts=[];},
    (_s,v)=>{v.support.hint=1;}, (_s,v)=>{v.passedTasks=['task'];},
    (_s,v)=>{v.completed=true;}, (_s,v)=>{v.undoCount=1;},
    (s)=>{s.firstAttempt.answer=3;}, (s)=>{s.helpFlags.hint=true;},
    (s)=>{s.revisionHistory.pop();}, (s)=>{s.domainState.checked=false;},
    (s)=>{s.currentWorkVersion=4;}, (s)=>{s.extra='unexpected';},
  ];
  for(const change of changes){const {shot,server}=interruptedSubtractTwo(),f=fixture('math-subtract',2);
    const s=plain(shot),v=plain(server);change(s,v);f.set(s);const old=plain(s);f.adapter.restore(v);
    assert.equal(f.confirmations.at(-1),false);assert.deepEqual(f.get(),old);
    assert.deepEqual(f.restoredSnapshots,[]);assert.deepEqual(f.sent,[]);
  }
});
test('p2 recovery is restricted to the reviewed content hash and cannot run in another page or course',()=>{
  for(const [kind,page,hash] of [['math-subtract',2,null],['math-subtract',2,'f'.repeat(64)],
    ['math-subtract',3,hashes['math-subtract'][3]],['math-zero',2,hashes['math-zero'][2]]]){
    const {shot,server}=interruptedSubtractTwo(),f=fixture(kind,page,hash);f.set(plain(shot));f.adapter.restore(plain(server));
    assert.equal(f.confirmations.at(-1),false);assert.deepEqual(f.get(),shot);
    assert.deepEqual(f.restoredSnapshots,[]);assert.deepEqual(f.sent,[]);
  }
});
test('p2 refuses a rejected or corrupted authored restore and rolls back the saved checkpoint',()=>{
  for(const mode of ['reject','corrupt']){
    const {shot,server}=interruptedSubtractTwo(),f=fixture('math-subtract',2);f.set(plain(shot));let calls=0;
    f.restorer(value=>{calls++;if(calls===1){if(mode==='reject')return false;
      const altered=plain(value);altered.firstAttempt.answer=3;f.set(altered);return true;}
      f.set(plain(value));return true;});
    f.adapter.restore(plain(server));assert.equal(f.confirmations.at(-1),false);
    assert.deepEqual(f.get(),shot);assert.equal(f.restoredSnapshots.length,2);assert.deepEqual(f.sent,[]);
    assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  }
});
test('verified zero SVG keyboard input runs one existing click handler and records only the real key',async()=>{
  const f=fixture('math-zero',2);f.restore();f.get().phase='playing';
  const target=f.svg('meaning-empty');let calls=0;
  f.sceneClick(event=>{calls++;assert.equal(event.isTrusted,false);f.get().work.meaning='empty';});
  assert.equal(f.event('meaning-empty','keydown',{key:'Enter',target}),true);
  assert.equal(calls,1);assert.equal(f.dispatched.length,1);assert.equal(f.dispatched[0].bubbles,true);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  await f.flush();assert.deepEqual(f.sent,[{name:'work',work:{context:'harbour',objects:[],position:0,meaning:'empty'}}]);
  await f.ack();assert.equal(f.window.miraActivityCheckpoint.capture().work.meaning,'empty');
});
test('SVG key repeat is blocked even when an older browser omits KeyboardEvent.repeat',async()=>{
  const f=fixture('math-zero',2);f.restore();f.get().phase='playing';const target=f.svg('meaning-empty');let calls=0;
  f.sceneClick(()=>{calls++;f.get().work.meaning=calls===1?'empty':'origin';});
  f.event('meaning-empty','keydown',{key:' ',target});await f.flush();await f.ack();
  assert.equal(f.event('meaning-empty','keydown',{key:' ',target,repeat:true}),true);
  assert.equal(f.event('meaning-empty','keydown',{key:' ',target}),true);
  assert.equal(calls,1);assert.equal(f.dispatched.length,1);
  f.keyup(' ',false);assert.equal(f.event('meaning-empty','keydown',{key:' ',target}),true);assert.equal(calls,1);
  f.keyup(' ');assert.equal(f.event('meaning-empty','keydown',{key:' ',target}),true);await f.flush();
  assert.equal(calls,2);assert.equal(f.sent.length,2);assert.equal(f.sent.at(-1).work.meaning,'origin');
});
test('SVG fallback supports legacy event factories and fails closed if none exists',async()=>{
  for(const options of [{noMouseEvent:true},{noMouseEvent:true,legacyGenericOnly:true}]){
    const f=fixture('math-zero',12,hashes['math-zero'][12],options);f.restore();f.get().phase='playing';let calls=0;
    f.sceneClick(()=>{calls++;f.get().work.meaning='empty';});const target=f.svg('meaning-empty');
    assert.equal(f.event('meaning-empty','keydown',{key:'Enter',target}),true);await f.flush();
    assert.equal(calls,1);assert.equal(f.dispatched[0].isTrusted,false);assert.equal(f.sent.length,1);
  }
  const f=fixture('math-zero',2,hashes['math-zero'][2],{noMouseEvent:true,noLegacyEvent:true});
  f.restore();f.get().phase='playing';let calls=0;f.sceneClick(()=>{calls++;});const target=f.svg('meaning-empty');
  assert.equal(f.event('meaning-empty','keydown',{key:'Enter',target}),true);assert.equal(calls,0);
  // Pointer input remains on the original path even without event constructors.
  assert.equal(f.event('meaning-empty','click',{target}),false);assert.equal(calls,1);
});
test('SVG keyboard fallback blocks synthetic keys, unavailable permission, disabled targets and unaligned recovery',()=>{
  for(const mode of ['synthetic','not_ready','not_aligned','disabled','outside']){
    const f=fixture('math-zero',2);f.restore();f.get().phase='playing';let calls=0;
    f.sceneClick(()=>calls++);const target=f.svg('meaning-empty',mode==='disabled'?{attributes:{'aria-disabled':'true'}}:
      mode==='outside'?{inScene:false}:{});
    if(mode==='not_ready')f.window.miraCourseOperation.ready=false;
    if(mode==='not_aligned')f.restore({context:'ruler',objects:[1],position:0,meaning:'origin'});
    const blocked=f.event('meaning-empty','keydown',{key:'Enter',target,isTrusted:mode!=='synthetic'});
    if(['not_ready','not_aligned','disabled'].includes(mode))assert.equal(blocked,true,mode);
    assert.equal(calls,0,mode);assert.equal(f.dispatched.length,0,mode);assert.deepEqual(f.sent,[],mode);
  }
});
test('SVG keyboard fallback stays scoped to reviewed pages and preserves a native SVG click method',async()=>{
  for(const [kind,page,hash] of [['math-zero',2,'f'.repeat(64)],['math-zero',7,hashes['math-zero'][7]],
    ['math-subtract',2,hashes['math-subtract'][2]]]){
    const f=fixture(kind,page,hash),target=f.svg('meaning-empty');let calls=0;f.sceneClick(()=>calls++);
    f.restore();assert.equal(f.event('meaning-empty','keydown',{key:'Enter',target}),false);
    assert.equal(f.dispatched.length,0);assert.equal(calls,0);
  }
  const f=fixture('math-zero',2);f.restore();f.get().phase='playing';const target=f.svg('meaning-empty');
  f.nativeClick(target);let calls=0;f.sceneClick(()=>{calls++;f.get().work.meaning='empty';});
  assert.equal(f.event('meaning-empty','keydown',{key:'Enter',target}),false);
  target.click();await f.flush();assert.equal(calls,1);assert.equal(f.sent.length,1);
  assert.equal(f.event('meaning-empty','keydown',{key:'Enter',target,repeat:true}),true);assert.equal(calls,1);
});
test('fresh reviewed openings run the authored handler once with no synthetic event or learning operation', () => {
  for (const [kind,pages] of [['math-subtract',[2,3,4,5,6,7,8,9,10,11]],
    ['math-zero',[1,2,3,4,5,11,12,13]]]) for (const page of pages) {
    const f=fixture(kind,page); let calls=0, received, receiver;
    const button=f.start(function(...args){calls++;received=args;receiver=this;});
    assert.equal(f.window.miraActivityCheckpoint.beginRequiresSelectedSceneIntent,true);
    assert.equal(Object.isFrozen(f.window.miraActivityCheckpoint),true);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false,kind+' '+page+' before restore');
    f.window.miraCourseOperation.ready=false; f.restore();
    assert.equal(f.confirmations.at(-1),true,kind+' '+page);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false,kind+' '+page+' before authorization');
    f.window.miraCourseOperation.ready=true;
    assert.equal(f.window.miraActivityCheckpoint.begin(),true,kind+' '+page);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false,kind+' '+page+' duplicate');
    assert.equal(calls,1); assert.deepEqual(received,[]); assert.equal(receiver,button);
    assert.deepEqual(f.sent,[]); assert.equal(f.get().firstAttempt ?? null,null);
  }
});
test('zero p3 teacher playing-before-intro uses the exact original start without inventing a response',()=>{
  const f=fixture('math-zero',3);f.get().phase='playing';const before=plain(f.get());let calls=0;
  f.start(()=>{calls++;assert.equal(f.get().phase,'ready');f.get().phase='playing';
    f.get().currentCue='zero-p3-repair-start';f.get().audioStatus='requested';});
  f.window.miraCourseOperation.ready=false;f.restore();assert.equal(f.confirmations.at(-1),true);
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.equal(f.restoredSnapshots.length,0);
  f.window.miraCourseOperation.ready=true;assert.equal(f.window.miraActivityCheckpoint.begin(),true);
  assert.equal(calls,1);assert.equal(f.restoredSnapshots.length,1);assert.deepEqual(f.restoredSnapshots[0],{...before,phase:'ready'});
  assert.equal(f.get().phase,'playing');assert.deepEqual(f.get().work,before.work);
  assert.deepEqual(f.get().help,before.help);assert.deepEqual(f.get().history,[]);assert.deepEqual(f.get().attempts,[]);
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(f.sent,[]);
});
test('zero p3 may start the pristine restored hidden world only after the private selected-page gate',()=>{
  for(const status of ['hidden','idle']){
    const f=fixture('math-zero',3),saved=initial(3,'math-zero');saved.phase='playing';saved.audioStatus=status;
    let calls=0;f.start(()=>{calls++;assert.equal(f.get().phase,'ready');f.get().phase='playing';
      f.get().currentCue='zero-p3-repair-start';f.get().audioStatus='requested';});
    const guarded=f.window.miraActivityCheckpoint;
    assert.equal(guarded.beginRequiresSelectedSceneIntent,true);
    assert.equal(guarded.beginMayResumeSelectedSceneIntent,true);
    assert.equal(guarded.restore(saved),true);f.window.miraCourseOperation.ready=false;f.restore();
    assert.equal(guarded.begin(),false);assert.equal(calls,0);
    f.window.miraCourseOperation.ready=true;assert.equal(guarded.begin(),true);
    assert.equal(guarded.begin(),false);assert.equal(calls,1);
    assert.deepEqual(f.restoredSnapshots[1],{...saved,phase:'ready'});
    assert.deepEqual(f.get().work,saved.work);assert.deepEqual(f.get().history,[]);
    assert.deepEqual(f.get().attempts,[]);assert.deepEqual(f.get().help,saved.help);assert.deepEqual(f.sent,[]);
  }
  assert.equal(fixture('math-zero',3,'f'.repeat(64)).window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,undefined);
  assert.equal(fixture('math-zero',2).window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,true);
  assert.equal(fixture('math-subtract',3).window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,true);
});
test('zero p3 rejects a restored opening when server evidence is missing, changed or noninitial',()=>{
  const changes=[s=>{s.support.replay=1;},s=>{s.support.hint=1;},s=>{s.support.demonstration=1;},
    s=>{s.history.push({name:'replay'});},s=>{s.attempts.push({});},s=>{s.firstAttempts.task={};},
    s=>{s.lastWork=initial(3,'math-zero').work;},s=>{s.workVersion=1;},s=>{s.completed=true;},
    s=>{s.passedTasks.push('task');},s=>{s.undoCount=1;},s=>{s.firstPredictions.task={};},
    s=>{delete s.support;},s=>{s.extra='unexpected';}];
  for(const change of changes){
    const f=fixture('math-zero',3),saved=initial(3,'math-zero'),server=initialZeroThreeServer();
    saved.phase='playing';saved.audioStatus='hidden';change(server);let calls=0;f.start(()=>calls++);
    f.window.miraActivityCheckpoint.restore(saved);f.adapter.restore(server);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.equal(calls,0);
    assert.deepEqual(f.get(),saved);assert.deepEqual(f.sent,[]);
  }
});
test('zero p3 never rearms a selected intro after real input or altered restored evidence',()=>{
  const f=fixture('math-zero',3),saved=initial(3,'math-zero');saved.phase='playing';saved.audioStatus='hidden';
  let calls=0;f.start(()=>calls++);f.window.miraActivityCheckpoint.restore(saved);f.restore();
  f.event('unknown','pointerdown');f.window.miraActivityCheckpoint.restore(saved);f.restore();
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.equal(calls,0);assert.deepEqual(f.sent,[]);
  for(const change of [s=>{s.help.replay=1;},s=>{s.history.push({name:'replay'});},
    s=>{s.attempts.push({});},s=>{s.currentCue='zero-p3-repair-start';},s=>{s.audioStatus='ready';},
    s=>{s.work.order=[0,1,2,3,4,5];},s=>{s.extra=true;}]){
    const g=fixture('math-zero',3),shot=plain(saved);change(shot);g.start(()=>calls++);
    g.window.miraActivityCheckpoint.restore(shot);g.restore();
    assert.equal(g.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(g.sent,[]);
  }
});
test('zero p3 teacher phase fix rejects altered history, help, selection, cue, work or user input',()=>{
  const changes=[s=>{s.help.replay=1;},s=>{s.help.hint=1;},s=>{s.history.push({name:'replay'});},
    s=>{s.currentCue='zero-p3-repair-start';},s=>{s.audioStatus='ready';},s=>{s.selected=0;},
    s=>{s.firstAttempts.task={};},s=>{s.pen=[0.4,0.1];},s=>{s.work.order=[0,1,2,3,4,5];}];
  for(const change of changes){const f=fixture('math-zero',3);f.get().phase='playing';change(f.get());
    let calls=0;f.start(()=>calls++);f.restore();assert.equal(f.window.miraActivityCheckpoint.begin(),false);
    assert.equal(calls,0);assert.deepEqual(f.restoredSnapshots,[]);assert.deepEqual(f.sent,[]);
  }
  const f=fixture('math-zero',3);f.get().phase='playing';f.start(()=>{});f.restore();f.event('unknown','pointerdown');
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(f.restoredSnapshots,[]);
  const wrong=fixture('math-zero',3,'f'.repeat(64));assert.equal(wrong.window.miraActivityCheckpoint.begin,undefined);
});
test('zero p3 restores the prior world if its ready reset or start control cannot be verified',()=>{
  const f=fixture('math-zero',3);f.get().phase='playing';const before=plain(f.get());f.restore();
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(f.get(),before);
  assert.equal(f.restoredSnapshots.length,2);assert.deepEqual(f.sent,[]);
  const bad=fixture('math-zero',3);bad.get().phase='playing';const old=plain(bad.get());bad.start(()=>{});
  let calls=0;bad.restorer(value=>{calls++;const x=plain(value);if(calls===1)x.selected=0;bad.set(x);return true;});
  bad.restore();assert.equal(bad.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(bad.get(),old);
  assert.deepEqual(bad.sent,[]);
});
test('zero p3 start exceptions roll back even after partial changes and keep the page sealed',()=>{
  for(const partial of [false,true]){
    const f=fixture('math-zero',3);f.get().phase='playing';const before=plain(f.get());
    f.start(()=>{if(partial){f.get().phase='playing';f.get().work.order=[0,1,2,3,4,5];
      f.get().currentCue='zero-p3-repair-start';}throw new Error('start failed');});
    f.restore();assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(f.get(),before);
    assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.ok(f.notices.includes('mira-course-operation-error'));
    assert.equal(f.event('zeroChip','click'),true);assert.deepEqual(f.sent,[]);
  }
  const failed=fixture('math-zero',3);failed.get().phase='playing';failed.start(()=>{throw new Error('start failed');});
  let calls=0;failed.restorer(value=>{calls++;if(calls>1)return false;failed.set(plain(value));return true;});
  failed.restore();assert.equal(failed.window.miraActivityCheckpoint.begin(),false);
  assert.equal(failed.window.miraActivityCheckpoint.capture(),null);assert.equal(failed.event('zeroChip','click'),true);
  assert.deepEqual(failed.sent,[]);
});
test('opening never overrides restored work, genuine input, pending work or an unusable start button', () => {
  const restored=fixture('math-subtract',3); let calls=0; restored.start(()=>calls++);
  const saved={total:4,removed:[1],remaining:[2,3,4],equation:{whole:4,change:1,result:3},
    links:{whole:null,change:null,result:null}};
  restored.restore(saved); assert.equal(restored.confirmations.at(-1),true);
  assert.equal(restored.window.miraActivityCheckpoint.begin(),false);
  const mismatch=fixture('math-subtract',3); mismatch.start(()=>calls++); mismatch.restore({...saved,total:5});
  assert.equal(mismatch.window.miraActivityCheckpoint.begin(),false);
  const touched=fixture('math-subtract',3); touched.start(()=>calls++); touched.restore();
  touched.event('unknown','pointerdown'); assert.equal(touched.window.miraActivityCheckpoint.begin(),false);
  const pending=fixture('math-subtract',3); pending.start(()=>calls++); pending.restore(); pending.event('num-original');
  assert.equal(pending.window.miraActivityCheckpoint.begin(),false);
  const unavailable=fixture('math-zero',1); unavailable.restore();
  assert.equal(unavailable.window.miraActivityCheckpoint.begin(),false);
  const button=unavailable.start(()=>calls++,{disabled:true});
  assert.equal(unavailable.window.miraActivityCheckpoint.begin(),false);
  button.disabled=false; button.hidden=true;
  assert.equal(unavailable.window.miraActivityCheckpoint.begin(),false);
  button.hidden=false; button.onclick=null;
  assert.equal(unavailable.window.miraActivityCheckpoint.begin(),false);
  assert.equal(calls,0); assert.deepEqual(restored.sent,[]); assert.deepEqual(touched.sent,[]);
});
test('opening fails closed when the page changed or was disposed while authorization was pending', () => {
  const changed=fixture('math-zero',1); let calls=0; changed.start(()=>calls++); changed.restore();
  changed.get().history.push({name:'replay'});
  assert.equal(changed.window.miraActivityCheckpoint.begin(),false);
  const spoken=fixture('math-subtract',2); spoken.start(()=>calls++); spoken.restore();
  spoken.get().instructionsComplete=true;
  assert.equal(spoken.window.miraActivityCheckpoint.begin(),false);
  const selected=fixture('math-subtract',3); selected.start(()=>calls++); selected.restore();
  selected.get().domainState.selected='original';
  assert.equal(selected.window.miraActivityCheckpoint.begin(),false);
  const disposed=fixture('math-subtract',3); disposed.start(()=>calls++); disposed.restore();
  const guarded=disposed.window.miraActivityCheckpoint; disposed.adapter.dispose();
  assert.equal(guarded.begin(),false); assert.equal(calls,0);
});
test('source page opens only after its verified fresh story is imported', () => {
  const f=fixture('math-subtract',12), story={total:3,removed:[1],remaining:[2,3],equation:{whole:3,change:1,result:2}};
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p11',available:true,sourceWorkSha256:'a'.repeat(64),saved:story};
  let calls=0; f.start(()=>calls++);
  f.importer(value=>{Object.assign(f.get().domainState,{story:plain(value.saved),saved:plain(value.saved),sourceWorkSha256:value.sourceWorkSha256});return true;});
  f.restore(null,ctx); assert.equal(f.confirmations.at(-1),true);
  assert.equal(f.window.miraActivityCheckpoint.begin(),true); assert.equal(calls,1); assert.deepEqual(f.sent,[]);
  const missing=fixture('math-subtract',12); missing.start(()=>calls++); missing.importer(()=>true);
  missing.restore(null,{...ctx,available:false,sourceWorkSha256:null,saved:null});
  assert.equal(missing.window.miraActivityCheckpoint.begin(),false); assert.equal(calls,1);
});
test('zero pages 6-10 open only their exact initial cue without replay or learning operations', () => {
  for (const page of [6,7,8,9,10]) {
    const f=fixture('math-zero',page), played=[]; f.window.miraNarrate=cue=>played.push(cue); f.restore();
    const before=plain(f.get()); assert.equal(f.window.miraActivityCheckpoint.begin(),true,String(page));
    assert.deepEqual(played,['p'+page+'-a1']); assert.deepEqual(f.get(),before);
    assert.deepEqual(f.sent,[]); assert.equal(f.window.miraActivityCheckpoint.begin(),false);
  }
});
test('zero cue opening rejects earlier support, other cues, prior audio, and pending permission', () => {
  for (const change of [
    f=>{f.get().helpFlags.replay=1;}, f=>{f.get().helpFlags.hint=1;},
    f=>{f.get().uiState.cue='p7-a2';}, f=>{f.get().firstPrediction={value:2};},
    f=>{f.narration({status:'playing',cueId:'p7-a1'});},
    f=>{f.window.miraCourseOperation.ready=false;},
  ]) {
    const f=fixture('math-zero',7); let calls=0; f.window.miraNarrate=()=>calls++; f.restore(); change(f);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false); assert.equal(calls,0); assert.deepEqual(f.sent,[]);
  }
});
test('zero source opening uses only the verified imported or missing cue without support evidence', () => {
  const story={type:'all-left',total:3,operator:'subtract',changed:[1,2,3],remaining:[],equation:{whole:3,change:3,result:0}};
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p13',available:true,sourceWorkSha256:'a'.repeat(64),saved:story};
  const available=fixture('math-zero',14),played=[];
  available.window.miraNarrate=cue=>played.push(cue);
  available.importer(value=>{Object.assign(available.get(),{sourceAvailable:true,phase:'playing',
    currentCue:'zero-p14-repair-instruction',audioStatus:'idle',workVersion:2,
    work:{story:plain(value.saved),saved:plain(value.saved),zeroRole:null,sourceWorkSha256:value.sourceWorkSha256,storyVersion:1,recordVersion:1}});return true;});
  available.restore(null,ctx); assert.equal(available.confirmations.at(-1),true);
  const saved=plain(available.get()); assert.equal(available.window.miraActivityCheckpoint.begin(),true);
  assert.deepEqual(played,['zero-p14-repair-instruction']); assert.deepEqual(available.get(),saved); assert.deepEqual(available.sent,[]);
  const missing=fixture('math-zero',14); missing.window.miraNarrate=cue=>played.push(cue);
  missing.importer(()=>{missing.get().currentCue='zero-p14-repair-missing';return true;});
  missing.restore(null,{...ctx,available:false,sourceWorkSha256:null,saved:null});
  assert.equal(missing.confirmations.at(-1),true); assert.equal(missing.window.miraActivityCheckpoint.begin(),true);
  assert.equal(played.at(-1),'zero-p14-repair-missing'); assert.deepEqual(missing.sent,[]);
  const assisted=fixture('math-zero',14); assisted.window.miraNarrate=cue=>played.push(cue);
  assisted.importer(()=>{assisted.get().currentCue='zero-p14-repair-missing';assisted.get().help.replay=1;return true;});
  assisted.restore(null,{...ctx,available:false,sourceWorkSha256:null,saved:null});
  assert.equal(assisted.window.miraActivityCheckpoint.begin(),false); assert.equal(played.length,2);
});
test('restoring through the wrapped checkpoint disarms an opening even if the snapshot is initially empty', () => {
  const f=fixture('math-subtract',3); let calls=0; f.start(()=>calls++); f.restore();
  assert.equal(f.window.miraActivityCheckpoint.restore(initial(3)),true);
  assert.equal(f.window.miraActivityCheckpoint.begin(),false); assert.equal(calls,0);
});
test('missing or changed hashes preserve the original two-argument operation behavior without opening', async () => {
  for (const hash of [null,'f'.repeat(64),hashes['math-subtract'][2]]) {
    const f=fixture('math-subtract',3,hash);
    assert.equal(f.window.miraActivityCheckpoint.begin,undefined);
    assert.equal(f.window.miraActivityCheckpoint.beginRequiresSelectedSceneIntent,undefined);
    f.restore(); assert.equal(f.confirmations.at(-1),true); f.event('num-original'); await f.flush();
    assert.deepEqual(f.sent,[]);
  }
  const legacy=fixture('math-subtract',3); legacy.restore();legacy.adapter.dispose();
  const a=legacy.window.installMathSubtractZeroCourseAdapter('scene-p3','math-subtract');
  assert.equal(legacy.window.miraActivityCheckpoint.begin,undefined);
  assert.equal(legacy.window.miraActivityCheckpoint.beginRequiresSelectedSceneIntent,undefined);
  a.restore({kind:'math-subtract',validator:'math-subtract-p3.v1',lastWork:null});
  assert.equal(legacy.confirmations.at(-1),true); a.dispose();
});
test('subtraction p1 has no callable opening and never substitutes replay', () => {
  const f=fixture('math-subtract',1); assert.equal(f.window.miraActivityCheckpoint.begin,undefined);
  assert.equal(f.window.miraActivityCheckpoint.beginRequiresSelectedSceneIntent,undefined);
});
test('fresh null prediction stays unanswered; local success cannot fabricate a prediction or success', async () => {
  const f = fixture(); f.restore(); assert.deepEqual(f.confirmations, [true]); assert.deepEqual(f.sent, []);
  f.event('sendTruckBtn'); f.get().phase = 'success'; f.get().completed = true; f.get().passed = true;
  await f.flush();
  assert.deepEqual(f.sent, [{name: 'submit', work: {removed: [], remaining: [1,2,3,4,5], prediction: null}}]);
  await f.reject(); assert.equal(f.window.miraActivityCheckpoint.capture(), null);
  assert.ok(f.notices.includes('mira-course-operation-error'));
});
test('records explicit prediction, actual moved identities and an explicit submit in order', async () => {
  const f = fixture(); f.restore();
  f.event('predPlusBtn'); f.changePrediction(3); await f.flush(); await f.ack();
  f.event('crate_2', 'pointerdown'); assert.equal(f.window.miraActivityCheckpoint.capture(), null);
  f.event('crate_2', 'pointerup'); f.move(2); await f.flush(); await f.ack();
  f.event('crate_5', 'pointerdown'); f.event('crate_5', 'pointerup'); f.move(5); await f.flush(); await f.ack();
  f.event('sendTruckBtn'); f.get().phase = 'success'; await f.flush();
  assert.deepEqual(f.sent.map(op => op.name), ['predict', 'work', 'work', 'submit']);
  assert.deepEqual(f.sent.at(-1).work, {removed: [2,5], remaining: [1,3,4], prediction: 3});
  assert.ok(f.sent.every(op => Object.keys(op.work).join(' ') === 'removed remaining prediction'));
});
test('blocks overlapping input and withholds checkpoints until a real operation acknowledgement', async () => {
  const f = fixture(); f.restore(); f.event('predPlusBtn'); f.changePrediction(1);
  assert.equal(f.window.miraActivityCheckpoint.capture(), null);
  assert.equal(f.event('sendTruckBtn'), true); await f.flush();
  assert.equal(f.window.miraActivityCheckpoint.capture(), null); assert.equal(f.event('crate_1', 'pointerdown'), true);
  await f.ack(); assert.equal(f.window.miraActivityCheckpoint.capture().prediction, 1);
  assert.equal(f.notices.filter(name => name === 'mira-activity-state-changed').length, 1);
});
test('waits through transient captures and never reports a partial move', async () => {
  const f = fixture(); f.restore(); f.event('crate_1', 'pointerdown');
  const settled = f.get(); settled.domainState.crates[0].state = 'truck'; f.set(null);
  f.event('crate_1', 'pointerup'); await f.flush();
  assert.equal(f.sent.length, 0); assert.equal(f.window.miraActivityCheckpoint.capture(), null);
  f.set(settled); await f.flush(); assert.deepEqual(f.sent[0].work.removed, [1]);
});
test('cancelling a drag without moving objects creates no response or stuck checkpoint', async () => {
  const f = fixture(); f.restore(); f.event('crate_1', 'pointerdown');
  assert.equal(f.event('predPlusBtn'), true);
  f.event('crate_1', 'pointercancel'); await f.flush();
  assert.deepEqual(f.sent, []); assert.notEqual(f.window.miraActivityCheckpoint.capture(), null);
});
test('ignores synthetic, disabled and non-domain events; keyboard buttons count only their native click', async () => {
  const f = fixture(); f.restore();
  f.event('predPlusBtn', 'click', {isTrusted: false}); f.event('predPlusBtn', 'click', {disabled: true});
  f.event('unknown'); f.event('predPlusBtn', 'keydown', {key: 'Enter'}); await f.flush();
  assert.deepEqual(f.sent, []);
  f.event('body', 'keydown', {key: '1'}); f.changePrediction(1); await f.flush();
  assert.deepEqual(f.sent, [{name: 'predict', work: {removed: [], remaining: [1,2,3,4,5], prediction: 1}}]);
});
test('replay and hint count real support without resetting work; no demo is inferred from a flag', async () => {
  const f = fixture(); f.restore(); f.event('replayBtn'); f.get().helpFlags.seenDemo = true;
  await f.flush(); await f.ack(); f.event('hintBtn'); await f.flush();
  assert.deepEqual(f.sent.map(op => op.name), ['replay', 'hint']);
  assert.equal(f.sent[0].work.helpFlags, undefined);
});
test('returning a real object records undo and an explicit reset records retry', async () => {
  const f = fixture(); f.move(2); f.changePrediction(3);
  f.restore({removed: [2], remaining: [1,3,4,5], prediction: 3});
  f.event('crate_2', 'keydown', {key: 'Enter'}); f.move(2, 'warehouse'); await f.flush(); await f.ack();
  f.event('resetBtn'); f.set(initial()); await f.flush();
  assert.deepEqual(f.sent.map(op => op.name), ['undo', 'retry']);
});
test('mismatched or malformed restores remain quiet and fail closed', async () => {
  const f = fixture(); f.restore({removed: [1], remaining: [2,3,4,5], prediction: 0});
  assert.equal(f.confirmations.at(-1), false); assert.equal(f.event('sendTruckBtn'), true);
  await f.flush(); assert.equal(f.sent.length, 0); assert.equal(f.window.miraActivityCheckpoint.capture(), null);
  const bad = fixture(); bad.get().domainState.crates[1].id = 'crate_1'; bad.restore();
  assert.equal(bad.confirmations.at(-1), false);
  const old = fixture(); delete old.get().version; old.restore();
  assert.equal(old.confirmations.at(-1), false);
  const defaultAnswer = fixture(); defaultAnswer.changePrediction(0); defaultAnswer.restore();
  assert.equal(defaultAnswer.confirmations.at(-1), false);
});
test('tap-place records only the real truck-zone action and preserves object identities', async () => {
  const f = fixture(); f.restore(); f.event('predPlusBtn'); f.changePrediction(3); await f.flush(); await f.ack();
  f.event('crate_4', 'pointerdown'); f.event('crate_4', 'pointerup'); await f.flush();
  assert.equal(f.sent.length, 1); // Selecting an object has not moved it.
  f.event('truckZone'); f.move(4); await f.flush();
  assert.deepEqual(f.sent.at(-1), {name: 'work', work: {removed: [4], remaining: [1,2,3,5], prediction: 3}});
});
test('an old acknowledgement after dispose cannot publish new checkpoint evidence', async () => {
  const f = fixture(); f.restore(); f.event('predPlusBtn'); f.changePrediction(1); await f.flush();
  f.adapter.dispose(); await f.ack();
  assert.equal(f.window.miraActivityCheckpoint.capture(), null);
  assert.equal(f.notices.filter(name => name === 'mira-activity-state-changed').length, 0);
});
test('a rejected operation from a previous restore cannot disable the newly aligned page', async () => {
  const f = fixture(); f.restore(); f.event('predPlusBtn'); f.changePrediction(1); await f.flush();
  f.restore({removed: [], remaining: [1,2,3,4,5], prediction: 1}); await f.reject();
  assert.equal(f.confirmations.at(-1), true); assert.notEqual(f.window.miraActivityCheckpoint.capture(), null);
  assert.equal(f.notices.includes('mira-course-operation-error'), false);
});
test('unreviewed page projections are explicitly unsupported instead of guessed', () => {
  assert.throws(() => fixture('math-subtract', 13), /math_scene_projection_not_reviewed/);
  assert.throws(() => fixture('math-zero', 15), /math_scene_projection_not_reviewed/);
});
test('zero tail pages restore real worlds, retain incorrect meanings and submit only actual trials or checks',async()=>{
  for(const page of [11,12,13]){const f=fixture('math-zero',page);f.restore();assert.deepEqual(f.confirmations,[true],String(page));assert.deepEqual(f.sent,[]);}
  const f=fixture('math-zero',11);f.restore();f.event('finishReviewBtn');f.get().completed=true;await f.flush();assert.equal(f.sent.length,0);
  f.event('runTrialBtn');Object.assign(f.get().work,{executed:true,equation:{whole:2,change:0,result:2}});await f.flush();await f.ack();
  assert.deepEqual(f.sent.map(x=>x.name),['submit']);
  const p=fixture('math-zero',12);p.restore();p.event('meaning-origin');p.get().work.meaning='origin';await p.flush();await p.ack();p.event('checkBtn');await p.flush();
  assert.equal(p.sent.at(-1).work.meaning,'origin');assert.equal(p.sent.at(-1).name,'submit');
});
test('zero terminal source changes clear only the current pointer and unavailable sources never fabricate a default story',()=>{
  const f=fixture('math-zero',14),story={type:'all-left',total:3,operator:'subtract',changed:[1,2,3],remaining:[],equation:{whole:3,change:3,result:0}};
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p13',available:true,sourceWorkSha256:'a'.repeat(64),saved:story};
  f.importer(value=>{if(value.available&&f.get().work?.sourceWorkSha256!==value.sourceWorkSha256)f.get().work={story:plain(value.saved),saved:plain(value.saved),zeroRole:null,sourceWorkSha256:value.sourceWorkSha256,storyVersion:1,recordVersion:1};return true;});
  f.restore(null,ctx);assert.equal(f.confirmations.at(-1),true);assert.equal(f.sent.length,0);
  f.get().work.zeroRole='result';const saved=plain(f.get().work);f.restore(saved,ctx);assert.equal(f.get().work.zeroRole,'result');assert.equal(f.confirmations.at(-1),true);
  f.restore(saved,{...ctx,sourceWorkSha256:'b'.repeat(64)});assert.equal(f.get().work.zeroRole,null);assert.equal(f.confirmations.at(-1),true);
  f.restore(null,{...ctx,available:false,saved:null,sourceWorkSha256:null});assert.equal(f.confirmations.at(-1),true);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  assert.equal(f.event('replayBtn'),false);assert.equal(f.event('hintBtn'),false);assert.equal(f.event('checkBtn'),true);assert.equal(f.sent.length,0);
});
test('authenticated actual teacher demonstrations count support without changing child work',async()=>{
  const f=fixture('math-zero',1);f.restore();const event={type:'SET_WIDGET_STATE',state:{boats:[{id:'boat1',present:true},{id:'boat2',present:false}]}};
  f.message(event,{});await f.flush();assert.equal(f.sent.length,0);
  f.message(event);f.get().teacherDemo='one-left';await f.flush();await f.ack();
  assert.deepEqual(f.sent,[{name:'demonstration',work:{removed:[],remaining:[1,2],answer:null}}]);
  const p=fixture('math-zero',4);p.restore();p.event('hintBtn');p.get().teacherDemo='zero-trace';await p.flush();await p.ack();await Promise.resolve();
  assert.deepEqual(p.sent.map(x=>x.name),['hint','demonstration']);assert.deepEqual(p.sent.at(-1).work.strokes,[]);
});
test('zero p5 accepts the frozen boat-A through boat-D teacher demonstration only when ready',async()=>{
  const event={type:'SET_WIDGET_STATE',state:{boats:['boat-A','boat-B','boat-C','boat-D'].map((id,i)=>({id,departed:i<2}))}};
  const f=fixture('math-zero',5);f.restore();assert.equal(f.message(event),false);
  f.get().teacherDemo='two-left';await f.flush();await f.ack();
  assert.deepEqual(f.sent.map(x=>x.name),['demonstration']);
  const blocked=fixture('math-zero',5);blocked.restore();blocked.window.miraCourseOperation.ready=false;
  assert.equal(blocked.message(event),true);await blocked.flush();assert.deepEqual(blocked.sent,[]);
});
test('teacher demonstration requires a real parent message and blocks forged MessageEvent.source',async()=>{
  const event={type:'SET_WIDGET_STATE',state:{boats:[{id:'boat1',present:true},{id:'boat2',present:false}]}};
  const f=fixture('math-zero',1);f.restore();
  assert.equal(f.message(event,f.window.parent,false),true);await f.flush();
  assert.equal(f.get().teacherDemo,null);assert.deepEqual(f.sent,[]);
  assert.equal(f.message(event,{},true),false);await f.flush();assert.deepEqual(f.sent,[]);
  assert.equal(f.message(event,f.window.parent,true),false);f.get().teacherDemo='one-left';
  await f.flush();assert.deepEqual(f.sent.map(value=>value.name),['demonstration']);
  const p=fixture('math-zero',3);p.restore();
  assert.equal(p.message({type:'SET_WIDGET_STATE',state:{phase:'playing'}},p.window.parent,false),true);
});
test('private parent replay IDs are retained through ACK and duplicates cannot count twice',async()=>{
  const f=fixture();f.restore();const id='12345678-1234-4123-8123-123456789abc';
  assert.equal(f.adapter.requestParentReplay(id),true);assert.equal(f.adapter.requestParentReplay(id),true);await f.flush();
  assert.deepEqual(plain(f.sendOptions),[{operationId:id}]);assert.equal(f.sent.length,1);
  assert.equal(f.adapter.requestParentReplay(id),true);await f.ack();await f.flush();assert.equal(f.sent.length,1);
  assert.equal(f.adapter.requestParentReplay('not-a-real-request'),false);
});
test('all inspected canonical subtraction pages restore quietly from their real initial state',()=>{
  for(const page of [2,4,6,7,8,9,10,11]){
    const f=fixture('math-subtract',page);f.restore();assert.deepEqual(f.confirmations,[true],String(page));assert.deepEqual(f.sent,[]);
  }
});
test('p2 requires the actual answer choice and explicit check; automatic completion never supplies an answer',async()=>{
  const f=fixture('math-subtract',2);f.restore();
  f.event('piece1','click',{selectors:['[data-object-id]','button']});Object.assign(f.get().domainState,{removed:[1],remaining:[2,3,4]});
  await f.flush();await f.ack();f.event('check');f.get().completed=true;await f.flush();assert.equal(f.sent.length,1);
  f.event('answer2');f.get().domainState.answer=2;await f.flush();await f.ack();f.event('check');await f.flush();
  assert.deepEqual(f.sent.map(x=>x.name),['work','work','submit']);assert.equal(f.sent.at(-1).work.answer,2);
});
test('p4 trace holds checkpoints throughout a real pointer path; point mode never invents ink',async()=>{
  const f=fixture('math-subtract',4);f.restore();f.event('pad','pointerdown');
  f.get().domainState.strokes=[[[.2,.4],[.3,.4]]];assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  f.event('pad','pointerup');Object.assign(f.get().domainState,{strokes:[[[.2,.4],[.7,.4]]],symbol:'subtract'});
  await f.flush();await f.ack();f.event('pointMinus');Object.assign(f.get().domainState,{mode:'point',strokes:[]});await f.flush();
  assert.deepEqual(f.sent[0].work.strokes,[[[.2,.4],[.7,.4]]]);assert.deepEqual(f.sent[1].work.strokes,[]);
});
test('p6 records actual evidence and numeric edits rather than accepting the default result as independent calculation',async()=>{
  const f=fixture('math-subtract',6);f.restore();f.event('evidence-removed');f.get().domainState.evidence='removed';await f.flush();await f.ack();
  f.event('value5');f.get().domainState.equation.whole=5;await f.flush();await f.ack();f.event('check');await f.flush();
  assert.deepEqual(f.sent.at(-1),{name:'submit',work:{removed:[1,2],remaining:[3,4,5],equation:{whole:5,change:2,result:3},evidence:'removed'}});
});
test('p7 submits only a real completed counting path, keeping remaining count and countdown distinct',async()=>{
  const f=fixture('math-subtract',7);f.restore();
  for(const id of [2,1,3]){f.event('piece'+id,'click',{selectors:['[data-object-id]','button']});f.get().domainState.counted.push(id);f.get().domainState.answer=f.get().domainState.counted.length;await f.flush();await f.ack();}
  assert.deepEqual(f.sent.map(x=>x.name),['work','work','submit']);
  f.event('backMethod');Object.assign(f.get().domainState,{method:'count-back',countdown:[4],answer:null});await f.flush();await f.ack();
  f.event('depart');Object.assign(f.get().domainState,{countdown:[4,3],answer:3});await f.flush();
  assert.equal(f.sent.at(-1).name,'submit');assert.deepEqual(f.sent.at(-1).work.countdown,[4,3]);
});
test('p9 keeps explicit predictions separate from object motion and submits actual A/B worlds',async()=>{
  const f=fixture('math-subtract',9);f.restore();f.event('predictB');f.get().prediction=f.get().domainState.prediction='B';await f.flush();await f.ack();
  f.event('pieceA1','click',{selectors:['[data-object-id]','button']});Object.assign(f.get().domainState,{removedA:[1],remainingA:[2,3,4,5]});await f.flush();await f.ack();
  f.event('pieceB3','click',{selectors:['[data-object-id]','button']});Object.assign(f.get().domainState,{removedB:[1,2,3],remainingB:[4,5]});await f.flush();await f.ack();
  f.event('check');await f.flush();assert.deepEqual(f.sent.map(x=>x.name),['predict','work','work','submit']);assert.equal(f.sent.at(-1).work.prediction,'B');
});
test('p11 save is an actual response and p12 consumes only authenticated previous saved work',async()=>{
  const f=fixture('math-subtract',11);f.restore();f.event('save');await f.flush();assert.equal(f.sent.length,0);
  f.event('piece1','click',{selectors:['[data-object-id]','button']});Object.assign(f.get().domainState.story,{removed:[1],remaining:[2,3],equation:{whole:3,change:1,result:2}});await f.flush();await f.ack();
  f.event('save');f.get().domainState.saved=plain(f.get().domainState.story);await f.flush();assert.equal(f.sent.at(-1).name,'submit');
  const story=plain(f.get().domainState.story),ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p11',available:true,sourceWorkSha256:'a'.repeat(64),saved:story};
  const p=fixture('math-subtract',12);p.importer(value=>{if(p.get().domainState.sourceWorkSha256!==value.sourceWorkSha256)Object.assign(p.get().domainState,{story:plain(value.saved),saved:plain(value.saved),sourceWorkSha256:value.sourceWorkSha256,links:{whole:null,change:null,result:null}});return true;});
  p.restore(null,ctx);assert.deepEqual(p.confirmations,[true]);assert.deepEqual(p.sent,[]);
  p.event('zone-before');p.get().domainState.links.whole='before';await p.flush();await p.ack();
  const restored=plain(p.sent.at(-1).work);p.restore(restored,ctx);assert.equal(p.confirmations.at(-1),true);assert.equal(p.get().domainState.links.whole,'before');
  p.restore(restored,{...ctx,sourceSceneId:'scene-p99'});assert.equal(p.confirmations.at(-1),false);
});
test('all zero prediction and empty-operation pages restore without guessing or submitting',()=>{
  for(const page of [6,7,8,9,10]){const f=fixture('math-zero',page);f.restore();assert.deepEqual(f.confirmations,[true],String(page));assert.deepEqual(f.sent,[]);}
});
test('zero p7 gate observes work; only the explicit check submits and later prediction correction remains predict',async()=>{
  const f=fixture('math-zero',7);f.restore();f.event('predict-4','click',{selectors:['[data-predict]']});f.get().prediction=f.get().domainState.work.prediction=4;await f.flush();await f.ack();
  f.event('gate-click-zone','keydown',{key:'Enter'});f.get().domainState.work.gateOpen=true;await f.flush();await f.ack();
  f.event('continue-btn');await f.flush();await f.ack();f.event('predict-3','click',{selectors:['[data-predict]']});f.get().prediction=f.get().domainState.work.prediction=3;await f.flush();
  assert.deepEqual(f.sent.map(x=>x.name),['predict','work','submit','predict']);
});
test('zero equation tasks require actual event, result choice and explicit checks; p9 operator is independently chosen',async()=>{
  for(const page of [8,9,10]){
    const f=fixture('math-zero',page);f.restore();const w=f.get().domainState.work;
    f.event(page===8?'executeRequestBtn':page===10?'arrivalGateBtn':'execute','click',{selectors:page===9?['.execute-context']:[]});w.executed=true;await f.flush();await f.ack();
    f.event('result-1','click',{selectors:['.result-choice']});w.equation.result=1;await f.flush();await f.ack();
    f.event('checkRecordBtn');await f.flush();
    if(page===9){assert.equal(f.sent.length,2);f.event('plus','click',{selectors:['.symbol-token']});f.get().domainState.operatorChosen=true;await f.flush();f.event('checkRecordBtn');await f.flush();}
    assert.equal(f.sent.at(-1).name,'submit');assert.equal(f.sent.at(-1).work.equation.result,1);
  }
});
test('zero keyboard pen keeps one gesture pending until the actual pen-up and rejects synthetic key points',async()=>{
  const f=fixture('math-zero',4);f.restore();f.event('inkSurface','keydown',{key:' '});const s=f.get();f.set(null);
  assert.equal(f.event('inkSurface','keydown',{key:'ArrowRight'}),false);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  assert.equal(f.event('inkSurface','keydown',{key:'ArrowRight',isTrusted:false}),true);
  f.event('inkSurface','keydown',{key:' '});s.work.strokes=[[[.2,.2],[.22,.2],[.24,.2]]];f.set(s);await f.flush();
  assert.deepEqual(f.sent,[{name:'work',work:s.work}]);
});
test('p3 saves actual connections; only a fully specified response is submitted', async () => {
  const f = fixture('math-subtract', 3); f.restore();
  assert.deepEqual(f.confirmations, [true]); assert.equal(f.sent.length, 0);
  f.event('num-original'); f.get().domainState.selected = 'original'; await f.flush();
  assert.equal(f.sent.length, 0);
  for (const [role, zone] of [['original', 'remaining'], ['removed', 'removed'], ['remaining', 'original']]) {
    f.event('zone-' + zone); f.get().domainState.connections[role] = zone;
    f.get().domainState.selected = null; f.get().completed = true;
    await f.flush(); await f.ack();
  }
  assert.deepEqual(f.sent.map(op => op.name), ['work', 'work', 'submit']);
  assert.deepEqual(f.sent.at(-1).work, {total: 4, removed: [1], remaining: [2,3,4],
    equation: {whole: 4, change: 1, result: 3},
    links: {whole: 'remaining', change: 'removed', result: 'before'}});
});
test('p3 restores quietly and rejects unknown connections or changed object identities', () => {
  const f = fixture('math-subtract', 3); f.get().domainState.connections.original = 'original';
  f.restore({total: 4, removed: [1], remaining: [2,3,4], equation: {whole: 4, change: 1, result: 3},
    links: {whole: 'before', change: null, result: null}});
  assert.equal(f.confirmations.at(-1), true); assert.equal(f.sent.length, 0);
  f.get().domainState.connections.original = 'correct'; f.restore();
  assert.equal(f.confirmations.at(-1), false);
  const swapped = fixture('math-subtract', 3); swapped.get().stableObjectIds[0] = 'made-up'; swapped.restore();
  assert.equal(swapped.confirmations.at(-1), false);
});
test('p5 projects real removed IDs and visible system row pairs; completion requires the actual check', async () => {
  const f = fixture('math-subtract', 5); f.restore();
  for (const id of ['L2','L5']) {
    f.event('tool-' + id); const d = f.get().domainState;
    d.leftItems = d.leftItems.filter(value => value !== id); d.removedLeft.push(id);
    d.pairs = d.leftItems.slice(0,3).map((left,i) => [left, 'R' + (i+1)]);
    f.get().completed = true; await f.flush(); await f.ack();
  }
  assert.deepEqual(f.sent.map(op => op.name), ['work','work']);
  f.event('check'); f.get().domainState.checked = 'equal'; await f.flush();
  assert.deepEqual(f.sent.at(-1), {name: 'submit', work: {removed: [2,5], remaining: [1,3,4],
    pairs: [[1,1],[3,2],[4,3]]}});
});
test('p5 never reconstructs missing pairs from an equal/completed flag', () => {
  const f = fixture('math-subtract', 5); f.get().domainState.pairs = undefined;
  f.get().completed = true; f.get().domainState.checked = 'equal'; f.restore();
  assert.equal(f.confirmations.at(-1), false); assert.equal(f.sent.length, 0);
});
test('zero pages restore their actual initial works without any response or invented answer', () => {
  for (let page=1;page<=5;page++) {
    const f=fixture('math-zero',page); f.restore();
    assert.deepEqual(f.confirmations,[true],String(page)); assert.equal(f.sent.length,0);
  }
});
test('zero p1 captures a drag ending on the SVG capture owner, then an explicit answer and check', async () => {
  const f=fixture('math-zero',1); f.restore(); f.get().phase='playing';
  f.event('boat-1','pointerdown'); const settled=plain(f.get()); f.set(null);
  f.event('scene','pointerup'); await f.flush(); assert.equal(f.sent.length,0);
  settled.work={removed:[1],remaining:[2],answer:null}; f.set(settled); await f.flush(); await f.ack();
  f.event('zone-removed'); f.get().work={removed:[1,2],remaining:[],answer:null}; await f.flush(); await f.ack();
  f.event('number-0'); f.get().work.answer=0; await f.flush(); await f.ack();
  f.event('checkBtn'); f.get().phase='complete'; await f.flush();
  assert.deepEqual(f.sent.map(op=>op.name),['work','work','work','submit']);
  assert.deepEqual(f.sent.at(-1).work,{removed:[1,2],remaining:[],answer:0});
});
test('zero SVG keyboard input is attributed to the real key, not its synthetic click', async () => {
  const f=fixture('math-zero',2); f.restore(); f.get().phase='playing';
  f.event('meaning-origin','keydown',{key:'Enter'});
  f.event('meaning-origin','click',{isTrusted:false}); f.get().work.meaning='origin';
  await f.flush(); await f.ack(); f.event('checkBtn'); await f.flush();
  assert.deepEqual(f.sent.map(op=>op.name),['work','submit']);
  assert.equal(f.sent.at(-1).work.meaning,'origin');
});
test('zero p4 records only actual normalized points and distinct trace/free attempts', async () => {
  const f=fixture('math-zero',4); f.restore(); f.get().phase='playing';
  f.event('inkSurface','pointerdown'); const settled=plain(f.get()); f.set(null);
  f.event('scene','pointerup'); await f.flush();
  const actualStroke=[[[.5,.1],[.3,.5],[.5,.9],[.7,.5],[.5,.1]]]; settled.work.strokes=plain(actualStroke); f.set(settled);
  await f.flush(); await f.ack(); f.event('checkBtn'); await f.flush(); await f.ack();
  f.event('nextStepBtn'); f.get().work={mode:'free',strokes:[]}; await f.flush();
  assert.deepEqual(f.sent.map(op=>op.name),['work','submit','work']);
  assert.deepEqual(f.sent[1].work.strokes,actualStroke);
  assert.deepEqual(f.sent.at(-1).work,{mode:'free',strokes:[]});
});
test('zero p5 preserves number-choice work and only submits the later equation check', async () => {
  const f=fixture('math-zero',5); f.get().phase='playing';
  f.get().work={removed:[1,2,3,4],remaining:[],equation:{whole:null,change:null,result:0},links:{whole:null,change:null,result:null}};
  f.restore(plain(f.get().work)); f.event('checkBtn'); f.get().phase='linking'; await f.flush();
  assert.equal(f.sent.length,0);
  f.event('zone-before'); f.get().work.equation.whole=4; f.get().work.links.whole='before'; await f.flush(); await f.ack();
  f.event('zone-removed'); f.get().work.equation.change=4; f.get().work.links.change='removed'; await f.flush(); await f.ack();
  f.event('zone-remaining'); f.get().work.links.result='remaining'; await f.flush(); await f.ack();
  f.event('checkBtn'); await f.flush(); assert.equal(f.sent.at(-1).name,'submit');
});
test('parent replay requests queue behind in-flight work without waiting to authorize playback', async () => {
  const f=fixture(); f.restore(); f.event('predPlusBtn'); f.changePrediction(2); await f.flush();
  assert.equal(f.adapter.requestParentReplay(),true);
  assert.deepEqual(f.sent.map(op=>op.name),['predict']);
  await f.ack(); await f.flush();
  assert.deepEqual(f.sent.map(op=>op.name),['predict','replay']);
  assert.equal(f.sent[1].work.prediction,2);
  assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  await f.ack(); assert.notEqual(f.window.miraActivityCheckpoint.capture(),null);
  assert.equal(f.sent[1].work.audioStatus,undefined);
});
test('parent replay during a drag waits for the actual settled work without capturing intermediate state', async () => {
  const f=fixture('math-zero',1); f.restore(); f.get().phase='playing';
  f.event('boat-1','pointerdown'); const settled=plain(f.get()); f.set(null);
  assert.equal(f.adapter.requestParentReplay(),true); await f.flush(); assert.equal(f.sent.length,0);
  f.event('scene','pointerup'); settled.work={removed:[1],remaining:[2],answer:null}; f.set(settled);
  await f.flush(); await f.ack(); await f.flush();
  assert.deepEqual(f.sent.map(op=>op.name),['work','replay']);
  assert.deepEqual(f.sent[1].work,settled.work);
});


function zeroFourPlaying() {
  return {version:1,page:4,phase:'playing',work:{mode:'trace',strokes:[]},selected:null,activeRole:'whole',answer:null,
    firstAttempts:{},attempts:[],help:{replay:0,hint:0,demonstration:0},history:[],workVersion:1,
    completedContexts:[],tracePassed:false,traceWork:null,currentCue:'zero-p4-repair-trace',audioStatus:'playing',
    pen:[0.5,0.1],penDown:false,teacherDemo:null};
}
function zeroFourServer() {return {...initialZeroThreeServer(),validator:'math-zero-p4.v1'};}
test('zero p4 selected restored trace plays its exact original cue without modifying learning progress',()=>{
  const f=fixture('math-zero',4), shot=zeroFourPlaying(), calls=[];
  f.window.miraNarrate=cue=>{calls.push(cue);return Promise.resolve(true);};
  const guarded=f.window.miraActivityCheckpoint;
  assert.equal(guarded.beginMayResumeSelectedSceneIntent,true);
  assert.equal(guarded.restore(shot),true);f.window.miraCourseOperation.ready=false;f.adapter.restore(zeroFourServer());
  assert.equal(f.confirmations.at(-1),true);assert.equal(guarded.begin(),false);assert.deepEqual(calls,[]);
  f.window.miraCourseOperation.ready=true;assert.equal(guarded.begin(),true);assert.equal(guarded.begin(),false);
  assert.deepEqual(calls,['zero-p4-repair-trace']);assert.deepEqual(f.get(),shot);
  assert.deepEqual(f.restoredSnapshots,[shot]);assert.deepEqual(f.sent,[]);
});
test('zero p4 restored cue rejects every changed learning field, server evidence or content hash',()=>{
  const mutations=[s=>{s.work.strokes=[[[0.5,0.1],[0.4,0.2]]];},s=>{s.work.mode='free';},
    s=>{s.history.push({name:'hint'});},s=>{s.help.replay=1;},s=>{s.help.hint=1;},
    s=>{s.help.demonstration=1;},s=>{s.attempts.push({});},s=>{s.firstAttempts.trace={};},
    s=>{s.workVersion=2;},s=>{s.currentCue='zero-p4-repair-free';},s=>{s.audioStatus='ready';},
    s=>{s.pen=[0.4,0.1];},s=>{s.tracePassed=true;},s=>{s.teacherDemo='zero-trace';}];
  for(const change of mutations){
    const f=fixture('math-zero',4),shot=zeroFourPlaying(),calls=[];change(shot);f.window.miraNarrate=c=>calls.push(c);
    f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(zeroFourServer());
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  }
  for(const change of [s=>{s.support.replay=1;},s=>{s.history.push({name:'replay'});},s=>{s.workVersion=1;},
    s=>{s.attempts.push({});},s=>{s.firstAttempts.trace={};},s=>{delete s.support;},s=>{s.extra=true;}]){
    const f=fixture('math-zero',4),server=zeroFourServer(),calls=[];change(server);f.window.miraNarrate=c=>calls.push(c);
    f.window.miraActivityCheckpoint.restore(zeroFourPlaying());f.adapter.restore(server);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  }
  const wrong=fixture('math-zero',4,'f'.repeat(64));
  assert.equal(wrong.window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,undefined);
});
test('zero p4 user input, missing audio helper or a synchronous audio failure cannot fabricate progress',()=>{
  const f=fixture('math-zero',4),shot=zeroFourPlaying(),calls=[];f.window.miraNarrate=c=>calls.push(c);
  f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(zeroFourServer());f.event('unknown','pointerdown');
  f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(zeroFourServer());
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  const unavailable=fixture('math-zero',4);unavailable.window.miraActivityCheckpoint.restore(shot);unavailable.adapter.restore(zeroFourServer());
  assert.equal(unavailable.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(unavailable.get(),shot);assert.deepEqual(unavailable.sent,[]);
  const failure=fixture('math-zero',4);failure.window.miraActivityCheckpoint.restore(shot);failure.adapter.restore(zeroFourServer());
  failure.window.miraNarrate=()=>{throw Error('audio failed');};
  assert.equal(failure.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(failure.get(),shot);assert.deepEqual(failure.sent,[]);
});

function zeroSixNoopFixture(count=1,version=1) {
  const shot=initial(6,'math-zero'), work=plain(shot.domainState.work);
  shot.phase=version===1?'ready':'playing';
  shot.domainState={work,n:3,boats:[1,2,3].map(id=>({id:String(id),departed:false}))};
  shot.revisionHistory=Array.from({length:count},()=>({name:'change-quantity',work:plain(work)}));
  shot.currentWorkVersion=version;
  shot.uiState={passed:[],trials:{},message:'换一个数量，再猜一次。以前的尝试仍保留。',cue:'p6-a1',extra:null};
  return {shot,server:{...initialZeroThreeServer(),validator:'math-zero-p6.v1'}};
}
test('zero p6 preserves a proven local initial no-op history without manufacturing a server operation',async()=>{
  for(const [count,version] of [[1,1],[1,2],[2,1],[2,3],[239,2]]){
    const {shot,server}=zeroSixNoopFixture(count,version);const before=plain(shot),f=fixture('math-zero',6);f.set(shot);f.adapter.restore(server);
    assert.equal(f.confirmations.at(-1),true);assert.deepEqual(f.get(),before);assert.deepEqual(f.sent,[]);
    assert.equal(f.event('prediction-zero','click',{selectors:['.prediction-chip']}),false);
    f.get().domainState.work.prediction=0;f.get().prediction=0;await f.flush();
    assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'predict');assert.equal(f.sent[0].work.prediction,0);
  }
});
test('zero p6 rejects changed work, unknown or truncated history, evidence and mismatched server or identity',()=>{
  const mutations=[
    (s,v)=>s.revisionHistory[0].name='predict',
    (s,v)=>s.revisionHistory[0].work.prediction=0,
    (s,v)=>s.revisionHistory[0].work.remaining=[1,2],
    (s,v)=>s.revisionHistory[0].extra=true,
    (s,v)=>s.domainState.work.prediction=0,
    (s,v)=>s.prediction=0,
    (s,v)=>s.firstAttempt={task:'test'},
    (s,v)=>s.firstPrediction={value:0},
    (s,v)=>s.helpFlags.hint=1,
    (s,v)=>s.domainState.boats[0].departed=true,
    (s,v)=>s.uiState.trials={x:{}},
    (s,v)=>s.uiState.passed=['task'],
    (s,v)=>s.uiState.message='unexpected',
    (s,v)=>s.uiState.cue='p6-a2',
    (s,v)=>s.uiState.extra={},
    (s,v)=>s.currentWorkVersion=3,
    (s,v)=>s.phase='complete',
    (s,v)=>s.extra=true,
    (s,v)=>v.support.replay=1,
    (s,v)=>v.history.push({name:'replay'}),
    (s,v)=>v.attempts.push({task:'task'}),
    (s,v)=>v.workVersion=1,
    (s,v)=>v.completed=true,
  ];
  for(const mutate of mutations){const {shot,server}=zeroSixNoopFixture();mutate(shot,server);const before=plain(shot),f=fixture('math-zero',6);f.set(shot);f.adapter.restore(server);assert.equal(f.confirmations.at(-1),false);assert.deepEqual(f.get(),before);assert.deepEqual(f.sent,[]);}
  {const {shot,server}=zeroSixNoopFixture(240,1),f=fixture('math-zero',6);f.set(shot);f.adapter.restore(server);assert.equal(f.confirmations.at(-1),false);}
  {const {shot,server}=zeroSixNoopFixture(),f=fixture('math-zero',6,'0'.repeat(64));f.set(shot);f.adapter.restore(server);assert.equal(f.confirmations.at(-1),false);}
});

const sortedJson=value=>Array.isArray(value)?value.map(sortedJson):value&&typeof value==='object'
  ? Object.fromEntries(Object.keys(value).sort().map(key=>[key,sortedJson(value[key])])):value;
const subtractStoryFixture=()=>({total:3,removed:[1],remaining:[2,3],equation:{whole:3,change:1,result:2}});
test('reviewed p6 and p11 checkpoints recover sorted API JSON while preserving all student state',()=>{
  for(const page of [6,11]){
    const f=fixture('math-subtract',page),shot=initial(page,'math-subtract');
    shot.instructionsComplete=true;shot.currentWorkVersion=2;
    if(page===6){Object.assign(shot.domainState,{equation:{whole:5,change:2,result:3},evidence:'before',checked:true});
      shot.phase='complete';shot.firstAttempt={equation:{whole:3,change:2,result:3},helped:true};}
    else {const story=subtractStoryFixture();Object.assign(shot.domainState,{story:plain(story),saved:plain(story),storyVersion:2,previousWorks:[plain(story)]});
      shot.phase='complete';shot.firstAttempt={story:plain(story),helped:true};}
    shot.helpFlags.hint=true;shot.revisionHistory=[{version:1,action:'move',details:{id:1}},{version:2,action:'save',details:{story:subtractStoryFixture()}}];
    const server=sortedJson(shot),before=plain(server);
    const result=f.window.prepareMathSubtractZeroCheckpoint('scene-p'+page,hashes['math-subtract'][page],server);
    assert.deepEqual(sortedJson(result),before);assert.deepEqual(server,before);
    const eq=page===6?result.domainState.equation:result.domainState.story.equation;
    assert.deepEqual(Object.keys(eq),['whole','change','result']);
    if(page===11){assert.equal(JSON.stringify(result.domainState.story),JSON.stringify(result.domainState.saved));
      assert.deepEqual(Object.keys(result.firstAttempt.story.equation),['whole','change','result']);
      assert.deepEqual(Object.keys(result.domainState.previousWorks[0].equation),['whole','change','result']);}
    assert.deepEqual(plain(result.revisionHistory),server.revisionHistory);assert.deepEqual(f.sent,[]);
  }
});
test('reviewed p6 preserves wrong answers and refuses changed or extra equation fields',()=>{
  const f=fixture('math-subtract',6),shot=sortedJson(initial(6,'math-subtract'));
  const out=f.window.prepareMathSubtractZeroCheckpoint('scene-p6',hashes['math-subtract'][6],shot);
  assert.equal(out.domainState.equation.whole,3);assert.equal(out.domainState.equation.change,2);
  for(const change of [x=>delete x.domainState.equation.result,x=>{x.domainState.equation.extra=1;},x=>{x.domainState.equation.whole=0;},x=>{x.sceneId='scene-p5';}]){
    const bad=sortedJson(initial(6,'math-subtract'));change(bad);
    assert.throws(()=>f.window.prepareMathSubtractZeroCheckpoint('scene-p6',hashes['math-subtract'][6],bad));
  }
  assert.equal(f.window.prepareMathSubtractZeroCheckpoint('scene-p6','f'.repeat(64),shot),shot);
  assert.equal(f.window.prepareMathSubtractZeroCheckpoint('scene-p7',hashes['math-subtract'][6],shot),shot);
});
test('p12 imported source and a sorted checkpoint keep identical key order and source digest on re-entry',()=>{
  const f=fixture('math-subtract',12),story=sortedJson(subtractStoryFixture()),digest='a'.repeat(64);
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p11',available:true,sourceWorkSha256:digest,saved:story};
  const before=plain(ctx);
  f.importer(value=>{
    if(JSON.stringify(value.saved.equation)!==JSON.stringify({whole:3,change:1,result:2}))return false;
    const d=f.get().domainState;
    if(d.sourceWorkSha256===value.sourceWorkSha256)return JSON.stringify(value.saved)===JSON.stringify(d.story)&&JSON.stringify(value.saved)===JSON.stringify(d.saved);
    Object.assign(d,{story:plain(value.saved),saved:plain(value.saved),sourceWorkSha256:value.sourceWorkSha256});return true;
  });
  f.restore(null,ctx);assert.equal(f.confirmations.at(-1),true);assert.deepEqual(ctx,before);
  assert.equal(f.get().domainState.sourceWorkSha256,digest);assert.deepEqual(f.sent,[]);
  f.get().domainState.links.whole='before';const serverWork=sortedJson({story:f.get().domainState.story,saved:f.get().domainState.saved,
    links:f.get().domainState.links,sourceWorkSha256:digest,storyVersion:1,recordVersion:1});
  const fromApi=sortedJson(f.get());const restored=f.window.prepareMathSubtractZeroCheckpoint('scene-p12',hashes['math-subtract'][12],fromApi);
  assert.deepEqual(sortedJson(restored),fromApi);assert.equal(restored.domainState.links.whole,'before');f.set(plain(restored));
  f.restore(serverWork,ctx);assert.equal(f.confirmations.at(-1),true);assert.equal(f.get().domainState.links.whole,'before');
  assert.deepEqual(f.sent,[]);
});
test('p12 source normalization is hash scoped and rejects changed values or added keys',()=>{
  for(const change of [s=>{s.equation.result=1;},s=>{s.equation.extra=0;},s=>{s.extra=true;},s=>{s.removed=[1,2,3];s.remaining=[];}]){
    const f=fixture('math-subtract',12),story=sortedJson(subtractStoryFixture());change(story);
    const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p11',available:true,sourceWorkSha256:'a'.repeat(64),saved:story};
    f.importer(()=>true);f.restore(null,ctx);assert.equal(f.confirmations.at(-1),false);assert.deepEqual(f.imports,[]);assert.deepEqual(f.sent,[]);
  }
  const wrong=fixture('math-subtract',12,'f'.repeat(64)),story=sortedJson(subtractStoryFixture());
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p11',available:true,sourceWorkSha256:'a'.repeat(64),saved:story};
  wrong.importer(value=>Object.keys(value.saved.equation).join(',')==='whole,change,result');wrong.restore(null,ctx);
  assert.equal(wrong.confirmations.at(-1),false);assert.deepEqual(Object.keys(wrong.imports[0].saved.equation),['change','result','whole']);
});
test('p11 and p12 reject malformed stories without erasing historical state',()=>{
  for(const page of [11,12]){
    const f=fixture('math-subtract',page),s=initial(page,'math-subtract'),story=sortedJson(subtractStoryFixture());
    s.domainState.story=story;s.domainState.saved=plain(story);if(page===12)s.domainState.sourceWorkSha256='a'.repeat(64);
    s.firstAttempt=page===11?{story:plain(story),helped:false}:null;
    const original=sortedJson(s),bad=plain(original);bad.domainState.story.equation.extra=1;
    assert.throws(()=>f.window.prepareMathSubtractZeroCheckpoint('scene-p'+page,hashes['math-subtract'][page],bad));
    assert.deepEqual(original,sortedJson(s));assert.deepEqual(f.sent,[]);
  }
});


function replayOnlyZero(page,n,status='playing') {
  const work=initial(page,'math-zero').work,cue=page===3?'zero-p3-repair-start':'zero-p4-repair-trace';
  const history=Array.from({length:Math.min(n,160)},(_,i)=>{const version=n-Math.min(n,160)+i+1;
    return {name:'replay',version,before:work,after:work,help:{replay:version,hint:0,demonstration:0}};});
  const shot={version:1,page,phase:'playing',work,selected:null,activeRole:'whole',answer:null,firstAttempts:{},attempts:[],
    help:{replay:n,hint:0,demonstration:0},history,workVersion:n+1,completedContexts:[],tracePassed:false,traceWork:null,
    currentCue:cue,audioStatus:status,pen:[0.5,0.1],penDown:false,teacherDemo:null};
  const server={kind:'math-zero',validator:'math-zero-p'+page+'.v1',phase:'playing',completed:false,lastWork:work,workVersion:1,
    attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],support:{hint:0,replay:n,demonstration:0},
    undoCount:0,retryCount:0,exposureCount:0,history:Array.from({length:n},(_,i)=>({name:'replay',task:page===3?'task':'trace',
      workVersion:1,work,support:{hint:0,replay:i+1,demonstration:0}})),evidenceBoundary:'client_reported_picture_supported_practice',
    oralSkill:'unobserved',paperHandwriting:'unobserved'};
  return {shot:plain(shot),server:plain(server),cue};
}
test('p3 and p4 replay-only worlds resume their exact original cue without new student evidence',()=>{
  for(const page of [3,4])for(const n of [1,2,160,161,512]){
    const {shot,server,cue}=replayOnlyZero(page,n),f=fixture('math-zero',page),spoken=[];
    f.window.miraNarrate=id=>{spoken.push(id);return Promise.resolve(true);};
    const guarded=f.window.miraActivityCheckpoint;assert.equal(guarded.beginMayResumeSelectedSceneIntent,true);
    assert.equal(guarded.restore(shot),true);f.window.miraCourseOperation.ready=false;f.adapter.restore(server);
    assert.equal(f.confirmations.at(-1),true);assert.equal(guarded.begin(),false);assert.deepEqual(spoken,[]);
    f.window.miraCourseOperation.ready=true;assert.equal(guarded.begin(),true);assert.equal(guarded.begin(),false);
    assert.deepEqual(spoken,[cue]);assert.deepEqual(f.get(),shot);assert.deepEqual(f.restoredSnapshots,[shot]);assert.deepEqual(f.sent,[]);
  }
});
test('p3 and p4 replay-only opening rejects stale, changed, incomplete, mixed or forged evidence',()=>{
  for(const page of [3,4]){
    const shotChanges=[s=>{s.help.hint=1;},s=>{s.help.replay++;},s=>{s.history[0].version++;},
      s=>{s.history[0].help.replay++;},s=>{s.history[0].name='hint';},s=>{s.history.pop();},
      s=>{s.workVersion++;},s=>{s.attempts.push({});},s=>{s.firstAttempts.task={};},s=>{s.currentCue='other';},
      s=>{s.audioStatus='idle';},s=>{s.selected=0;},s=>{s.pen=[0.4,0.1];},
      s=>{s.work=page===3?{order:[0,1,2,3,4,5],quantities:s.work.quantities}:{mode:'trace',strokes:[[[0.5,0.1],[0.4,0.2]]]};}];
    for(const change of shotChanges){const {shot,server}=replayOnlyZero(page,2),f=fixture('math-zero',page),spoken=[];
      change(shot);f.window.miraNarrate=x=>spoken.push(x);f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);
      assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(spoken,[]);assert.deepEqual(f.sent,[]);}
    const serverChanges=[s=>{s.support.replay++;},s=>{s.history[0].name='work';},s=>{s.history[1].support.replay=1;},
      s=>{s.history[0].task='other';},s=>{s.history.pop();},s=>{s.firstAttempts.task={};},s=>{s.attempts.push({});},
      s=>{s.support.hint++;},s=>{s.workVersion=2;},s=>{s.lastWork=null;},s=>{s.exposureCount=1;},s=>{s.extra=true;}];
    for(const change of serverChanges){const {shot,server}=replayOnlyZero(page,2),f=fixture('math-zero',page),spoken=[];
      change(server);f.window.miraNarrate=x=>spoken.push(x);f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);
      assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(spoken,[]);assert.deepEqual(f.sent,[]);}
    const wrong=fixture('math-zero',page,'f'.repeat(64));assert.equal(wrong.window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,undefined);
  }
});
test('p3 and p4 replay-only openings recheck current state and never override real user activity',()=>{
  for(const page of [3,4]){
    const {shot,server}=replayOnlyZero(page,1),f=fixture('math-zero',page),spoken=[];f.window.miraNarrate=x=>spoken.push(x);
    f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);f.get().history[0].help.replay=99;
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(spoken,[]);assert.deepEqual(f.sent,[]);
    const g=fixture('math-zero',page),calls=[];g.window.miraNarrate=x=>calls.push(x);
    g.window.miraActivityCheckpoint.restore(shot);g.adapter.restore(server);g.event('unknown','pointerdown');
    assert.equal(g.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(g.sent,[]);
  }
});


const p9OldMessage='这一段的方向和数量都对上了。再检查另一段。';
const p9FinalMessage='两段都检查好了。到港加0，离港减0。';
// Synthetic fixtures exercise only the authenticated completed-cue gate.
function zeroCompletedSample(page) {
  const shot=initial(page,'math-zero');shot.phase='complete';
  const story={type:'all-left',total:3,operator:'subtract',changed:[1,2,3],remaining:[],equation:{whole:3,change:3,result:0}};
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p13',available:true,sourceWorkSha256:'a'.repeat(64),saved:plain(story)};
  const works={2:{context:'ruler',objects:[1],position:0,meaning:'origin'},
    3:{order:[0,1,2,3,4,5],quantities:[[],[1],[1,2],[1,2,3],[1,2,3,4],[1,2,3,4,5]]},
    4:{mode:'free',strokes:[[[0.5,0.1],[0.7,0.4]]]},
    5:{removed:[1,2,3,4],remaining:[],equation:{whole:4,change:4,result:0},links:{whole:'before',change:'removed',result:'remaining'}},
    6:{total:3,removed:[1,2,3],remaining:[],prediction:0},
    7:{incoming:[],remaining:[1,2,3],gateOpen:true,prediction:3},
    8:{removed:[],remaining:[1,2],executed:true,equation:{whole:2,change:0,result:2}},
    9:{context:'incoming',total:2,changed:[],remaining:[1,2],executed:true,operator:'add',equation:{whole:2,change:0,result:2}},
    10:{operator:'subtract',changed:[],remaining:[],executed:true,equation:{whole:0,change:0,result:0}},
    11:{total:2,operator:'add',changed:[],remaining:[1,2],executed:true,equation:{whole:2,change:0,result:2}},
    12:{context:'path',objects:[1],position:0,meaning:'origin'},13:{story:plain(story),saved:plain(story)},
    14:{story:plain(story),saved:plain(story),zeroRole:'result',sourceWorkSha256:ctx.sourceWorkSha256,storyVersion:1,recordVersion:1}};
  const cues={2:'zero-p2-repair-goodOrigin',3:'zero-p3-repair-success',4:'zero-p4-repair-successFree',
    5:'zero-p5-repair-success',6:'p6-a4',7:'p7-a4',8:'p8-a4',9:'p9-a4',10:'p10-a4',11:'p11-a4',12:'p12-a4',13:'zero-p13-repair-saved',14:'p14-a4'};
  const support={hint:0,replay:0,demonstration:0},work=works[page];
  if(page>=6&&page<=10){shot.domainState.work=plain(work);shot.uiState.cue=cues[page];
    if(page===6||page===7)shot.prediction=work.prediction;}
  else {shot.work=plain(work);shot.currentCue=cues[page];shot.audioStatus='ready';shot.help=plain(support);}
  const passed=({2:['harbour','ruler'],4:['trace','free'],9:['incoming','departing'],10:['add','subtract'],
    11:['add','subtract','different-n'],12:['tools','path']})[page]||['task'];
  const server={kind:'math-zero',validator:'math-zero-p'+page+'.v1',phase:'complete',completed:true,lastWork:plain(work),
    passedTasks:passed,attempts:[],history:[],support:plain(support),evidenceBoundary:'client_reported_picture_supported_practice',
    oralSkill:'unobserved',paperHandwriting:'unobserved'};
  return {shot,server,ctx,cue:cues[page]};
}
function restoreZeroCompleted(page,value=zeroCompletedSample(page),hash=hashes['math-zero'][page]) {
  const f=fixture('math-zero',page,hash),spoken=[];f.window.miraNarrate=cue=>spoken.push(cue);
  if(page===14)f.importer(()=>true);
  f.window.miraActivityCheckpoint.restore(value.shot);f.adapter.restore(value.server,page===14?value.ctx:undefined);
  return {f,spoken};
}
test('completed zero p2-p14 resumes an approved current cue without changing evidence or sending replay',()=>{
  for(let page=2;page<=14;page++){
    const value=zeroCompletedSample(page),{f,spoken}=restoreZeroCompleted(page,value),before=plain(f.get()),server=plain(value.server),imports=f.imports.length;
    assert.equal(f.confirmations.at(-1),true,'alignment p'+page);
    assert.equal(f.window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,true);
    assert.equal(f.window.miraActivityCheckpoint.begin(),true,'begin p'+page);
    assert.deepEqual(spoken,[value.cue]);assert.deepEqual(f.get(),before);assert.deepEqual(value.server,server);
    assert.equal(f.imports.length,imports);assert.deepEqual(f.sent,[]);assert.equal(f.window.miraActivityCheckpoint.begin(),false);
  }
});
test('completed zero cue rejects changed work, support, completion, cue, permission, hash and source',()=>{
  for(let page=2;page<=14;page++)for(const change of [
    x=>{x.server.completed=false;},x=>{x.server.phase='playing';},x=>{x.server.lastWork=null;},
    x=>{x.server.passedTasks=[];},x=>{x.server.support.replay++;},x=>{x.shot.phase='playing';},
    x=>{if(page>=6&&page<=10)x.shot.uiState.cue='p'+page+'-a1';else x.shot.currentCue='unreviewed';},
  ]){const value=zeroCompletedSample(page);change(value);const {f,spoken}=restoreZeroCompleted(page,value);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false,'p'+page);assert.deepEqual(spoken,[]);assert.deepEqual(f.sent,[]);}
  for(let page=2;page<=14;page++){
    const {f,spoken}=restoreZeroCompleted(page);f.window.miraCourseOperation.ready=false;
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(spoken,[]);
    const wrong=restoreZeroCompleted(page,zeroCompletedSample(page),'f'.repeat(64));assert.equal(wrong.f.window.miraActivityCheckpoint.begin,undefined);
  }
  const value=zeroCompletedSample(14);value.ctx.sourceWorkSha256='b'.repeat(64);
  const bad=restoreZeroCompleted(14,value);assert.equal(bad.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(bad.spoken,[]);
});
test('completed zero never plays a context-specific outcome for the wrong scene or writing stage',()=>{
  const wrongContext=zeroCompletedSample(2);wrongContext.shot.currentCue='zero-p2-repair-goodEmpty';
  const a=restoreZeroCompleted(2,wrongContext);assert.equal(a.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(a.spoken,[]);
  const harbour=zeroCompletedSample(2);harbour.shot.work={context:'harbour',objects:[],position:0,meaning:'empty'};
  harbour.server.lastWork=plain(harbour.shot.work);harbour.shot.currentCue='zero-p2-repair-goodEmpty';
  const good=restoreZeroCompleted(2,harbour);assert.equal(good.f.window.miraActivityCheckpoint.begin(),true);assert.deepEqual(good.spoken,['zero-p2-repair-goodEmpty']);
  harbour.shot.currentCue='zero-p2-repair-goodOrigin';const reverse=restoreZeroCompleted(2,harbour);
  assert.equal(reverse.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(reverse.spoken,[]);
  const wrongStage=zeroCompletedSample(4);wrongStage.shot.currentCue='zero-p4-repair-successTrace';
  const b=restoreZeroCompleted(4,wrongStage);assert.equal(b.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(b.spoken,[]);
  const wrongMode=zeroCompletedSample(4);wrongMode.shot.work.mode='trace';wrongMode.server.lastWork.mode='trace';
  const c=restoreZeroCompleted(4,wrongMode);assert.equal(c.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(c.spoken,[]);
  assert.deepEqual([...a.f.sent,...b.f.sent,...c.f.sent],[]);
});
test('completed zero rechecks state and rejects real input or an unavailable audio helper',()=>{
  for(const page of [2,6,9,14]){
    const {f,spoken}=restoreZeroCompleted(page);f.get().phase='playing';
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(spoken,[]);
    const g=restoreZeroCompleted(page);g.f.event('unknown','pointerdown');
    assert.equal(g.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(g.spoken,[]);
    const h=restoreZeroCompleted(page);delete h.f.window.miraNarrate;
    assert.equal(h.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(h.spoken,[]);assert.deepEqual(h.f.sent,[]);
  }
});
test('completed zero waits for real operations or toolbar replay and never manufactures evidence on audio failure',()=>{
  for(const [page,control] of [[2,'checkBtn'],[6,'confirmBtn'],[9,'checkRecordBtn'],[14,'checkBtn']]){
    const {f,spoken}=restoreZeroCompleted(page);f.event(control);
    assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.equal(f.window.miraActivityCheckpoint.begin(),false);
    assert.deepEqual(spoken,[]);assert.deepEqual(f.sent,[]);
    const g=restoreZeroCompleted(page);assert.equal(g.f.adapter.requestParentReplay(),true);
    assert.equal(g.f.window.miraActivityCheckpoint.capture(),null);assert.equal(g.f.window.miraActivityCheckpoint.begin(),false);
    assert.deepEqual(g.spoken,[]);assert.deepEqual(g.f.sent,[]);
    const h=restoreZeroCompleted(page),before=plain(h.f.get());h.f.window.miraNarrate=()=>{throw new Error('no audio');};
    assert.equal(h.f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(h.f.get(),before);assert.deepEqual(h.f.sent,[]);
  }
});
function p9Finished() {
  const work=context=>{const n=context==='incoming'?2:3;return {context,total:n,changed:[],remaining:Array.from({length:n},(_,i)=>i+1),
    executed:true,operator:context==='incoming'?'add':'subtract',equation:{whole:n,change:0,result:n}};};
  const incoming=work('incoming'),departing=work('departing');
  const trials={departing:{work:plain(departing),chosen:true}},shot=initial(9,'math-zero');
  Object.assign(shot,{phase:'complete',domainState:{work:plain(incoming),context:'incoming',panels:plain(trials),operatorChosen:true},
    stableObjectIds:[1,2],uiState:{passed:['departing','incoming'],trials:plain(trials),extra:{chosen:true},message:p9OldMessage,cue:'p9-a4'}});
  const server={kind:'math-zero',validator:'math-zero-p9.v1',phase:'complete',completed:true,passedTasks:['departing','incoming'],lastWork:plain(incoming)};
  return {shot,server,incoming,departing};
}
test('p9 changes only the visible final message after both locally correct tasks and server confirmation',()=>{
  const {shot,server}=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);f.set(plain(shot));
  f.window.miraCourseOperation.ready=false;f.adapter.restore(server);assert.equal(f.confirmations.at(-1),true);
  assert.equal(node.textContent,p9OldMessage);f.window.miraCourseOperation.ready=true;f.operationReady();
  assert.equal(node.textContent,p9FinalMessage);assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);
  f.adapter.dispose();node.textContent=p9OldMessage;f.operationReady();assert.equal(node.textContent,p9OldMessage);
});
test('p9 keeps original feedback when work, completion, server confirmation or content identity disagrees',()=>{
  const changes=[x=>{x.shot.phase='playing';},x=>{x.shot.uiState.passed=['incoming'];},
    x=>{x.shot.domainState.work.equation.result=1;},x=>{x.shot.uiState.trials.departing.work.equation.result=2;},
    x=>{x.shot.uiState.trials.departing.chosen=false;},x=>{x.shot.domainState.panels={};},
    x=>{x.server.passedTasks=['incoming'];x.server.completed=false;x.server.phase='playing';},
    x=>{x.server.completed=false;},x=>{x.server.lastWork=null;}];
  for(const change of changes){const value=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);change(value);f.set(value.shot);
    f.adapter.restore(value.server);f.operationReady();assert.equal(node.textContent,p9OldMessage);assert.deepEqual(f.sent,[]);}
  const wrong=p9Finished(),f=fixture('math-zero',9,'f'.repeat(64)),node=f.feedback(p9OldMessage);
  f.set(wrong.shot);f.adapter.restore(wrong.server);f.operationReady();assert.equal(node.textContent,p9OldMessage);
});
test('p9 final message waits for actual submit ACK, and later edits restore normal feedback',async()=>{
  const {shot,server,incoming}=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);
  shot.phase='playing';shot.uiState.passed=['departing'];server.phase='playing';server.completed=false;server.passedTasks=['departing'];
  f.set(shot);f.adapter.restore(server);f.event('checkRecordBtn');
  f.get().phase='complete';f.get().uiState.passed=['departing','incoming'];await f.flush();
  assert.equal(f.sent.at(-1).name,'submit');assert.equal(node.textContent,p9OldMessage);
  await f.ack();assert.equal(node.textContent,p9FinalMessage);
  f.event('result-choice','click',{selectors:['.result-choice']});f.get().phase='playing';f.get().domainState.work.equation.result=1;
  f.get().uiState.message='记录已修改，点检查核对。';node.textContent=f.get().uiState.message;await f.flush();await f.ack();
  assert.equal(node.textContent,'记录已修改，点检查核对。');assert.equal(f.get().domainState.work.equation.result,1);
  assert.deepEqual(f.sent.map(v=>v.name),['submit','work']);assert.equal(incoming.equation.result,2);
});
test('p9 a rejected or pending final submit never changes the completion message',async()=>{
  const {shot,server}=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);
  shot.phase='playing';shot.uiState.passed=['departing'];server.phase='playing';server.completed=false;server.passedTasks=['departing'];
  f.set(shot);f.adapter.restore(server);f.event('checkRecordBtn');f.get().phase='complete';f.get().uiState.passed=['departing','incoming'];
  await f.flush();assert.equal(node.textContent,p9OldMessage);await f.reject();assert.equal(node.textContent,p9OldMessage);
});


function subtractReplayInitial(page,count,started) {
  const shot=initial(page,'math-subtract'),work=plain(shot.domainState);delete work.bound;delete work.checked;delete work.selected;delete work.editing;
  shot.instructionsComplete=started;shot.phase=started?'playing':'idle';
  const support={hint:0,replay:count,demonstration:0};
  const server={kind:'math-subtract',validator:'math-subtract-p'+page+'.v1',phase:'playing',completed:false,lastWork:count?work:null,workVersion:count?1:0,
    attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:[],support,undoCount:0,retryCount:0,exposureCount:0,
    history:Array.from({length:count},(_,i)=>({name:'replay',task:'task',workVersion:1,work,support:{hint:0,replay:i+1,demonstration:0}})),
    evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'};
  return {shot:plain(shot),server:plain(server)};
}
test('subtraction p4 p6 p8 selected replay-only pages use the authored start or current voice without recording support',()=>{
  for(const page of [4,6,8])for(const started of [false,true])for(const count of [0,1,2,512]){
    const {shot,server}=subtractReplayInitial(page,count,started),f=fixture('math-subtract',page),calls=[];
    f.start(()=>calls.push('start'));f.replay(()=>calls.push('replay'));f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);
    assert.equal(f.confirmations.at(-1),true);assert.equal(f.window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,true);
    assert.equal(f.window.miraActivityCheckpoint.begin(),true,`${page} ${started} ${count}`);
    assert.deepEqual(calls,[started?'replay':'start']);assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);
  }
});
test('subtraction p4 p6 p8 resumed audio fails closed for changed histories, help, snapshots or hash',()=>{
  for(const page of [4,6,8])for(const change of [
    (s,v)=>{v.history[0].name='work';},(s,v)=>{v.support.replay=2;},(s,v)=>{v.history[0].workVersion=2;},
    (s,v)=>{v.history[0].support.replay=2;},(s,v)=>{v.attempts.push({});},(s,v)=>{s.helpFlags.hint=true;},
    (s,v)=>{s.revisionHistory.push({version:1,action:'hint',details:{}});},(s,v)=>{s.domainState.remaining=[];},
    (s,v)=>{s.phase='complete';},(s,v)=>{v.extra=true;},
  ]){
    const {shot,server}=subtractReplayInitial(page,1,true),f=fixture('math-subtract',page),calls=[];change(shot,server);
    f.start(()=>calls.push('start'));f.replay(()=>calls.push('replay'));f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  }
  for(const page of [4,6,8]){const f=fixture('math-subtract',page,'f'.repeat(64));assert.equal(f.window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,undefined);}
});
test('subtraction resumed audio rechecks state and never overrides a genuine student action',()=>{
  const {shot,server}=subtractReplayInitial(4,1,true),f=fixture('math-subtract',4),calls=[];f.replay(()=>calls.push(1));
  f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);f.get().helpFlags.hint=true;
  assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  const g=fixture('math-subtract',4);g.replay(()=>calls.push(1));g.window.miraActivityCheckpoint.restore(shot);g.adapter.restore(server);
  g.event('unknown','pointerdown');assert.equal(g.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);
});

// The p2/p3/p5/p7 values reproduce the completed test-session checkpoints;
// p9-p12 cover additional authored completion predicates without claiming a
// live session for those pages.
function extraFinishedSample(page) {
  const shot=initial(page,'math-subtract');shot.prediction=null;shot.phase='complete';shot.instructionsComplete=true;
  const story={total:3,removed:[1],remaining:[2,3],equation:{whole:3,change:1,result:2}};
  const ctx={schemaVersion:'mira.math-story-source.v1',sourceSceneId:'scene-p11',available:true,sourceWorkSha256:'a'.repeat(64),saved:plain(story)};
  let work;
  if(page===2){
    work={removed:[1],remaining:[2,3,4],answer:3};shot.domainState={...work,checked:true};
    shot.firstAttempt={removed:[1],remaining:[2,3,4],answer:4,helped:false};
    shot.revisionHistory=[{version:1,action:'move',details:{id:1}},{version:2,action:'answer',details:{answer:4}},
      {version:3,action:'check',details:{answer:4,removed:[1],remaining:[2,3,4],checked:false}},
      {version:4,action:'answer',details:{answer:3}},{version:5,action:'check',details:{...work,checked:false}}];
  }else if(page===3){
    const details=[{number:4,zone:'original',objectIds:['b1','b2','b3','b4'],correct:true,helped:false},
      {number:1,zone:'removed',objectIds:['b1'],correct:true,helped:false},{number:3,zone:'remaining',objectIds:['b2','b3','b4'],correct:true,helped:false}];
    shot.domainState={connections:{original:'original',removed:'removed',remaining:'remaining'},selected:null};
    shot.firstAttempt=plain(details[0]);shot.revisionHistory=details.map((v,i)=>({version:i+1,action:'connect',details:v}));
    work={total:4,removed:[1],remaining:[2,3,4],equation:{whole:4,change:1,result:3},links:{whole:'before',change:'removed',result:'remaining'}};
  }else if(page===5){
    shot.domainState={leftItems:['L1','L2','L3'],rightItems:['R1','R2','R3'],removedLeft:['L5','L4'],
      pairs:[['L1','R1'],['L2','R2'],['L3','R3']],checked:'equal'};
    shot.firstAttempt={leftItems:['L1','L2','L3'],removedLeft:['L5','L4'],pairs:plain(shot.domainState.pairs),equal:true,helped:false};
    shot.revisionHistory=[{version:1,action:'remove',details:{id:'L5',leftCount:4}},{version:2,action:'remove',details:{id:'L4',leftCount:3}},
      {version:3,action:'check',details:plain(shot.firstAttempt)}];work={removed:[4,5],remaining:[1,2,3],pairs:[[1,1],[2,2],[3,3]]};
  }else if(page===7){
    work={removed:[4],remaining:[1,2,3],method:'count-remaining',counted:[1,2,3],countdown:[],answer:3};
    shot.domainState={...work,visited:['count-remaining']};shot.firstAttempt={method:'count-remaining',id:1,answer:1,helped:false};
    shot.revisionHistory=[{version:1,action:'method',details:{method:'count-remaining'}},
      ...[1,2,3].map((id,i)=>({version:i+2,action:'count',details:{id,counted:[1,2,3].slice(0,id)}}))];
  }else if(page===9){
    work={removedA:[1],remainingA:[2,3,4,5],removedB:[1,2,3],remainingB:[4,5],prediction:'A'};
    shot.domainState={...work,checked:true};shot.prediction='A';shot.firstAttempt={prediction:'A',beforeRemoval:true,helped:false};
  }else if(page===10){work={removed:[1],remaining:[2,3],answer:2};shot.domainState={...work,checked:true};}
  else if(page===11){work={story:plain(story),saved:plain(story)};shot.domainState={...work,storyVersion:1,previousWorks:[]};}
  else {work={story:plain(story),saved:plain(story),links:{whole:'before',change:'removed',result:'remaining'},
      sourceWorkSha256:ctx.sourceWorkSha256,storyVersion:1,recordVersion:1};shot.domainState={...work,selected:null,checked:true};}
  shot.currentWorkVersion=shot.revisionHistory.length;
  const server={kind:'math-subtract',validator:'math-subtract-p'+page+'.v1',phase:'complete',completed:true,lastWork:plain(work),
    workVersion:3,attempts:[],firstAttempts:{},firstPredictions:{},latestPredictions:{},passedTasks:['task'],
    support:{hint:0,replay:page===2||page===3?1:0,demonstration:0},undoCount:0,retryCount:0,exposureCount:0,history:[],
    evidenceBoundary:'client_reported_picture_supported_practice',oralSkill:'unobserved',paperHandwriting:'unobserved'};
  return {shot:plain(shot),server,ctx};
}
function restoreExtraFinished(page,values=extraFinishedSample(page),hash=hashes['math-subtract'][page]) {
  const f=fixture('math-subtract',page,hash),calls=[];f.replay(()=>calls.push('replay'));
  if(page===12)f.importer(()=>true);
  f.window.miraActivityCheckpoint.restore(values.shot);f.adapter.restore(values.server,page===12?values.ctx:undefined);
  return {f,calls};
}
test('completed subtraction p2 p3 p5 p7 and p9-p12 can resume only selected original audio, preserving evidence',()=>{
  for(const page of [2,3,5,7,9,10,11,12]){
    const value=extraFinishedSample(page),{f,calls}=restoreExtraFinished(page,value),before=plain(f.get()),originalServer=plain(value.server);
    assert.equal(f.confirmations.at(-1),true,'aligned p'+page);
    assert.equal(f.window.miraActivityCheckpoint.beginMayResumeSelectedSceneIntent,true);
    assert.equal(f.window.miraActivityCheckpoint.begin(),true,'resume p'+page);
    assert.deepEqual(calls,['replay']);assert.deepEqual(f.get(),before);assert.deepEqual(f.sent,[]);
    assert.deepEqual(value.server,originalServer);assert.equal(f.window.miraActivityCheckpoint.begin(),false);
  }
});
test('completed subtraction audio rejects mismatched server, non-complete local state, no permission and changed hash',()=>{
  for(const page of [2,3,5,7,9,10,11,12])for(const change of [
    x=>{x.server.completed=false;},x=>{x.server.phase='playing';},x=>{x.server.lastWork=null;},
    x=>{x.server.lastWork=Object.assign({},x.server.lastWork,{extra:true});},x=>{x.shot.phase='playing';},
    x=>{x.shot.instructionsComplete=false;},x=>{x.shot.helpFlags.hint='yes';},
  ]){
    const value=extraFinishedSample(page);change(value);const {f,calls}=restoreExtraFinished(page,value);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false,'p'+page);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  }
  for(const page of [2,3,5,7,9,10,11,12]){
    const {f,calls}=restoreExtraFinished(page);f.window.miraCourseOperation.ready=false;
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);
    const wrong=restoreExtraFinished(page,extraFinishedSample(page),'f'.repeat(64));
    assert.equal(wrong.f.window.miraActivityCheckpoint.begin,undefined);assert.deepEqual(wrong.calls,[]);
  }
});
test('completed subtraction audio rechecks local completion and source immediately before playing',()=>{
  for(const page of [2,3,5,7,9,10,11,12]){
    const {f,calls}=restoreExtraFinished(page);f.get().helpFlags.hint=true;
    // Help is an existing field and unchanged by replay; altered work is not allowed.
    if(page===3)f.get().domainState.connections.original=null;
    else if(page===5)f.get().domainState.checked=null;
    else if(page===7)f.get().domainState.counted.pop();
    else if(page===9)f.get().domainState.checked=false;
    else if(page===11)f.get().domainState.saved=null;
    else if(page===12)f.get().domainState.sourceWorkSha256='b'.repeat(64);
    else f.get().domainState.checked=false;
    assert.equal(f.window.miraActivityCheckpoint.begin(),false,'p'+page);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);
  }
  const value=extraFinishedSample(12);value.ctx.saved.removed=[2];
  const {f,calls}=restoreExtraFinished(12,value);assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);
});
function subtractFinishedSample(page) {
  const {shot,server}=subtractReplayInitial(page,1,true),R={hint:0,replay:1,demonstration:0},base=plain(server.lastWork);
  const event=(name,work,workVersion)=>({name,task:'task',work,workVersion,support:plain(R)});
  const attempt=(work,correct,workVersion,index)=>({task:'task',work,correct,workVersion,support:plain(R),undoCount:0,retryCount:0,
    priorReveals:0,priorAttempts:index,priorPageAttempts:index,pictureSupport:true,assistanceOutsideApp:'unobserved'});
  let history,attempts;
  if(page===4){
    const first={...base,removed:[1],remaining:[2,3,4]},last={...first,mode:'point',symbol:'subtract'};
    attempts=[attempt(first,false,2,0),attempt(last,true,3,1)];
    history=[event('replay',base,1),event('work',first,2),event('submit',first,2),event('work',last,3),event('submit',last,3)];
    shot.domainState={...last,bound:true};shot.firstAttempt={removed:[1],symbol:null,strokes:[],mode:'trace',helped:false};
    shot.revisionHistory=[{version:1,action:'move',details:{id:1}},{version:2,action:'bind',details:{...first,bound:false}},
      {version:3,action:'point',details:{symbol:'subtract'}},{version:4,action:'bind',details:{...last,bound:false}}];shot.currentWorkVersion=4;
  }else if(page===6){
    const first={...base,evidence:'before'},last={...first,equation:{whole:5,change:2,result:3}};
    attempts=[attempt(last,true,3,0)];history=[event('replay',base,1),event('work',first,2),event('work',last,3),event('submit',last,3)];
    shot.domainState={...last,editing:null,checked:true};shot.firstAttempt={field:'whole',value:5,evidence:'before',helped:false};
    shot.revisionHistory=[{version:1,action:'evidence',details:{evidence:'before'}},
      {version:2,action:'edit',details:{field:'whole',value:5,equation:last.equation,evidence:'before'}},
      {version:3,action:'check',details:{equation:last.equation,evidence:'before'}}];shot.currentWorkVersion=3;
  }else{
    const first={...base,removed:[1,2,3],remaining:[4,5]},last={...first,answer:2};
    attempts=[attempt(last,true,3,0)];history=[event('replay',base,1),event('work',first,2),event('work',last,3),event('submit',last,3)];
    shot.domainState={...last,selected:'groupB',checked:true};shot.firstAttempt={removed:[1,2,3],remaining:[4,5],answer:2,helped:false};
    shot.revisionHistory=[{version:1,action:'move-group',details:{key:'groupA',removed:[1,2,3]}},
      {version:2,action:'answer',details:{key:'groupB',answer:2}},{version:3,action:'check',details:{removed:[1,2,3],remaining:[4,5],answer:2}}];shot.currentWorkVersion=3;
  }
  shot.phase='complete';Object.assign(server,{phase:'complete',completed:true,lastWork:plain(history.at(-1).work),workVersion:3,
    passedTasks:['task'],history,attempts,firstAttempts:{task:plain(attempts[0])}});
  return {shot:plain(shot),server:plain(server)};
}
test('completed subtraction p4 p6 and p8 retain accepted work and first attempt while resuming the original cue',()=>{
  for(const page of [4,6,8]){const {shot,server}=subtractFinishedSample(page),f=fixture('math-subtract',page),calls=[];
    f.replay(()=>calls.push('replay'));f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);
    assert.equal(f.confirmations.at(-1),true);assert.equal(f.window.miraActivityCheckpoint.begin(),true);
    assert.deepEqual(calls,['replay']);assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);}
});
test('completed subtraction resume rejects any stale work, missing history, changed attempts or mismatched completion',()=>{
  for(const page of [4,6,8])for(const change of [
    (s,v)=>{s.firstAttempt.helped=true;},(s,v)=>{s.revisionHistory.pop();},(s,v)=>{s.currentWorkVersion--;},
    (s,v)=>{v.history.pop();},(s,v)=>{v.attempts[0].correct=!v.attempts[0].correct;},
    (s,v)=>{v.history[1].workVersion=7;},(s,v)=>{v.firstAttempts.task.correct=!v.firstAttempts.task.correct;},
    (s,v)=>{v.support.hint=1;},(s,v)=>{s.phase='playing';},(s,v)=>{s.domainState[page===4?'bound':'checked']=false;},
  ]){const {shot,server}=subtractFinishedSample(page),f=fixture('math-subtract',page),calls=[];change(shot,server);
    f.replay(()=>calls.push('replay'));f.window.miraActivityCheckpoint.restore(shot);f.adapter.restore(server);
    assert.equal(f.window.miraActivityCheckpoint.begin(),false);assert.deepEqual(calls,[]);assert.deepEqual(f.sent,[]);}
});

test('exact subtraction p1 adds a separate native truck button and activates authored click exactly once',async()=>{
  for(const key of ['Enter',' ']){
    const f=fixture('math-subtract',1,hashes['math-subtract'][1],{truck:true});let originalCalls=0;
    assert.equal(f.truck.getAttribute('role'),null);assert.equal(f.truck.getAttribute('tabindex'),null);
    assert.equal(f.truck.getAttribute('aria-label'),'货车区');assert.equal(f.truck.parentNode,f.sceneArea);
    assert.equal(f.truckButton.tagName,'BUTTON');assert.equal(f.truckButton.getAttribute('type'),'button');
    assert.equal(f.truckButton.textContent,'把选中的箱子装上车');
    assert.equal(f.activityShell.children[1],f.truckButton);assert.equal(f.sceneArea.nextSibling,f.truckButton);f.restore();
    f.event('predPlusBtn');f.changePrediction(3);await f.flush();await f.ack();
    f.truckClick(e=>{originalCalls++;assert.equal(e.isTrusted,false);assert.equal(e.target,f.truck);f.move(1);f.move(2);});
    assert.equal(f.event('mira-truck-assist','keydown',{key,target:f.truckButton}),true);assert.equal(originalCalls,1);
    const used=f.dispatched.at(-1);assert.equal(f.truck.dispatchEvent(used),false);assert.equal(originalCalls,1);
    assert.equal(f.event('mira-truck-assist','keydown',{key,target:f.truckButton,repeat:true}),true);assert.equal(originalCalls,1);
    await f.flush();assert.deepEqual(f.sent.map(x=>x.name),['predict','work']);
    assert.deepEqual(f.sent.at(-1).work,{removed:[1,2],remaining:[3,4,5],prediction:3});
    f.keyup(key);assert.equal(f.event('mira-truck-assist','keydown',{key,target:f.truckButton}),true);assert.equal(originalCalls,1);
    await f.ack();assert.equal(f.event('mira-truck-assist','keydown',{key,target:f.truckButton}),true);assert.equal(originalCalls,1);
    f.keyup(key);f.truckClick(()=>{originalCalls++;});f.event('mira-truck-assist','keydown',{key,target:f.truckButton});await f.flush();
    assert.equal(originalCalls,2);assert.equal(f.sent.length,2);
    f.adapter.dispose();assert.equal(f.truckButton.parentNode,null);assert.equal(f.truck.getAttribute('aria-label'),'货车区');
  }
});
test('exact subtraction p1 truck button supports a real pointer click and preserves original truck clicks',async()=>{
  const f=fixture('math-subtract',1,hashes['math-subtract'][1],{truck:true});f.restore();let calls=0;
  f.truckClick(()=>{calls++;f.move(1);});
  assert.equal(f.event('mira-truck-assist','click',{target:f.truckButton}),true);assert.equal(calls,1);
  await f.flush();assert.deepEqual(f.sent.map(x=>x.name),['work']);await f.ack();
  assert.equal(f.event('truckZone','click',{target:f.truck}),false);f.move(2);await f.flush();
  assert.deepEqual(f.sent.map(x=>x.name),['work','work']);assert.deepEqual(f.sent[1].work.removed,[1,2]);await f.ack();
});
test('truck button is hash scoped and synthetic truck clicks cannot bypass input accounting',async()=>{
  {const f=fixture('math-subtract',1,'0'.repeat(64),{truck:true});f.restore();assert.equal(f.truckButton,null);}
  {const f=fixture('math-subtract',1,hashes['math-subtract'][1],{truck:true,truckRole:'region'});f.restore();assert.equal(f.truckButton,null);}
  for(const mode of ['aligned','not-aligned','pending','rejected','offline','no-click-factory']){
    const f=fixture('math-subtract',1,hashes['math-subtract'][1],{truck:true,...(mode==='no-click-factory'?{noMouseEvent:true,noLegacyEvent:true}:{})});let calls=0;
    f.truckClick(()=>calls++);f.restore(mode==='not-aligned'?{removed:[1],remaining:[2,3,4,5],prediction:3}:null);
    if(mode==='pending'||mode==='rejected'){f.event('predPlusBtn');f.changePrediction(3);await f.flush();if(mode==='rejected')await f.reject();}
    if(mode==='offline')f.window.miraCourseOperation.ready=false;
    const fake={type:'click',isTrusted:false,preventDefault(){this.defaultPrevented=true;},stopImmediatePropagation(){this.stopped=true;}};
    assert.equal(f.truck.dispatchEvent(fake),false,mode);assert.equal(calls,0,mode);
    assert.equal(f.event('mira-truck-assist','click',{target:f.truckButton,isTrusted:false}),true,mode);
    if(mode!=='aligned')assert.equal(f.event('mira-truck-assist','keydown',{key:'Enter',target:f.truckButton}),true,mode);
    await f.flush();assert.equal(calls,0,mode);assert.deepEqual(f.sent.map(x=>x.name),['pending','rejected'].includes(mode)?['predict']:[],mode);
  }
});
test('exact subtraction p1 only maps authored number keys 1 through 5',async()=>{
  const f=fixture('math-subtract',1,hashes['math-subtract'][1]);f.restore();
  assert.equal(f.event('sceneArea','keydown',{key:'0'}),false);await f.flush();assert.deepEqual(f.sent,[]);
  assert.notEqual(f.window.miraActivityCheckpoint.capture(),null);
  for(const key of ['1','2','3','4','5'])assert.equal(f.event('sceneArea','keydown',{key,isTrusted:false}),true,key+' synthetic');
  assert.equal(f.event('sceneArea','keydown',{key:'6',isTrusted:false}),false);assert.deepEqual(f.sent,[]);
  for(const n of [1,5]){assert.equal(f.event('sceneArea','keydown',{key:String(n)}),false);f.changePrediction(n);await f.flush();await f.ack();}
  assert.deepEqual(f.sent.map(x=>x.name),['predict','predict']);assert.equal(f.sent[0].work.prediction,1);assert.equal(f.sent[1].work.prediction,5);
});

test('exact subtraction p1 crate key activates once per genuine press, without affecting pointer work',async()=>{
  for(const key of ['Enter',' ']){
    const f=fixture('math-subtract',1,hashes['math-subtract'][1],{truck:true});f.restore();
    let toggles=0;const press=(repeat=false,trusted=true)=>{const blocked=f.event('crate_1','keydown',{key,repeat,isTrusted:trusted});if(!blocked)toggles++;return blocked;};
    assert.equal(press(),false);await f.flush();assert.equal(toggles,1);assert.deepEqual(f.sent,[]);
    assert.equal(press(true),true);assert.equal(press(),true);f.keyup(key,false);f.blur(false);assert.equal(press(),true);
    assert.equal(toggles,1);f.blur();assert.equal(press(),false);await f.flush();
    f.keyup(key);assert.equal(press(),false);await f.flush();assert.equal(toggles,3);assert.deepEqual(f.sent,[]);
    f.keyup(key);assert.equal(f.event('crate_1','click'),false);await f.flush();assert.deepEqual(f.sent,[]);
    assert.equal(f.event('crate_1','pointerdown'),false);f.move(1);
    assert.equal(f.event('crate_1','pointerup'),false);await f.flush();
    assert.deepEqual(f.sent.map(x=>x.name),['work']);assert.deepEqual(f.sent[0].work,{removed:[1],remaining:[2,3,4,5],prediction:null});await f.ack();
  }
  const g=fixture('math-subtract',1,'0'.repeat(64));g.restore();
  assert.equal(g.event('crate_1','keydown',{key:'Enter'}),false);await g.flush();
  assert.equal(g.event('crate_1','keydown',{key:'Enter',repeat:true}),false);await g.flush();assert.deepEqual(g.sent,[]);
});

test('exact subtraction p1 crate blocks synthetic keys and real keys when progress is unsafe',async()=>{
  for(const mode of ['aligned','not-aligned','pending','rejected','offline']){
    const f=fixture('math-subtract',1,hashes['math-subtract'][1],{truck:true});
    f.restore(mode==='not-aligned'?{removed:[1],remaining:[2,3,4,5],prediction:3}:null);
    if(mode==='pending'||mode==='rejected'){
      f.event('predPlusBtn');f.changePrediction(3);await f.flush();if(mode==='rejected')await f.reject();
    }
    if(mode==='offline')f.window.miraCourseOperation.ready=false;
    for(const key of ['Enter',' ']){
      assert.equal(f.event('crate_1','keydown',{key,isTrusted:false}),true,mode+' '+key+' synthetic');
      if(mode!=='aligned'){
        assert.equal(f.event('crate_1','keydown',{key}),true,mode+' '+key+' genuine');f.keyup(key);
      }
    }
    const expected=mode==='pending'||mode==='rejected'?['predict']:[];
    assert.deepEqual(f.sent.map(x=>x.name),expected,mode);
    if(mode==='rejected')assert.ok(f.notices.includes('mira-course-operation-error'));
    if(mode==='pending'||mode==='rejected'||mode==='offline'||mode==='not-aligned')
      assert.equal(f.window.miraActivityCheckpoint.capture(),null,mode);
  }
});


test('p9 observer repairs a later authored redraw without an operation and disconnects on dispose',()=>{
  const {shot,server}=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);f.set(plain(shot));
  f.adapter.restore(server);assert.equal(node.textContent,p9FinalMessage);assert.equal(f.observers.filter(o=>o.connected).length,1);
  node.textContent=p9OldMessage;f.redraw(node);assert.equal(node.textContent,p9FinalMessage);
  f.redraw(node);assert.equal(node.textContent,p9FinalMessage);assert.deepEqual(f.get(),shot);assert.deepEqual(f.sent,[]);
  f.adapter.dispose();assert.equal(f.observers.filter(o=>o.connected).length,0);
  node.textContent=p9OldMessage;f.redraw(node);assert.equal(node.textContent,p9OldMessage);
});
test('p9 observer never repairs before alignment, while offline, pending or after a rejected operation',async()=>{
  for(const mode of ['unaligned','offline','pending','rejected']){
    const {shot,server}=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);f.set(plain(shot));
    if(mode==='unaligned')server.lastWork.equation.result=1;
    if(mode==='offline')f.window.miraCourseOperation.ready=false;
    f.adapter.restore(server);
    if(mode==='pending'||mode==='rejected'){
      f.event('checkRecordBtn');await f.flush();if(mode==='rejected')await f.reject();
    }
    node.textContent=p9OldMessage;f.redraw(node);assert.equal(node.textContent,p9OldMessage,mode);
    if(mode==='pending'){await f.ack();assert.equal(node.textContent,p9FinalMessage);}
  }
});


test('p9 restores completion even when the current panel retains an earlier saved trial',()=>{
  const {shot,server,incoming}=p9Finished(),f=fixture('math-zero',9),node=f.feedback(p9OldMessage);
  const oldTrial=plain(incoming);oldTrial.equation.result=null;
  shot.uiState.trials.incoming={work:oldTrial,chosen:true};shot.domainState.panels=plain(shot.uiState.trials);f.set(shot);
  f.window.miraCourseOperation.ready=false;f.adapter.restore(server);assert.equal(f.confirmations.at(-1),true);
  f.window.miraCourseOperation.ready=true;f.operationReady();assert.equal(node.textContent,p9FinalMessage);
  node.textContent=p9OldMessage;f.redraw(node);assert.equal(node.textContent,p9FinalMessage);assert.deepEqual(f.sent,[]);
});
