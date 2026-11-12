const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

function load(name) {
  let rules;
  const noop = () => {};
  const K = {ready:noop, hud:noop, sfx:{buzz:noop,pick:noop}, game(options) { rules = options; }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'..','pages',name+'.js'),'utf8'), {K,Image:class {}});
  return rules;
}
function play(rules,level) {
  const g = {
    level, levelMisses:0, taps:[], pointer:{x:0,y:0,down:false}, won:false,
    miss() { this.levelMisses++; },
    say(message,kind) { this.speech={message,kind}; },
    sparkle() {},
    win() { this.won=true; }
  };
  rules.reset(g,level);
  return g;
}
function tick(rules,g,frame,pilot=false) {
  if (pilot) rules.autopilot(g,frame);
  rules.update(g,frame);
  g.taps.length=0;
}
function followCircle(rules,g,sign) {
  for (let i=1;i<=194&&!g.won;i++) {
    const angle=sign*Math.min(2*Math.PI,2*Math.PI*i/172);
    g.pointer.x=783+146*Math.cos(angle);
    g.pointer.y=427+146*Math.sin(angle);
    tick(rules,g,1/60);
  }
}

test('both pilots complete each level twice with the human frame rules',()=>{
  for (const name of ['circle','cup']) {
    const rules=load(name);
    for (let attempt=0;attempt<2;attempt++) {
      for (let level=0;level<rules.levels;level++) {
        const g=play(rules,level);
        for (let i=0;i<1300&&!g.won;i++) tick(rules,g,1/60,true);
        assert.equal(g.won,true,name+' level '+(level+1));
        assert.equal(g.levelMisses,name==='cup'?1:0);
      }
    }
  }
});

test('teacher demo awards no child stars and student play keeps all stars',()=>{
  for (const name of ['circle','cup']) {
    const rules=load(name);
    assert.equal(rules.starsFor({autoLoop:true}),0);
    assert.equal(rules.starsFor({autoLoop:false}),3);
  }
});

test('a pen shortcut cannot jump the circle and either direction is playable',()=>{
  const rules=load('circle');
  for (const sign of [-1,1]) {
    const g=play(rules,0);
    Object.assign(g.pointer,{x:929,y:427,down:true});
    tick(rules,g,1/60);
    Object.assign(g.pointer,{x:783,y:427});
    tick(rules,g,1/60);
    assert.equal(g.data.sweep,0);
    assert.equal(g.levelMisses,1);
    assert.match(g.speech.message,/看看笔和绳/);
    followCircle(rules,g,sign);
    assert.equal(g.won,true);
    assert.equal(rules.starsFor(g),3);
  }
});

test('the larger circle needs a longer rope before any line can be drawn',()=>{
  const rules=load('circle');
  const g=play(rules,1);
  Object.assign(g.pointer,{x:904,y:427,down:true});
  tick(rules,g,1/60);
  Object.assign(g.pointer,{x:904,y:477});
  tick(rules,g,1/60);
  assert.equal(g.data.sweep,0);
  assert.equal(g.data.adjusted,false);
  Object.assign(g.pointer,{x:971,y:427});
  tick(rules,g,1/60);
  assert.equal(g.data.radius,188);
  assert.equal(g.data.adjusted,true);
  assert.equal(g.data.blocked,true);
  assert.equal(g.data.sweep,0);
});

test('teacher handoff releases the virtual pointer before the first child press',()=>{
  const rules=load('circle');
  const g=play(rules,0);
  tick(rules,g,1/60,true);
  assert.equal(g.pointer.down,true);
  rules.reset(g,0);
  assert.equal(g.pointer.down,false);
  Object.assign(g.pointer,{x:929,y:427,down:true});
  tick(rules,g,1/60);
  assert.ok(g.data.grip);
});

test('cannot swap untested stock or confuse a broad curled mat with a flat small one',()=>{
  const rules=load('cup');
  const g=play(rules,2);
  g.taps.push({x:1080,y:337});
  tick(rules,g,1/60);
  assert.equal(g.data.wide,false);
  for (let i=0;i<200&&!g.data.observation;i++) tick(rules,g,1/60,true);
  assert.equal(g.data.observation.covers,false);
  assert.equal(g.data.observation.flat,false);
  assert.match(g.speech.message,/看看垫边/);
  g.taps.push({x:1080,y:548});
  tick(rules,g,1/60);
  assert.equal(g.data.flat,false);
  for (let i=0;i<650&&!g.won;i++) tick(rules,g,1/60,true);
  assert.equal(g.won,true);
  assert.equal(g.data.wide,true);
  assert.equal(g.data.flat,true);
});
