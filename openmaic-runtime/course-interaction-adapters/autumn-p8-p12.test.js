const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname,'autumn-p8-p12.js'),'utf8');

function fixture(scene, ready=true) {
  const docHandlers={}, winHandlers={}, sent=[], confirmed=[];
  class Element {
    constructor(id) { this.id=id; this.dataset={}; this.isConnected=true; this.style={}; }
    closest(selector) { return selector === '#'+this.id ? this : null; }
  }
  const elements={startOverlay:{classList:{contains:()=>false}},start:{hidden:false},'ready-layer':{hidden:false},'start-overlay':{classList:{contains:()=>false}}};
  const document={addEventListener:(t,f)=>docHandlers[t]=f, removeEventListener:()=>{},getElementById:id=>elements[id],querySelector:()=>null};
  const window={miraCourseOperation:{ready,send:op=>{sent.push(op);return Promise.resolve();},restoreConfirmed:x=>confirmed.push(x)},
    addEventListener:(t,f)=>winHandlers[t]=f,removeEventListener:()=>{},dispatchEvent:()=>{}};
  vm.runInNewContext(source,{window,document,Element,CustomEvent:class{},queueMicrotask,Promise,Number,JSON});
  const adapter=window.installAutumnCourseAdapter(scene);
  function click(id,trusted=true) { const e={target:new Element(id),isTrusted:trusted,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}};docHandlers.click(e);return e; }
  return {click,sent,window,confirmed,winHandlers,adapter};
}

for (const [page,button] of [[8,'startGooseBtn'],[9,'startBtn'],[10,'start-pencil'],[11,'startBtn'],[12,'start-book']]) {
  test(`p${page}: authentic start only`,()=>{
    const f=fixture('scene-p'+page);
    f.click(button,false); assert.equal(f.sent.length,0);
    f.click(button,true); assert.equal(JSON.stringify(f.sent),JSON.stringify([{name:'start'}]));
  });
}
test('unready blocks page input and sends nothing',()=>{
  const f=fixture('scene-p9',false), e=f.click('startBtn');
  assert.equal(e.prevented,true);assert.equal(e.stopped,true);assert.equal(f.sent.length,0);
});
test('p11 restore requires exact server progress and picture/text support',()=>{
  const f=fixture('scene-p11');
  const supports=[{picture:true,text:true},{picture:false,text:false},{picture:false,text:false}];
  let state={feedbackPhase:'ready',domainState:{mode:0,practiceSaved:[false,false,false],supports}};
  f.window.miraActivityCheckpoint={capture:()=>state};
  const restore=f.winHandlers['mira-course-operation-restore'];
  const server={phase:'ready',completed:false,mode:0,saved:[],supports};
  restore({detail:{sceneId:'scene-p11',serverState:server}});
  restore({detail:{sceneId:'scene-p11',serverState:{...server,phase:'playing'}}});
  state={feedbackPhase:'playing',domainState:{mode:1,practiceSaved:[true,false,false],supports}};
  restore({detail:{sceneId:'scene-p11',serverState:{...server,phase:'playing',mode:1,saved:[0]}}});
  restore({detail:{sceneId:'scene-p11',serverState:{...server,phase:'playing',mode:1,saved:[0],supports:[]}}});
  assert.deepEqual(f.confirmed,[true,false,true,false]);
});

test('p9 restore requires exact server context, choice and completed contexts',()=>{
  const f=fixture('scene-p9');
  f.window.miraActivityCheckpoint={capture:()=>({feedbackPhase:'playing',domainState:{context:1,selectedTone:2,completedContexts:[0]}})};
  const restore=f.winHandlers['mira-course-operation-restore'];
  const server={phase:'playing',completed:false,context:1,tone:2,completedContexts:[0]};
  restore({detail:{sceneId:'scene-p9',serverState:server}});
  restore({detail:{sceneId:'scene-p9',serverState:{...server,tone:4}}});
  assert.deepEqual(f.confirmed,[true,false]);
});

