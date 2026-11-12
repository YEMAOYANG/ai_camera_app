import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = path => readFileSync(new URL(path,import.meta.url),'utf8');
const lesson=JSON.parse(read('../lesson.json'));
const dt=1/60;
const noop=()=>{};

function load(page,template){
  let game;
  const removed=[];
  const K={ready:noop,$:()=>({style:{},addEventListener:noop}),
    $$:()=>[{classList:{remove:name=>removed.push(name)}}],
    game:value=>{game=value;}};
  const scope=vm.createContext({K,Image:class {},capture:(config,rules)=>({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js')+'\nClassic.create=capture;',scope);
  vm.runInContext(read('../../../kit/game_templates/'+template+'.js'),scope);
  vm.runInContext(read('../pages/'+page+'.js'),scope);
  return {...game,removed};
}

function play({rules},level){
  const world=rules.reset(level);
  const events=[];
  const feedback={award:()=>events.push('award'),lost:()=>events.push('lost'),
    fx:noop,move:noop,drop:noop,jump:noop,resetCheckpoint:()=>events.push('reset')};
  const step=(...keys)=>rules.update(world,level,{press:key=>keys.includes(key),held:()=>false},dt,feedback);
  const awards=()=>events.filter(x=>x==='award').length;
  function until(predicate,callback){
    for(let frame=0;frame<7200&&!predicate();frame++)callback(frame);
    assert.ok(predicate(),'real template rules did not reach the stop condition');
  }
  const pilot=()=>rules.update(world,level,rules.pilot(world,level,dt),dt,feedback);
  return {world,events,step,awards,until,pilot};
}

test('catching the entire fixed-size batch advances one bag; a too-small tray rejects it',()=>{
  const game=load('pack-exact','orchardCatch');
  for(const [i,level] of game.config.levels.entries()){
    game.rules.validate(level,i);
    const [full,remainder]=level.capacity;
    assert.equal(full%level.group,0);
    assert.ok(remainder<level.group);
    assert.deepEqual(Array.from(level.batches.slice(0,-1),b=>b[0]),Array(full/level.group).fill(level.group));
    assert.equal(level.batches.at(-1)[0],remainder);
    for(let round=0;round<2;round++){
      const run=play(game,level);
      run.until(()=>run.awards()===1,run.pilot);
      assert.deepEqual(Array.from(run.world.fill),[level.group,0]);
      run.until(()=>run.awards()===level.batches.length,run.pilot);
      assert.deepEqual(Array.from(run.world.fill),[full,remainder]);
      assert.ok(run.events.every(x=>x==='award'));
    }
  }
  const first=game.config.levels[0];
  const wrong=play(game,first);
  wrong.step('action');
  wrong.until(()=>wrong.events.includes('lost'),()=>wrong.step());
  assert.deepEqual(wrong.events,['lost','reset']);
  assert.deepEqual(Array.from(wrong.world.fill),[0,0]);
  assert.equal(wrong.world.index,0);
});

test('every route station equals the next remainder and the exit is earned only at the stop',()=>{
  const game=load('count-steps','bubbleMaze');
  const code=read('../pages/count-steps.js');
  const amounts=new Map([...code.matchAll(/([A-Z]):'__IMG:station-(\d+)__'/g)]
    .map(([,id,count])=>[id,Number(count)]));
  for(const [i,level] of game.config.levels.entries()){
    game.rules.validate(level,i);
    const values=Array.from(level.route,id=>amounts.get(id));
    assert.deepEqual(values,values.map((_,i)=>level.total-(i+1)*level.group));
    assert.ok(values.at(-1)>=0&&values.at(-1)<level.group);
    for(let round=0;round<2;round++){
      const run=play(game,level);
      run.until(()=>run.awards()===game.rules.goal(level),run.pilot);
      assert.ok(run.events.every(x=>x==='award'));
      assert.equal(run.world.i,values.length+1);
    }
  }
  const wrong=play(game,game.config.levels[0]);
  for(const key of ['right','right','right','right','up','right','right','down']){
    for(let frame=0;frame<26;frame++)wrong.step(...(frame===0?[key]:[]));
  }
  assert.deepEqual([wrong.world.x,wrong.world.y,wrong.world.i],[7,5,0]);
  assert.deepEqual(wrong.events,['lost']);
});

test('teachers start with speech, demonstrate against real anchors, and reset visual prompts',()=>{
  for(const [key,template] of [['pack-exact','orchardCatch'],['count-steps','bubbleMaze']]){
    const scene=lesson.scenes.find(x=>x.key===key);
    assert.ok(scene.script[0].say);
    assert.deepEqual(scene.script[1].setState,{demo:true,level:1,pause:true});
    assert.deepEqual(scene.script.at(-1).setState,{demo:false,level:1,pause:false});
    const html=read('../pages/'+key+'.html');
    for(const action of scene.script.filter(x=>x.highlight)){
      assert.ok(html.includes('id="'+action.highlight.slice(1)+'"'));
    }
    const game=load(key,template);
    game.onState(null,{demo:true,pause:true});
    assert.deepEqual(game.removed,[]);
    game.onState(null,{pause:false});
    game.onState(null,{demo:false});
    assert.deepEqual(game.removed,['teach-hl','teach-hl']);
    for(const group of game.config.cues){
      for(const cue of [group.goal,group.hint,group.hint2,group.praise,...(group.steps??[])]){
        const ref=scene.gameAudio[cue];
        const split=ref.lastIndexOf('-');
        const owner=lesson.scenes.find(x=>x.key===ref.slice(0,split));
        assert.ok(owner.script[Number(ref.slice(split+1))-1].say);
      }
    }
  }
});
