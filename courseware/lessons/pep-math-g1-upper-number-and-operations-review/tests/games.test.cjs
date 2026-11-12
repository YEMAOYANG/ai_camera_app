const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const templates = path.join(root, '../../kit/game_templates');
const lesson = require('../lesson.json');
const dt = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  const K = {gameTemplates:{}, ready(){}, stage:()=>({append(){}}), $(){}, game(result){game=result;}};
  const Classic = {
    bot, create:(config,rules)=>({config,rules}), ease:(_,target)=>target,
    validToken:value=>Number.isFinite(value),
    match:(first,second,level)=>first+second===level.total,
  };
  const context=vm.createContext({K,Classic});
  vm.runInContext(fs.readFileSync(path.join(templates,template+'.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'pages',page+'.js'),'utf8'),context);
  return {...game,bot};
}

function play({rules,config,bot}, index) {
  const level=config.levels[index];
  rules.validate(level,index);
  const world=rules.reset(level);
  const score={awards:0,misses:0};
  function update(input, seconds=dt) {
    rules.update(world,level,input,seconds,{
      award(){score.awards++;},
      lost(){score.misses++;rules.adapt(world,score.misses);},
      fx(){},move(){},drop(){},
    });
  }
  function finish() {
    for(let frame=0;frame<3600 && score.awards<rules.goal(level);frame++){
      update(rules.pilot(world,level,dt));
    }
    assert.equal(score.awards,rules.goal(level));
  }
  return {world,score,finish,press:(key,seconds)=>update(bot(key),seconds)};
}

test('snake rejects fewer stamps when it asks for more, then can finish all rounds', () => {
  const game=load('compareSnake','compare-stamps');
  const mismatch=play(game,0);
  mismatch.press('right');
  mismatch.press('right',.8);
  mismatch.press('up',.8);
  assert.deepEqual(mismatch.score,{awards:0,misses:1});
  assert.equal(mismatch.world.help,false);
  const relation={gt:(n,r)=>n>r,lt:(n,r)=>n<r,eq:(n,r)=>n===r};
  for(const [i,level] of game.config.levels.entries()){
    let ref=level.start;
    for(const round of level.rounds){
      const candidates=round.foods.map(item=>item[2]).filter(n=>relation[round.relation](n,ref));
      assert.equal(candidates.length,1);
      ref=candidates[0];
      assert.ok(lesson.images['count-'+ref]);
    }
    const session=play(game,i);
    session.finish();
    assert.equal(session.world.ref,ref);
  }
});

test('a tile stacked above a partner gets no point, adjacent tens finish each board', () => {
  const game=load('fallingTiles','fill-ten-trays');
  const wrong=play(game,0);
  wrong.press('right');
  wrong.press('action');
  assert.deepEqual(wrong.score,{awards:0,misses:1});
  assert.equal(wrong.world.failureCount,1);
  for(const [i,level] of game.config.levels.entries()){
    assert.equal(level.total,10);
    const session=play(game,i);
    session.finish();
    assert.equal(session.world.i,level.pieces.length);
  }
});
