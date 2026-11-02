const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const source=fs.readFileSync(require('node:path').join(__dirname,'math-split-add.js'),'utf8');
function fixture(page=2,kind='math-add',initial={round:0,prediction:null,gates:[false,false]}) {
  const handlers={},sent=[],confirmed=[],events=[],timers=new Map();let seq=0,snapshot=initial,resolve;
  class Element {constructor(selector){this.selector=selector;}closest(selectors){return selectors.split(',').includes(this.selector)?this:null;}}
  const document={addEventListener:(n,f)=>handlers[n]=f,removeEventListener:n=>delete handlers[n]};
  const window={miraActivityCheckpoint:{capture:()=>snapshot},dispatchEvent:e=>events.push(e.type),miraCourseOperation:{ready:true,restoreConfirmed:x=>confirmed.push(x),send:op=>{sent.push(op);return new Promise(r=>resolve=r);}}};
  const capture=window.miraActivityCheckpoint.capture;
  vm.runInNewContext(source,{window,document,Element,Event:class{constructor(type){this.type=type;}},CustomEvent:class{constructor(type){this.type=type;}},setTimeout:f=>{timers.set(++seq,f);return seq;},clearTimeout:id=>timers.delete(id)});
  const adapter=window.installSplitAddCourseAdapter('scene-p'+page,kind);
  return {adapter,window,sent,confirmed,events,capture,set:s=>snapshot=s,restore:w=>adapter.restore({kind,validator:kind+'-p'+page+'.v1',lastWork:w}),flush:()=>{const all=[...timers.values()];timers.clear();all.forEach(f=>f());},ack:async()=>{resolve();await Promise.resolve();},click:(selector,trusted=true)=>{let blocked=false;handlers.click({type:'click',isTrusted:trusted,target:new Element(selector),preventDefault(){blocked=true;},stopImmediatePropagation(){}});return blocked;}};
}
test('only a fresh or matching restored work state is authorized',()=>{
 const f=fixture();f.restore(null);assert.deepEqual(f.confirmed,[true]);
 f.click('#gate');f.set({round:0,prediction:3,gates:[true,true],completed:true,mastered:true});f.flush();
 assert.equal(f.sent[0].name,'submit');assert.deepEqual(Object.keys(f.sent[0].work),['round','prediction','gates']);
 assert.equal(f.window.miraActivityCheckpoint.capture(),null);assert.equal(f.click('#gate'),true);
 f.adapter.dispose();assert.equal(f.window.miraActivityCheckpoint.capture,f.capture);
 const mismatch=fixture();mismatch.restore({round:1,prediction:4,gates:[true,true]});assert.deepEqual(mismatch.confirmed,[false]);assert.equal(mismatch.click('#gate'),true);mismatch.flush();assert.equal(mismatch.sent.length,0);
});
test('acknowledgement releases checkpoint; replay and untrusted input are quiet',async()=>{
 const f=fixture();f.restore(null);f.click('#gate',false);f.flush();assert.equal(f.sent.length,0);
 f.click('#gate');f.set({round:0,prediction:3,gates:[true,false]});f.flush();assert.equal(f.sent[0].name,'work');await f.ack();
 assert.equal(f.window.miraActivityCheckpoint.capture().prediction,3);assert.ok(f.events.includes('mira-activity-state-changed'));
 f.click('#replay');f.flush();assert.equal(f.sent.length,1);
});
test('transient animation snapshots are retried without saving a partial state',()=>{
 const f=fixture();f.restore(null);f.click('#gate');f.set(null);f.flush();assert.equal(f.sent.length,0);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
 f.set({round:0,prediction:3,gates:[true,true]});f.flush();assert.equal(f.sent.length,1);
});
test('creation submits actual parts and equation, excluding saved completion claims',()=>{
 const f=fixture(11,'math-add',{part1:[],part2:[],equation:{num1:null,num2:null,total:null}});f.restore(null);
 f.click('#saveBtn');f.set({part1:[{id:'a',prop:'boat'}],part2:[{id:'b',prop:'boat'}],equation:{num1:1,num2:1,total:3},savedVersion:'fake',completed:true});f.flush();
 assert.equal(f.sent[0].name,'submit');assert.equal(f.sent[0].work.equation.total,3);assert.equal(f.sent[0].work.completed,undefined);
});
