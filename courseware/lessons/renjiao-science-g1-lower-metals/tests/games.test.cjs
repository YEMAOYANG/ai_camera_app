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

test('a visible polish result is rejected by the sound station without scoring',()=>{
  const {config,logic} = load('sort-metal-evidence','sortingDepot');
  const level = config.levels[0], w=logic.reset(level), {state,fb}=callbacks();
  const polished = level.items[0], rightDock=level.docks.find(d=>d.y===polished.y);
  assert.equal(polished.group,'polish');
  assert.equal(rightDock.group,'tap');
  logic.update(w,level,bot('right'),.32,fb);
  const beforeWrong = [...w.state.items];
  logic.update(w,level,bot('right'),.32,fb);
  assert.equal(state.misses,1);
  assert.equal(state.awards,0);
  assert.deepEqual([...w.state.items],beforeWrong);
  assert.equal(w.wrongGroup,'polish');
});

test('the real depot movement reaches only the method that produced each record',()=>{
  const {config,logic} = load('sort-metal-evidence','sortingDepot');
  assert.deepEqual(Array.from(config.levels,l=>l.items.length),[2,3,4]);
  assert.equal(config.levels[1].items.filter(i=>i.group==='bend').length,2);
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
      assert.equal(dock.sample,'station-'+dock.group);
    }
  }
});

test('the feedback and its tail fit above the camera cue',()=>{
  const {bubbleAt,logic}=load('photograph-metal-samples','shutterScout');
  const feedback=bubbleAt();
  const cue=logic.goalAnchor();
  assert.equal(feedback.x,cue.x+cue.w/2);
  assert.ok(feedback.y-34>=2);
  assert.ok(feedback.y+52<cue.y);
});

test('the real camera rejects a wrong angle and records the right declared pair after every level sequence',()=>{
  const {config,logic} = load('photograph-metal-samples','shutterScout');
  const card=lesson.scenes.find(s=>s.key==='photograph-metal-samples').observationCard;
  const imgs={icons:new Map(Object.keys(config.art.icons).map(id=>[id,{complete:true,naturalWidth:100}]))};
  const trial='same-metal-two-views';
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

test('the first successful action matches the visible teacher demonstration',()=>{
  const depot=load('sort-metal-evidence','sortingDepot');
  const camera=load('photograph-metal-samples','shutterScout');
  const firstAction=(game,imgs)=>{
    const level=game.config.levels[0], world=game.logic.reset(level);
    const {state,fb}=callbacks();
    for(let frame=0;frame<6000&&!state.awards;frame++)
      game.logic.update(world,level,game.logic.pilot(world,level),.016,fb,imgs);
    assert.equal(state.awards,1);
    assert.equal(state.misses,0);
    assert.equal(state.observations.length,0);
    return {level,world};
  };
  const {level,world}=firstAction(depot);
  const [firstDock,secondItem]=world.state.items;
  assert.equal(level.docks[0].group,'polish');
  assert.equal(firstDock,-1-level.docks[0].y*level.map[0].length-level.docks[0].x);
  assert.equal(secondItem,level.items[1].y*level.map[0].length+level.items[1].x);
  const imgs={icons:new Map(Object.keys(camera.config.art.icons).map(id=>[id,{complete:true,naturalWidth:100}]))};
  const firstPhoto=firstAction(camera,imgs).world.photos[0];
  assert.equal(firstPhoto.view,'metal-top-copper');
  assert.equal(firstPhoto.state,1);
});
