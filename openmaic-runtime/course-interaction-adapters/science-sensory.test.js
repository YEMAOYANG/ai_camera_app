const assert = require('node:assert/strict');
const test = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, 'science-sensory.js'), 'utf8');
function fixture(page = 2) {
  const handlers = {}, sent = [], confirmations = [], timers = new Map(); let tid = 0, busy = false;
  let state = {page, started:false, phase:0, selected:'', channels:[], clues:[], excluded:[], guess:'', firstGuess:'',
    revealed:false, revised:false, rotation:0, force:1, probes:[], direction:0, heard:[], links:{}, route:[], robot:0, help:0,
    complete:true, mastery:true, attempts:[]};
  class Element {
    constructor(id) {this.id = id; this.dataset = ['begin','reset','help','replay'].includes(id) ? {} : {act:id};}
    closest() {return this;}
  }
  const checkpoint=Object.freeze({version:1,capture:()=>busy?null:JSON.parse(JSON.stringify({schemaVersion:'mira.science.sensory-lab.v1',state}))});
  const window={miraActivityCheckpoint:checkpoint,dispatchEvent(){},miraCourseOperation:{ready:true,
    restoreConfirmed:x=>confirmations.push(x),send:op=>{sent.push(op);return Promise.resolve();}}};
  const document={addEventListener:(n,f)=>handlers[n]=f,removeEventListener:n=>delete handlers[n]};
  vm.runInNewContext(source,{window,document,Element,Event:class{},CustomEvent:class{},
    setTimeout:f=>{timers.set(++tid,f);return tid;},clearTimeout:id=>timers.delete(id)});
  const adapter=window.installScienceSensoryAdapter('scene-p'+page);
  return {window,adapter,sent,confirmations,state,busy:x=>busy=x,
    restore:()=>adapter.restore({kind:'science-sensory',validator:'science-sensory-p'+page+'.v1',lastWork:null}),
    event:(id,trusted=true)=>handlers.click({type:'click',isTrusted:trusted,target:new Element(id),preventDefault(){},stopImmediatePropagation(){}}),
    flush:async()=>{const batch=[...timers.values()];timers.clear();batch.forEach(f=>f());await Promise.resolve();}};
}
test('waits for real audio completion and prevents premature checkpoint persistence',async()=>{
  const f=fixture();f.restore();assert.deepEqual(f.confirmations,[true]);
  f.event('begin');f.state.started=true;f.busy(true);await f.flush();
  assert.equal(f.sent.length,0);assert.equal(f.window.miraActivityCheckpoint.capture(),null);
  f.busy(false);await f.flush();assert.equal(f.sent.length,1);assert.equal(f.sent[0].action,'start');
  assert.equal('complete' in f.sent[0].work,false);assert.equal('mastery' in f.sent[0].work,false);
});
test('interrupted simulation earns no heard sound operation',async()=>{
  const f=fixture(9);f.restore();f.state.started=true;f.event('listen');f.busy(true);await f.flush();
  f.busy(false);await f.flush();assert.equal(f.sent.length,0);
  f.event('listen');f.state.heard.push('bird');f.state.attempts.push({action:'bird'});await f.flush();
  assert.equal(f.sent.length,1);assert.equal(f.sent[0].action,'listen');
});
test('untrusted input and mismatched restore never report operations',async()=>{
  const f=fixture();f.restore();f.event('begin',false);await f.flush();assert.equal(f.sent.length,0);
  f.adapter.restore({kind:'science-sensory',validator:'science-sensory-p2.v1',lastWork:{started:true}});
  f.event('eye');await f.flush();assert.equal(f.sent.length,0);assert.equal(f.confirmations.at(-1),false);
});
