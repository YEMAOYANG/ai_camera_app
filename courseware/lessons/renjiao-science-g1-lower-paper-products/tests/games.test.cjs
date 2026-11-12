const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const test = require('node:test');
const {runInNewContext} = require('node:vm');

const root=join(__dirname,'..');
const kit=join(root,'..','..','kit','game_templates');
const lesson=JSON.parse(readFileSync(join(root,'lesson.json'),'utf8'));
const bot=(...keys)=>({held:key=>keys.includes(key),press:key=>keys.includes(key)});

function load(page,template){
  let result;
  const K={gameTemplates:{},ready(){},game(v){
    result=v;
    v.anchors=new Map();
    return {follow:(selector,rect)=>v.anchors.set(selector,rect)};
  }};
  const Classic={create:(config,logic)=>({config,logic}),bot,
    center:(x,y,w,h)=>({x:x-w/2,y:y-h/2,w,h}),
    ease:(_value,target)=>target,clamp:(v,min,max)=>Math.max(min,Math.min(max,v))};
  const ctx={K,Classic};
  runInNewContext(readFileSync(join(kit,template+'.js'),'utf8'),ctx);
  runInNewContext(readFileSync(join(root,'pages',page+'.js'),'utf8'),ctx);
  result.config.levels.forEach(result.logic.validate);
  return result;
}

function feedback(onAward=()=>{}){
  const state={awards:0,misses:0,observations:[]};
  const fb={move(){},fx(){},drop(){},jump(){},lost(){state.misses++;},
    award(){state.awards++;onAward();},
    observe(trial,views){state.observations.push({trial,...views});}};
  return {state,fb};
}

test('moving into the immediately reachable pulp station before tearing is rejected',()=>{
  const {config,logic}=load('rebuild-paper-route','bubbleMaze');
  const level=config.levels[0],w=logic.reset(level),{state,fb}=feedback();
  assert.equal(level.route[0],'A');
  logic.update(w,level,bot('right'),.016,fb);
  assert.equal(w.map[w.y][w.x],'B');
  assert.equal(w.i,0);
  assert.equal(state.misses,1);
  assert.equal(state.awards,0);
});

test('the first route pointer marks the visible next-step tile',()=>{
  const {anchors,config,logic}=load('rebuild-paper-route','bubbleMaze');
  const scene=lesson.scenes.find(entry=>entry.key==='rebuild-paper-route');
  const pointer=scene.script.find(beat=>beat.highlight).highlight;
  const {x,y,w,h}=anchors.get(pointer)();
  const level=config.levels[0], world=logic.reset(level);
  const station=logic.target(world,level);
  assert.ok(x<=640&&x+w>=640&&y<=46&&y+h>=46);
  assert.ok(station.y>y+h);
});

test('shared maze movement reaches each paper step in order and only then the exit',()=>{
  const {config,logic}=load('rebuild-paper-route','bubbleMaze');
  assert.deepEqual(Array.from(config.levels,l=>l.route.join('')),['AB','BCD','ABCD']);
  for(const level of config.levels){
    const w=logic.reset(level),reached=[];
    const {state,fb}=feedback(()=>reached.push(level.map[w.y][w.x]));
    for(let frames=0;frames<8000&&state.awards<logic.goal(level);frames++)
      logic.update(w,level,logic.pilot(w,level),.016,fb);
    assert.deepEqual(reached,[...level.route,'E']);
    assert.equal(state.misses,0);
    assert.equal(w.i,level.route.length+1);
  }
});

test('the camera feedback and its tail fit above the requested photo angle',()=>{
  const {bubbleAt,logic}=load('photograph-paper-shapes','shutterScout');
  const feedback=bubbleAt();
  const goal=logic.goalAnchor();
  assert.equal(feedback.x,goal.x+goal.w/2);
  assert.ok(feedback.y-34>=2);
  assert.ok(feedback.y+52<goal.y);
});

test('wrong photo angle leaves no capture and successful level records the actual pair',()=>{
  const {config,logic}=load('photograph-paper-shapes','shutterScout');
  const card=lesson.scenes.find(scene=>scene.key==='photograph-paper-shapes').observationCard;
  const imgs={icons:new Map(Object.keys(config.art.icons).map(id=>[id,{complete:true,naturalWidth:100}]))};
  const trial='same-paper-two-views';
  const first=config.levels[0], start=logic.reset(first), wrong=feedback();
  logic.update(start,first,bot(),1.45,wrong.fb,imgs);
  logic.update(start,first,bot('action'),.016,wrong.fb,imgs);
  assert.equal(wrong.state.misses,1);
  assert.equal(wrong.state.awards,0);
  assert.equal(wrong.state.observations.length,0);

  for(const [i,level] of config.levels.entries()){
    const w=logic.reset(level),{state,fb}=feedback();
    for(let frames=0;frames<8000&&state.awards<logic.goal(level);frames++){
      logic.update(w,level,logic.pilot(w,level),.016,fb,imgs);
      if(state.awards<logic.goal(level)) assert.equal(state.observations.length,0);
    }
    assert.equal(state.awards,logic.goal(level));
    assert.equal(state.misses,0);
    assert.equal(state.observations.length,1);
    const [capture]=state.observations, declared=card.levels[i].trials[0];
    assert.equal(capture.trial,trial);
    assert.equal(declared.id,trial);
    for(const direction of ['top','side']){
      assert.equal(capture[direction],level.photoViews[direction]);
      assert.equal(capture[direction],config.observation.trials[trial][direction][i]);
      assert.deepEqual(Object.keys(declared[direction]),[capture[direction]]);
      assert.equal(declared[direction][capture[direction]].image,capture[direction]);
    }
  }
});
