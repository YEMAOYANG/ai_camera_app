const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root=path.join(__dirname,'..');
const templates=path.join(root,'../../kit/game_templates');
const lesson=require('../lesson.json');
const dt=1/60;

function load(template,page) {
  const bot=(...keys)=>({press:key=>keys.includes(key),held:key=>keys.includes(key)});
  let activity;
  const K={gameTemplates:{},ready(){},stage:()=>({append(){}}),$(){},game(result){activity=result;}};
  const Classic={
    bot,create:(config,rules)=>({config,rules}),ease:(_,target)=>target,
    validToken:value=>typeof value==='string'&&value.length>0,
    clamp:(n,min,max)=>Math.min(max,Math.max(min,n)),
    match:(cue,value,level)=>level.pairs.some(([input,answer])=>input===cue&&answer===value),
  };
  const context=vm.createContext({K,Classic});
  vm.runInContext(fs.readFileSync(path.join(templates,template+'.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(root,'pages',page+'.js'),'utf8'),context);
  const audio=lesson.scenes.find(scene=>scene.page===page).gameAudio;
  const speech=cue=>{
    const ref=audio[cue];
    const split=ref.lastIndexOf('-');
    return lesson.scenes.find(scene=>scene.key===ref.slice(0,split)).script[Number(ref.slice(split+1))-1].say;
  };
  return {...activity,bot,speech};
}

function play({rules,config,bot},index) {
  const level=config.levels[index];
  rules.validate(level,index);
  const world=rules.reset(level);
  const score={awards:0,misses:0};
  const update=(input,seconds=dt)=>rules.update(world,level,input,seconds,{
    award(){score.awards++;},
    lost(){score.misses++;rules.adapt(world,score.misses);},
    fx(){},move(){},drop(){},jump(){},resetCheckpoint(){},
  });
  function finish() {
    for(let frame=0;frame<3600&&score.awards<rules.goal(level);frame++){
      update(rules.pilot(world,level,dt));
    }
    assert.equal(score.awards,rules.goal(level));
  }
  return {world,score,finish,press:(key,seconds)=>update(bot(key),seconds)};
}

test('only the object imagined by each character accepts its role card',()=>{
  const game=load('sortingDepot','role-depot');
  const story={drop:'cradle',fly:'pad',frog:'stage',fish:'shade'};
  const wrong=play(game,0);
  for(const key of ['up','right','right','down','down','left','right','up','up','left','left',
    'down','right','up','right','down','left','down','right']){
    wrong.press(key,.33);
  }
  assert.deepEqual(wrong.score,{awards:0,misses:1});
  assert.equal(wrong.world.wrongGroup,'cradle');
  assert.equal(wrong.world.help,false);
  for(const [index,level] of game.config.levels.entries()){
    for(const item of level.items){
      assert.equal(item.group,story[item.token]);
      assert.equal(level.docks.filter(dock=>dock.sample===item.group).length,1);
    }
    const session=play(game,index);
    session.finish();
    assert.ok(session.world.state.items.every(value=>value<0));
  }
});

test('spoken actions control the marble target, with no hint on a first miss',()=>{
  const game=load('magnetMarbles','pond-marbles');
  const cueWords={'listen-lie':'躺','listen-spread':'翅膀','listen-crouch':'蹲','listen-swim':'下面游'};
  const wrong=play(game,0);
  wrong.press('action');
  for(let i=0;i<55;i++)wrong.press();
  assert.deepEqual(wrong.score,{awards:0,misses:1});
  assert.equal(wrong.world.help,false);
  for(const [index,level] of game.config.levels.entries()){
    assert.equal(level.listenOnly,true);
    assert.deepEqual([...game.config.cues[index].steps],[...level.queue]);
    for(const [i,cue] of level.queue.entries()){
      assert.match(game.speech(game.config.cues[index].steps[i]),new RegExp(cueWords[cue]));
    }
    for(let i=1;i<level.targets.length;i++){
      assert.ok(level.targets[i].x-level.targets[i-1].x>=level.targetWidth+2*level.drift);
    }
    const session=play(game,index);
    session.finish();
    assert.equal(session.world.i,level.queue.length);
  }
});
