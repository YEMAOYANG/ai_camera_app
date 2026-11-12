const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const test = require('node:test');
const {runInNewContext} = require('node:vm');

const root = join(__dirname,'..');
const kit = join(root,'..','..','kit','game_templates');
const lesson = JSON.parse(readFileSync(join(root,'lesson.json'),'utf8'));
const bot = (...keys) => ({held:key=>keys.includes(key),press:key=>keys.includes(key)});
const validToken = value => typeof value==='string' && value.trim().length>0 && [...value].length<=18;

function load(page,template){
  let result;
  const K = {gameTemplates:{}, ready(){}, game(game){result=game;}};
  const Classic = {
    create:(config,logic)=>({config,logic}), bot, validToken,
    clamp:(value,min,max)=>Math.max(min,Math.min(max,value)),
    center:(x,y,w,h)=>({x:x-w/2,y:y-h/2,w,h}),
  };
  const context = {K,Classic};
  runInNewContext(readFileSync(join(kit,template+'.js'),'utf8'),context);
  runInNewContext(readFileSync(join(root,'pages',page+'.js'),'utf8'),context);
  result.config.levels.forEach((level,index)=>result.logic.validate(level,index));
  return result;
}

function callbacks(){
  const state = {awards:0,misses:0,observations:[]};
  const fb = {fx(){},move(){},drop(){},resetCheckpoint(){},
    award(){state.awards++;},lost(){state.misses++;},
    observe(trial,views){state.observations.push({trial,...views});},
  };
  return {state,fb};
}

test('the same-shaped wood tray is rejected by the plastic dock without scoring',()=>{
  const {config,logic} = load('material-docks','sortingDepot');
  const level = config.levels[0], w=logic.reset(level), {state,fb}=callbacks();
  const wood = level.items[0], rightDock=level.docks.find(d=>d.y===wood.y);
  assert.equal(wood.group,'wood');
  assert.equal(rightDock.group,'plastic');
  logic.update(w,level,bot('right'),.32,fb);
  const beforeWrong = [...w.state.items];
  logic.update(w,level,bot('right'),.32,fb);
  assert.equal(state.misses,1);
  assert.equal(state.awards,0);
  assert.deepEqual([...w.state.items],beforeWrong);
  assert.equal(w.wrongGroup,'wood');
});

test('the real depot movement reaches only its matching material docks in all three routes',()=>{
  const {config,logic} = load('material-docks','sortingDepot');
  assert.deepEqual(Array.from(config.levels,l=>l.items.length),[2,3,4]);
  assert.equal(config.levels[1].items.filter(i=>i.group==='wood').length,2);
  for(const level of config.levels){
    const w=logic.reset(level), {state,fb}=callbacks();
    for(let frames=0;frames<3000&&state.awards<logic.goal(level);frames++)
      logic.update(w,level,logic.pilot(w,level),.035,fb);
    assert.equal(state.awards,logic.goal(level));
    assert.equal(state.misses,0);
    for(const [index,position] of w.state.items.entries()){
      assert.ok(position<0);
      const destination=-1-position, cols=level.map[0].length;
      const dock=level.docks.find(d=>d.x===destination%cols&&d.y===Math.floor(destination/cols));
      assert.equal(dock.group,level.items[index].group);
      assert.equal(dock.sample,'swatch-'+dock.group);
    }
  }
});

test('the real camera rejects a wrong angle and records the right declared pair after every level sequence',()=>{
  const {config,logic} = load('material-photo-pairs','shutterScout');
  const card=lesson.scenes.find(s=>s.key==='material-photo-pairs').observationCard;
  const imgs={icons:new Map(Object.keys(config.art.icons).map(id=>[id,{complete:true,naturalWidth:100}]))};
  const trial='same-object-two-views';
  const first=config.levels[0], w=logic.reset(first), wrong=callbacks();
  logic.update(w,first,bot(),1.45,wrong.fb,imgs);
  logic.update(w,first,bot('action'),.02,wrong.fb,imgs);
  assert.equal(wrong.state.misses,1);
  assert.equal(wrong.state.awards,0);
  assert.equal(wrong.state.observations.length,0);

  for(const [index,level] of config.levels.entries()){
    const work=logic.reset(level), {state,fb}=callbacks();
    for(let frames=0;frames<7000&&state.awards<logic.goal(level);frames++){
      logic.update(work,level,logic.pilot(work,level),.016,fb,imgs);
      if(state.awards<logic.goal(level)) assert.equal(state.observations.length,0);
    }
    assert.equal(state.awards,logic.goal(level));
    assert.equal(state.misses,0);
    assert.equal(state.observations.length,1);
    const actual=state.observations[0], declared=card.levels[index].trials[0];
    assert.equal(actual.trial,trial);
    assert.equal(declared.id,trial);
    for(const view of ['top','side']){
      assert.equal(actual[view],level.photoViews[view]);
      assert.equal(actual[view],config.observation.trials[trial][view][index]);
      assert.deepEqual(Object.keys(declared[view]),[actual[view]]);
      assert.equal(declared[view][actual[view]].image,actual[view]);
    }
  }
});

test('the first error feedback fits above the requested camera angle',()=>{
  const {bubbleAt,logic} = load('material-photo-pairs','shutterScout');
  const bubble = bubbleAt();
  const card = logic.goalAnchor();
  assert.equal(bubble.x,card.x+card.w/2);
  assert.ok(bubble.y-34>=2);
  assert.ok(bubble.y+52<card.y);
});
