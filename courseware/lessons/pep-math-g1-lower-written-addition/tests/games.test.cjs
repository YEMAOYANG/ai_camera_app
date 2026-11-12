const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const lesson = require('../lesson.json');
const templates = path.join(root, '../../kit/game_templates');
const tick = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  const K = {gameTemplates:{}, ready(){}, stage:()=>({append(){}}), $(){}, game(result){return result;}};
  const Classic = {
    bot, create:(config,rules)=>({config,rules}),
    clamp:(x,min,max)=>Math.min(Math.max(x,min),max),
    validToken:value=>typeof value==='string' && value.length>0,
    match:(from,to,level)=>level.pairs.some(([a,b])=>a===from&&b===to),
  };
  const context=vm.createContext({K,Classic,requestAnimationFrame(){}});
  vm.runInContext(fs.readFileSync(path.join(templates,template+'.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'pages',page+'.js'),'utf8'),context);
  return {...vm.runInContext('activity',context),bot};
}

function play({rules,config,bot}, index) {
  const level=config.levels[index];
  rules.validate(level,index);
  const world=rules.reset(level);
  const result={awards:0,misses:0};
  function update(input) {
    rules.update(world,level,input,tick,{
      award(){result.awards++;},
      lost(){result.misses++;rules.adapt(world,result.misses);},
      fx(){},move(){},drop(){},jump(){},resetCheckpoint(){},
    });
  }
  return {
    world,result,
    press(key, frames=1){for(let n=0;n<frames;n++)update(key?bot(key):bot());},
    finish(){
      for(let frame=0;frame<1800 && result.awards<rules.goal(level);frame++){
        update(rules.pilot(world,level,tick));
      }
      assert.equal(result.awards,rules.goal(level));
    },
  };
}

test('sorted docks follow the sum of ones; a wrong dock gives no award',()=>{
  const game=load('sortingDepot','sort-by-ones');
  for(const level of game.config.levels){
    for(const item of level.items){
      const [a,b]=item.token.split('-').slice(1).map(Number);
      assert.equal(item.group,a+b<10?'under':'full');
      assert.ok(lesson.images[item.token]);
    }
  }
  const wrong=play(game,0);
  wrong.press('right',48);
  wrong.press('down');
  assert.deepEqual(wrong.result,{awards:0,misses:1});
  assert.equal(wrong.world.help,false);
  const first=play(game,0);
  first.press('down',24);
  first.press('right',48);
  assert.deepEqual(first.result,{awards:1,misses:0});
  assert.equal(first.world.state.items[0],-(2*7+4)-1);
  for(let run=0;run<2;run++)for(let i=0;i<3;i++)play(game,i).finish();
});

test('marble uses one exact total per source card and rejects a wrong visible target',()=>{
  const game=load('magnetMarbles','pair-check');
  for(const level of game.config.levels){
    for(const entry of level.queue){
      const [a,b]=entry.slice(1).split('-').map(Number);
      const matched=level.targets.filter(t=>level.pairs.some(([source,total])=>source===entry&&total===t.value));
      assert.deepEqual([...matched].map(x=>x.value),[String(a+b)]);
      assert.ok(lesson.images[entry]&&lesson.images['result-'+(a+b)]);
    }
  }
  const wrong=play(game,0);
  wrong.press('left',25);
  wrong.press('action');
  wrong.press(null,65);
  assert.deepEqual(wrong.result,{awards:0,misses:1});
  assert.equal(wrong.world.help,false);
  const first=play(game,0);
  first.press('action');
  first.press(null,65);
  assert.deepEqual(first.result,{awards:1,misses:0});
  assert.equal(first.world.locked.value,'35');
  for(let run=0;run<2;run++)for(let i=0;i<3;i++)play(game,i).finish();
});
