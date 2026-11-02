const assert=require('node:assert/strict'),test=require('node:test'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(require('node:path').join(__dirname,'science-fruit.js'),'utf8');
function fixture(page=2){
 const handlers={},sent=[],confirmed=[],timers=new Map(),notices={feedbackLine:{},zoneFeedback:{},feedbackBubble:{}};let tid=0,resolveSend;
 const shot={version:1,childDecision:[],domainState:{started:false},helpCount:0,completed:true};
 class Element {constructor(id,tag='BUTTON'){this.id=id;this.tagName=tag;}closest(){return this;}}
 const window={miraActivityCheckpoint:{capture:()=>JSON.parse(JSON.stringify(shot)),restore:s=>{Object.keys(shot).forEach(k=>delete shot[k]);Object.assign(shot,JSON.parse(JSON.stringify(s)));return true;}},dispatchEvent(){},miraCourseOperation:{ready:true,restoreConfirmed:x=>confirmed.push(x),send:op=>{sent.push(op);return new Promise(r=>resolveSend=r);}}};
 vm.runInNewContext(source,{window,document:{addEventListener:(n,f)=>handlers[n]=f,removeEventListener:n=>delete handlers[n],getElementById:id=>notices[id]},Element,Event:class{},CustomEvent:class{},setTimeout:f=>{timers.set(++tid,f);return tid;},clearTimeout:id=>timers.delete(id)});
 const adapter=window.installScienceFruitAdapter('scene-p'+page);
 const event=(type,id='start',trusted=true)=>{let blocked=false;handlers[type]({type,isTrusted:trusted,target:new Element(id),key:'Enter',preventDefault(){blocked=true;},stopImmediatePropagation(){}});return blocked;};
 return {adapter,window,shot,sent,confirmed,event,notices,restore:server=>adapter.restore(server||{kind:'science-fruit',validator:'science-fruit-p'+page+'.v1',lastWork:null}),
 flush:()=>{const t=[...timers.values()];timers.clear();t.forEach(f=>f());},ack:async()=>{resolveSend();await Promise.resolve();}};
}
test('pointer release does not swallow the ensuing real click; one operation per gesture',async()=>{
 const f=fixture();f.restore();assert.deepEqual(f.confirmed,[true]);
 f.event('pointerup');f.event('mouseup');assert.equal(f.event('click'),false);f.shot.domainState.started=true;f.flush();
 assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'work');assert.equal('completed' in f.sent[0].work,false);
 assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.equal(f.event('pointerdown','eyes'),true);
 await f.ack();assert.ok(f.window.miraActivityCheckpoint.capture());
 f.event('click','eyes');f.shot.childDecision.push('eyes');f.flush();assert.equal(f.sent.length,2);assert.equal(f.sent[1].name,'submit');
});
test('untrusted events do not report evidence; exact semantic recovery is required',()=>{
 const f=fixture();f.restore();f.event('click','start',false);f.flush();assert.equal(f.sent.length,0);
 f.restore({kind:'science-fruit',validator:'science-fruit-p2.v1',lastWork:{started:true}});assert.equal(f.confirmed.at(-1),false);
 assert.equal(f.event('click'),true);f.flush();assert.equal(f.sent.length,0);
});
test('restore ignores only unavailable historical response metadata',()=>{
 const f=fixture();f.shot.domainState.started=true;f.shot.childDecision=['eyes'];f.shot.firstAnswer='nose';
 const core={started:true,decision:['eyes'],domain:{},help:0,first:'nose'};
 f.restore({kind:'science-fruit',validator:'science-fruit-p2.v1',lastWork:{...core,response:{action:'add',channel:'eyes',timestamp:123}}});
 assert.equal(f.confirmed.at(-1),true);
 f.event('click','hand');f.shot.childDecision.push('hand');f.flush();
 assert.equal(f.sent.length,1);assert.equal(JSON.stringify(f.sent[0].work.decision),JSON.stringify(['eyes','hand']));
});
test('restore still rejects differences in graded and resumable fields',()=>{
 const f=fixture();f.shot.domainState.started=true;f.shot.childDecision=['eyes'];f.shot.firstAnswer='nose';
 const core={started:true,decision:['eyes'],domain:{},help:0,first:'nose',response:null};
 for(const changed of [
   {...core,decision:['hand']},{...core,domain:{force:'heavy'}},{...core,help:1},{...core,first:'eyes'}
 ]){
   f.restore({kind:'science-fruit',validator:'science-fruit-p2.v1',lastWork:changed});
   assert.equal(f.confirmed.at(-1),false);
 }
});
test('native keyboard activation is reported by its real click only',()=>{
 const f=fixture();f.restore();f.event('keydown');f.flush();assert.equal(f.sent.length,0);
 f.event('click');f.shot.domainState.started=true;f.flush();assert.equal(f.sent.length,1);
});
test('page six reads started from its own checkpoint rather than domainState',()=>{
 const f=fixture(6);
 f.shot.started=false;
 f.shot.childDecision={positions:{left:'apple',right:'tomato'},mode:'angle',force:'light'};
 f.shot.domainState={swapCount:0,fruits:{apple:{angle:0,probeForce:null},tomato:{angle:0,probeForce:null}}};
 f.restore();assert.equal(f.confirmed.at(-1),true);
 f.event('click','startExploreBtn');f.shot.started=true;f.flush();
 assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'work');assert.equal(f.sent[0].work.started,true);
});
test('page six permits only an explicit reset when a legacy local world is ahead',async()=>{
 const f=fixture(6);
 f.shot.started=true;f.shot.childDecision={positions:{left:'tomato',right:'apple'},mode:'probe',force:'light'};
 f.shot.domainState={swapCount:1,fruits:{apple:{angle:1,probeForce:'light'},tomato:{angle:1,probeForce:'light'}}};
 f.shot.firstAnswer={type:'angle',fruit:'apple',from:0,to:1};
 const server={kind:'science-fruit',validator:'science-fruit-p6.v1',completed:false,attempts:[],milestones:[],
   lastWork:{started:true,decision:{positions:{left:'apple',right:'tomato'},mode:'angle',force:'light'},
     domain:{swaps:0,fruits:{apple:{angle:1,force:null},tomato:{angle:0,force:null}}},
     help:0,first:f.shot.firstAnswer,response:null}};
 f.restore(server);assert.equal(f.confirmed.at(-1),true);
 assert.match(f.notices.feedbackLine.textContent,/重置/);
 assert.equal(f.event('click','leftCard'),true);f.flush();assert.equal(f.sent.length,0);
 assert.equal(f.event('click','resetBtn'),false);
 f.shot.childDecision={positions:{left:'apple',right:'tomato'},mode:'angle',force:'light'};
 f.shot.domainState={swapCount:0,fruits:{apple:{angle:0,probeForce:null},tomato:{angle:0,probeForce:null}}};
 f.flush();assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'work');assert.equal(f.sent[0].action,'resetBtn');
 await f.ack();assert.equal(f.event('click','leftCard'),false);
});
test('page six never permits recovery reset over recorded attempts or completion',()=>{
 for(const extra of [{completed:true,attempts:[],milestones:[]},{completed:false,attempts:[{}],milestones:[]},
   {completed:false,attempts:[],milestones:['before-swap']}] ){
   const f=fixture(6);f.shot.started=true;
   f.shot.childDecision={positions:{left:'tomato',right:'apple'},mode:'probe',force:'light'};
   f.shot.domainState={swapCount:1,fruits:{apple:{angle:1,probeForce:'light'},tomato:{angle:1,probeForce:'light'}}};
   f.restore({kind:'science-fruit',validator:'science-fruit-p6.v1',...extra,lastWork:{started:true}});
   assert.equal(f.confirmed.at(-1),false);assert.equal(f.event('click','resetBtn'),true);
 }
});
test('pages seven and eight restart unaccepted local-only work without importing old first answers',async()=>{
 for(const page of [7,8]){
   const f=fixture(page);f.shot.domainState.started=true;f.shot.firstAnswer={unverified:'old'};f.shot.helpCount=2;f.shot.undoHistory=[{unverified:true}];
   f.shot.childDecision=page===7?{'ev-round':'both'}:{apple_red:'left'};
   if(page===8)f.shot.domainState.currentStandard='color';
   f.restore({kind:'science-fruit',validator:'science-fruit-p'+page+'.v1',completed:false,attempts:[],milestones:[],lastWork:null});
   assert.equal(f.confirmed.at(-1),true);assert.equal(f.event('click','leftCard'),true);
   assert.match(page===7?f.notices.zoneFeedback.textContent:f.notices.feedbackBubble.textContent,page===7?/重置/:/重排/);
   const reset=page===8?'btnReset':'resetBtn';assert.equal(f.event('click',reset),false);
   f.shot.childDecision=page===7?{'ev-round':null}:{};f.flush();
   assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'work');assert.equal(f.sent[0].work.first,null);
   assert.equal(f.sent[0].work.help,0);assert.equal(JSON.stringify(f.shot.undoHistory),'[]');
   await f.ack();assert.equal(f.event('click','leftCard'),false);
 }
});
