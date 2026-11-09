const {test}=require('node:test');
const assert=require('node:assert/strict');
const boat=require('../pages/p03.js');
const trace=require('../pages/p04.js');
const pond=require('../pages/x04.js');
test('boat collection cannot finish before three real pushes; reset restores the journey',()=>{
 let s=boat.initial();s=boat.next(s,'collect');assert.equal(s.finished,false);assert.equal(s.pushes,0);assert.equal(s.misses,1);
 for(let i=0;i<3;i++)s=boat.next(s,'push');assert.equal(s.finished,false);
 s=boat.next(s,'collect');assert.equal(s.finished,true);assert.deepEqual(boat.next(s,'reset'),boat.initial());
});
test('unknown and teacher demo events cannot grant boat progress',()=>{
 const s=boat.initial();assert.strictEqual(boat.next(s,'demo'),s);assert.strictEqual(boat.next(s,'unknown'),s);
});
test('trace choices cannot finish before the physical change and wrong answers preserve retry',()=>{
 let s=trace.initial();s=trace.next(s,'path');assert.equal(s.finished,false);assert.equal(s.opened,false);
 s=trace.next(s,'spread');s=trace.next(s,'boat');assert.equal(s.finished,false);assert.equal(s.opened,true);
 s=trace.next(s,'path');assert.equal(s.finished,true);assert.deepEqual(trace.next(s,'reset'),trace.initial());
});
test('teacher trace demo does not become learner evidence',()=>{
 const s=trace.initial();assert.strictEqual(trace.next(s,'demo'),s);
});
test('small pond must visit four distinct poem objects in order; wrong targets leave progress recoverable',()=>{
 let s=pond.initial();s=pond.next(s,'dragonfly');assert.equal(s.index,0);assert.equal(s.finished,false);
 for(const event of ['spring','shade','lotus'])s=pond.next(s,event);
 assert.equal(s.finished,false);s=pond.next(s,'spring');assert.equal(s.index,3);
 s=pond.next(s,'dragonfly');assert.equal(s.finished,true);assert.deepEqual(pond.next(s,'reset'),pond.initial());
});
