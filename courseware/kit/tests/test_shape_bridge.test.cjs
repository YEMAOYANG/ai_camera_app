const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');

const kit=path.join(__dirname,'..');
const read=file=>JSON.parse(fs.readFileSync(path.join(kit,file),'utf8'));
const bridge=read('examples/classic-arcade/shape-bridge.json');
const roofs=read('examples/alternate/shape-bridge-roofs.json');
const script=fs.readFileSync(path.join(kit,'game_templates/shapeBridge.js'),'utf8');
const dt=1/60;

function play(level){
  const K={gameTemplates:{}};
  const Classic={
    create:(_,mechanic)=>mechanic,
    bot:(...keys)=>({press:key=>keys.includes(key),held:key=>keys.includes(key)}),
    clamp:(value,min,max)=>Math.min(max,Math.max(min,value)),
    ease:(_,target)=>target
  };
  vm.runInNewContext(script,{K,Classic});
  const rules=K.gameTemplates.shapeBridge({});
  rules.validate(level);
  const world=rules.reset(level);
  let awards=0,misses=0;
  const feedback={
    award(){awards++;},lost(){rules.adapt(world,++misses);},
    move(){},fx(){},jump(){},drop(){}
  };
  function step(input){rules.update(world,level,input,dt,feedback);}
  return {
    world,
    get awards(){return awards;},
    get misses(){return misses;},
    press(...keys){step(Classic.bot(...keys));},
    idle(frames){for(let i=0;i<frames;i++)step(Classic.bot());},
    pilot(){
      for(let i=0;i<1800&&awards<rules.goal(level);i++)step(rules.pilot(world,level,dt));
    }
  };
}

test('two layouts use the same rotation and placement rules across every level',()=>{
  for(const sample of [bridge,roofs]){
    for(const level of sample.levels){
      const game=play(level);
      game.pilot();
      assert.equal(game.awards,level.slots.length);
      assert.equal(game.world.filled.size,level.slots.length);
      assert.equal(game.misses,0);
    }
  }
});

test('the right column and same number of squares cannot compensate for an incorrect turn',()=>{
  const game=play(bridge.levels[1]);
  for(let i=0;i<5;i++)game.press('left');
  assert.equal(game.world.col,0);
  game.press('action');
  assert.equal(game.awards,0);
  assert.equal(game.misses,1);
  game.idle(35);
  game.press('action');
  assert.equal(game.misses,2);
  assert.equal(game.world.help,true);
  game.idle(35);
  const start=game.world.fall;
  game.idle(60);
  assert.ok(game.world.fall-start<1/bridge.levels[1].seconds);
  for(let i=0;i<3;i++)game.press('up');
  for(let i=0;i<5;i++)game.press('left');
  game.press('action');
  assert.equal(game.awards,1);
  assert.deepEqual([...game.world.filled],[0]);
});

test('two equivalent openings may be filled out of order without leaving a dead end',()=>{
  const game=play(roofs.levels[1]);
  for(let i=0;i<5;i++)game.press('right');
  game.press('left');
  assert.equal(game.world.col,6);
  game.press('up');
  game.press('action');
  assert.equal(game.awards,1);
  assert.deepEqual([...game.world.filled],[1]);
  game.pilot();
  assert.deepEqual([...game.world.filled],[1,0]);
  assert.equal(game.misses,0);
});

test('an overlap or a disconnected footprint fails when authoring the level',()=>{
  const source=bridge.levels[0];
  assert.throws(()=>play({...source,slots:[source.slots[0],{...source.slots[1],col:1}]}),/must not overlap/);
  assert.throws(()=>play({...source,slots:[{col:1,cells:[[0,0],[2,2]]},source.slots[1]]}),/must be connected/);
});
