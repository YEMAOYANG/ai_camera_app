const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const test=require('node:test');
const vm=require('node:vm');

const kit=path.join(__dirname,'..');
const read=file=>JSON.parse(fs.readFileSync(path.join(kit,file),'utf8'));
const orchard=read('examples/classic-arcade/orchard-catch.json');
const snacks=read('examples/alternate/orchard-catch-snacks.json');
const source=fs.readFileSync(path.join(kit,'game_templates/orchardCatch.js'),'utf8');
const dt=1/60;

function play(level){
  const K={gameTemplates:{}};
  const sprites=[];
  const Classic={
    create:(_,mechanic)=>mechanic,
    bot:(...keys)=>({press:key=>keys.includes(key),held:key=>keys.includes(key)}),
    box(){},
    center:(...bounds)=>bounds,
    sprite(_,asset,x,y){sprites.push({asset,x,y});return true;},
    clamp:(value,min,max)=>Math.max(min,Math.min(max,value))
  };
  vm.runInNewContext(source,{K,Classic});
  const rules=K.gameTemplates.orchardCatch({});
  rules.validate(level);
  const world=rules.reset();
  let misses=0, points=0, resets=0;
  const feedback={
    move(){},drop(){},fx(){},
    award(){points++;},
    lost(){rules.adapt(world,++misses);},
    resetCheckpoint(){points=0;resets++;}
  };
  const run=(frames=1,...keys)=>{
    for(let i=0;i<frames;i++)rules.update(world,level,Classic.bot(...keys),dt,feedback);
  };
  return {
    world,rules,run,
    get misses(){return misses;},
    get points(){return points;},
    get resets(){return resets;},
    draw(){
      sprites.length=0;
      const ctx={stroke(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},fill(){}};
      rules.draw(world,level,ctx,{icons:new Map([['fruit','apple']]),frames:['cart']},{t:0});
      return sprites.filter(sprite=>sprite.asset==='apple');
    },
    autopilot(){
      for(let i=0;i<3200&&points<rules.goal(level);i++){
        rules.update(world,level,rules.pilot(world,level,dt),dt,feedback);
      }
    }
  };
}

test('the same movement rules fill both baskets for both lesson data sets',()=>{
  for(const example of [orchard,snacks]){
    for(const level of example.levels){
      const round=play(level);
      round.autopilot();
      assert.deepEqual(Array.from(round.world.fill),level.capacity);
      assert.equal(round.points,level.batches.length);
      assert.equal(round.misses,0);
    }
  }
});

test('an entire bunch fits or resets the level without silently splitting fruit',()=>{
  const round=play(orchard.levels[0]);
  round.run(38,'left');
  round.run(240);
  assert.deepEqual(Array.from(round.world.fill),[2,0]);
  assert.equal(round.points,1);
  round.run(76,'right');
  round.run(220);
  assert.equal(round.resets,1);
  assert.equal(round.points,0);
  assert.deepEqual(Array.from(round.world.fill),[0,0]);
  assert.equal(round.world.index,0);
  round.autopilot();
  assert.deepEqual(Array.from(round.world.fill),[2,3]);
});

test('missing the landing strip retries the same bunch and two misses slow the fall',()=>{
  const round=play(orchard.levels[0]);
  round.run(590);
  assert.equal(round.misses,2);
  assert.equal(round.world.help,true);
  assert.equal(round.world.index,0);
  assert.equal(round.resets,0);
  const prior=round.world.fall;
  round.run(65);
  const change=round.world.fall-prior;
  assert.ok(change>0&&change<65*dt/orchard.levels[0].seconds);
  round.autopilot();
  assert.equal(round.points,2);
});

test('the falling cluster, preview, and filled slots draw their actual counts',()=>{
  const round=play(orchard.levels[0]);
  let apples=round.draw();
  assert.equal(apples.filter(({y})=>y>225).length,2);
  assert.equal(apples.filter(({x,y})=>x>500&&x<800&&y<200).length,3);
  round.run(38,'left');round.run(240);
  apples=round.draw();
  assert.equal(apples.filter(({x,y})=>x<350&&y<220).length,2);
  assert.equal(apples.filter(({y})=>y>225).length,3);
});

test('a level with the right total can still be rejected if no whole-bunch split fits',()=>{
  const level={...orchard.levels[0],batches:[[1,0],[4,2]]};
  assert.throws(()=>play(level),/must fit both baskets/);
});