test('p10 restore compares server strokes and completed characters without replay',()=>{
  const f=fixture('scene-p10');
  const points=[{x:0.2,y:0.3},{x:0.4,y:0.5}];
  f.window.miraActivityCheckpoint={capture:()=>({domainState:{phase:'playing'},childDecision:{currentChar:'ren',
    currentVersion:[points],versionA:[points],versionB:[],completedChars:[]}})};
  const restore=f.winHandlers['mira-course-operation-restore'];
  const server={phase:'playing',completed:false,character:'ren',strokes:[[[0.2,0.3],[0.4,0.5]]],
    versions:{ren:[[[0.2,0.3],[0.4,0.5]]],da:[]},completedChars:[]};
  restore({detail:{sceneId:'scene-p10',serverState:server}});
  restore({detail:{sceneId:'scene-p10',serverState:{...server,character:'da'}}});
  assert.deepEqual(f.confirmed,[true,false]);assert.equal(f.sent.length,0);
});

test('p8 restores in-progress and completed formations only when all recorded positions match',()=>{
  const f=fixture('scene-p8'), places=[[175,150],[475,330],[775,160],[300,425],[640,455],[840,355],[420,145]];
  const geese=places.map(([x,y],id)=>({id,x,y,directionAngle:-90,isLeader:id===0}));
  let domain={started:true,phase:'next_level_or_summary',level:2,flightAngle:-90,leaderId:0,order:['人','一'],geese,
    previousLegs:[{level:1,formationType:'人',leaderId:0,positions:geese}]};
  const server={phase:'playing',completed:false,level:2,flightAngle:-90,leader:0,order:['人','一'],positions:places,
    previousLegs:[{formation:'人',leader:0,positions:places}]};
  f.window.miraActivityCheckpoint={capture:()=>({domainState:domain})};
  const restore=f.winHandlers['mira-course-operation-restore'];
  restore({detail:{sceneId:'scene-p8',serverState:server}});
  const rounded=places.map(v=>[...v]);rounded[1]=[474.999808,330.000192];
  restore({detail:{sceneId:'scene-p8',serverState:{...server,positions:rounded}}});
  restore({detail:{sceneId:'scene-p8',serverState:{...server,leader:1}}});
  restore({detail:{sceneId:'scene-p8',serverState:{...server,previousLegs:[]}}});
  domain={...domain,phase:'level_complete'};
  restore({detail:{sceneId:'scene-p8',serverState:{...server,completed:true,phase:'complete'}}});
  assert.deepEqual(f.confirmed,[true,true,false,false,true]);assert.equal(f.sent.length,0);
});

test('p12 restores both saved observation works only when drafts and undo history agree',()=>{
  const f=fixture('scene-p12');
  const empty={selectedObject:null,color:null,quantity:0,direction:'right',action:'still',positions:[]};
  const leaf={selectedObject:'plant',color:'#C96A35',quantity:1,direction:'right',action:'still',positions:[{x:18,y:28}]};
  const bird={selectedObject:'animal',color:'#8B6B4E',quantity:1,direction:'right',action:'still',positions:[{x:18,y:28}]};
  const domain={started:true,feedbackPhase:'level_complete',currentVersionPage:'b',drafts:{a:leaf,b:bird},
    versions:{a:{childDecision:leaf,savedAt:10},b:{childDecision:bird,savedAt:11}},
    revisionHistory:[{version:'a',before:empty},{version:'b',before:empty}]};
  const server={phase:'complete',completed:true,page:'b',drafts:{a:leaf,b:bird},versions:{a:leaf,b:bird},
    history:[{page:'a',before:empty},{page:'b',before:empty}]};
  f.window.miraActivityCheckpoint={capture:()=>({domainState:domain})};
  const restore=f.winHandlers['mira-course-operation-restore'];
  restore({detail:{sceneId:'scene-p12',serverState:server}});
  domain.feedbackPhase='revise_or_retry';
  restore({detail:{sceneId:'scene-p12',serverState:{...server,phase:'playing'}}});
  domain.feedbackPhase='level_complete';
  restore({detail:{sceneId:'scene-p12',serverState:{...server,versions:{a:leaf,b:leaf}}}});
  restore({detail:{sceneId:'scene-p12',serverState:{...server,history:[{page:'a',before:empty}]}}});
  restore({detail:{sceneId:'scene-p12',serverState:{...server,completed:false}}});
  assert.deepEqual(f.confirmed,[true,true,false,false,false]);assert.equal(f.sent.length,0);
});
