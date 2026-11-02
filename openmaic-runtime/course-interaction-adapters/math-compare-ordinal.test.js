const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname,'math-compare-ordinal.js'),'utf8');
function fixture() {
  const handlers={},sent=[],confirmed=[],timers=[];
  let snapshot={phase:0,order:['telescope','compass','magnifier','ruler','tweezers'],completed:[true,true]};
  class Element {closest(selector){return selector.split(',').includes('#check') ? this : null;}}
  const document={addEventListener:(n,f)=>handlers[n]=f,removeEventListener:n=>delete handlers[n]};
  const window={miraActivityCheckpoint:{capture:()=>snapshot},miraCourseOperation:{ready:true,restoreConfirmed:x=>confirmed.push(x),send:op=>{sent.push(op);return Promise.resolve();}}};
  vm.runInNewContext(source,{window,document,Element,setTimeout:f=>timers.push(f),JSON,Object,Array,Number,Promise});
  const adapter=window.installMathCourseAdapter('scene-p5','math-ordinal');
  return {adapter,window,sent,confirmed,handlers,set:s=>snapshot=s,flush:()=>timers.splice(0).forEach(f=>f()),click:trusted=>handlers.click({type:'click',isTrusted:trusted,target:new Element()})};
}
test('restores equivalent JSON object order and projects only work',()=>{
 const f=fixture();f.adapter.restore({kind:'math-ordinal',validator:'math-ordinal-p5.v1',lastWork:{order:['telescope','compass','magnifier','ruler','tweezers'],phase:0}});
 assert.deepEqual(f.confirmed,[true]);f.click(true);
 f.set({phase:0,order:['compass','telescope','magnifier','ruler','tweezers'],completed:[true,true],mastered:true});
 assert.equal(f.sent.length,0);f.flush();assert.equal(f.sent.length,1);assert.equal(f.sent[0].name,'submit');
 assert.deepEqual(Object.keys(f.sent[0].work),['phase','order']);assert.equal(f.sent[0].work.order[1],'telescope');
});
test('mismatched restoration, untrusted input and replay do not submit',()=>{
 const f=fixture();f.adapter.restore({kind:'math-ordinal',validator:'math-ordinal-p5.v1',lastWork:{phase:1,order:[]}});
 assert.deepEqual(f.confirmed,[false]);f.click(true);f.flush();assert.equal(f.sent.length,0);
 f.adapter.restore({kind:'math-ordinal',validator:'math-ordinal-p5.v1',lastWork:null});f.click(false);f.flush();assert.equal(f.sent.length,0);
 f.window.miraCourseOperation.ready=false;f.click(true);f.flush();assert.equal(f.sent.length,0);
 f.adapter.dispose();assert.deepEqual(Object.keys(f.handlers),[]);
});
