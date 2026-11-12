const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

const templates = path.join(__dirname,'../../../kit/game_templates');
const pages = path.join(__dirname,'../pages');
const read = file => fs.readFileSync(file,'utf8');
const dt = 1/60;

function load(template,page){
  const fixture={};
  const K={ready(){},$(selector){return {style:{}};},game(options){
    fixture.options=options;
    return {follow(){}};
  }};
  const ctx={K,Image:class {complete=true;naturalWidth=100;},record(config,rules){
    Object.assign(fixture,{config,rules});
  }};
  const capture='Classic.create=(config,rules)=>{record(config,rules);return {draw(){}};};';
  vm.runInNewContext([read(path.join(templates,'classic.js')),capture,
    read(path.join(templates,template+'.js')),read(path.join(pages,page+'.js'))].join('\n'),ctx);
  fixture.config.levels.forEach(fixture.rules.validate);
  return fixture;
}

function drive(rules,level,world,finish,onAward){
  const quiet=()=>{};
  const feedback={fx:quiet,move:quiet,jump:quiet,drop:quiet,lost:quiet,award:onAward};
  for(let t=0;t<5400&&!finish();t++)rules.update(world,level,rules.pilot(world,level,dt),dt,feedback);
  assert.ok(finish(),'shared physics and collision rules must reach every authored checkpoint');
}

test('landmark hits pair one clue at a time and keep the first clue during the demo hold',()=>{
  const {config,rules,options}=load('magnetMarbles','aim-for-a-landmark');
  const targets=[['hall','guilin'],['gorges','taishan'],['westlake','hall']];
  for(const [index,level] of config.levels.entries()){
    const world=rules.reset(level),hits=[];
    drive(rules,level,world,()=>hits.length===level.queue.length,()=>hits.push(world.locked.value));
    assert.deepEqual(hits,targets[index]);
    // A completed queue must still draw without trying to resolve an undefined token.
    let clue;
    const context={drawImage(image){clue=image.src;}};
    options.draw({level:index,data:{w:world},autoLoop:false},context);
    assert.match(clue,/marble-\d+__/);
    if(index===0){
      options.draw({level:index,data:{w:world},autoLoop:true},context);
      assert.equal(clue,'__IMG:marble-100__');
    }
  }
});

test('platform routes contain each running sum in order',()=>{
  const {config,rules}=load('platformHop','hop-to-the-combined-count');
  const addends=[[1,2,5],[2,5,2],[5,2,2,2]];
  for(const [index,level] of config.levels.entries()){
    let sum=0;
    const expected=addends[index].map(n=>sum+=n);
    const world=rules.reset(level),landings=[];
    drive(rules,level,world,()=>landings.length===expected.length,()=>landings.push(world.checkpoint[3]));
    assert.deepEqual(landings,expected);
  }
});
