const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname,'english-classroom.js'),'utf8');
function fixture() {
  const handlers={}, sent=[], confirmed=[], timers=new Map(); let tid=0;
  let shot={version:1,page:2,round:0,seed:3,started:false,poses:[0,0],door:0,window:0,selected:0,
    turnSwap:0,lastAction:null,oral:'none',chosen:'stand',route:[],completed:[0,1,2,3],mastered:true};
  class Element {constructor(selector){this.selector=selector;}closest(s){return s==='#stage'||s.split(',').includes(this.selector)?this:null;}}
  const window={miraActivityCheckpoint:{capture:()=>shot},dispatchEvent:()=>{},miraCourseOperation:{ready:true,
    restoreConfirmed:x=>confirmed.push(x),send:op=>{sent.push(op);return Promise.resolve();}}};
  const document={addEventListener:(n,f)=>handlers[n]=f,removeEventListener:n=>delete handlers[n]};
  vm.runInNewContext(source,{window,document,Element,Event:class{},CustomEvent:class{},
    setTimeout:f=>{timers.set(++tid,f);return tid;},clearTimeout:id=>timers.delete(id)});
  const adapter=window.installEnglishClassroomAdapter('scene-p2');
  return {adapter,sent,confirmed,window,get:()=>shot,set:s=>shot=s,
    event:(sel,trusted=true)=>handlers.click({type:'click',isTrusted:trusted,target:new Element(sel),preventDefault(){},stopImmediatePropagation(){}}),
    flush:async()=>{const batch=[...timers.values()];timers.clear();batch.forEach(f=>f());await Promise.resolve();}};
}
test('animation/audio defers a genuine submit and strips forged completion flags',async()=>{
  const f=fixture();f.adapter.restore({kind:'english-classroom',validator:'english-classroom-p2.v1',lastWork:null});
  assert.deepEqual(f.confirmed,[true]);let s={...f.get(),started:true};f.set(s);f.event('#check');
  f.set(null);await f.flush();assert.equal(f.sent.length,0);
  f.set({...s,poses:[1,0],lastAction:{cmd:'stand',actor:0}});await f.flush();
  assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'submit');
  assert.equal('completed' in f.sent[0].work,false);assert.equal('mastered' in f.sent[0].work,false);
});
test('untrusted input and stale restoration never produce course credit',async()=>{
  const f=fixture();f.adapter.restore({kind:'english-classroom',validator:'english-classroom-p2.v1',lastWork:{round:3}});
  assert.deepEqual(f.confirmed,[false]);f.event('#check');await f.flush();assert.equal(f.sent.length,0);
  f.adapter.restore({kind:'english-classroom',validator:'english-classroom-p2.v1',lastWork:null});
  f.event('#check',false);await f.flush();assert.equal(f.sent.length,0);
  f.set({...f.get(),started:true});f.event('#replay');await f.flush();assert.equal(f.sent[0].name,'help');
});
