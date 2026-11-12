import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {compare,definitions,depotPairs,digits,snakePlans} from '../art-source/comparison-diagrams.mjs';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const dt=1/60;
function game(page,template){
  let options;
  const K={ready(){},$(){return {style:{},addEventListener(){}};},draw:{rr(){}},game(value){options=value;}};
  const scope=vm.createContext({K,Image:class {complete=true;naturalWidth=200;naturalHeight=160;},
    capture:(config,rules)=>({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js')+'\nClassic.create=capture;',scope);
  vm.runInContext(read('../../../kit/game_templates/'+template+'.js'),scope);
  vm.runInContext(read('../pages/'+page+'.js'),scope);
  return options;
}
function feedback(){
  const result={awards:0,misses:0,move(){},drop(){},jump(){},fx(){},resetCheckpoint(){}};
  result.award=()=>result.awards++;
  result.lost=()=>result.misses++;
  return result;
}
function press(key){return {held:()=>false,press:value=>value===key};}
function advance(rules,l,w,f,key,frames=60){
  rules.update(w,l,press(key),dt,f);
  for(let i=0;i<frames;i++)rules.update(w,l,press(),dt,f);
}
function complete({rules},level,index){
  rules.validate(level,index);
  const world=rules.reset(level),result=feedback();
  for(let frame=0;frame<14400&&result.awards<rules.goal(level);frame++){
    rules.update(world,level,rules.pilot(world,level,dt),dt,result);
  }
  assert.equal(result.awards,rules.goal(level));
  assert.equal(result.misses,0);
  return world;
}
function painted(spec,level,w,index=0){
  const pictures=[];
  spec.drawTop({level:index,data:{level,w}},{drawImage:img=>pictures.push(img.src),fill(){}});
  return pictures;
}

test('compare the highest differing place and preserve the left-to-right sign',()=>{
  for(let a=0;a<=100;a++){
    const [h,t,u]=digits(a);
    assert.equal(100*h+10*t+u,a);
    for(let b=0;b<=100;b++){
      const result=compare(a,b);
      assert.equal(result.group,a>b?'gt':a<b?'lt':'eq');
      assert.equal(result.place,a===b?null:a===100||b===100?'hundreds':Math.floor(a/10)!==Math.floor(b/10)?'tens':'ones');
    }
  }
  for(const invalid of [-1,101,3.6,'61'])assert.throws(()=>digits(invalid),RangeError);
  assert.equal(definitions['grouped-51-47'].shared,4);
  assert.equal(definitions['grouped-71-75'].place,'ones');
  assert.equal(definitions['equal-64-64'].group,'eq');
  assert.equal(definitions['reverse-75-71'].group,'gt');
  assert.deepEqual(definitions['between-10-and-14'].active,[11,12,13]);
});

test('snake eats only a valid number and actually switches the reference each round',()=>{
  const spec=game('drive-the-compare-snake','compareSnake');
  const {rules,config}=spec;
  for(const [i,level] of config.levels.entries()){
    const plan=snakePlans[i];
    assert.equal(level.start,plan.start);
    let prior=plan.start;
    for(const [j,round] of level.rounds.entries()){
      const [group,right,wrong]=plan.steps[j];
      const foods=Array.from(round.foods,row=>row[2]);
      assert.equal(round.relation,group);
      assert.ok(foods.includes(right)&&foods.includes(wrong));
      assert.equal(compare(right,prior).group,group);
      assert.notEqual(compare(wrong,prior).group,group);
      prior=right;
    }
    const done=complete(spec,level,i);
    assert.equal(done.round,plan.steps.length);
    assert.equal(done.ref,prior);
    assert.equal(done.body.length,2+plan.steps.length);
    assert.ok(painted(spec,level,done,i).some(src=>src.includes('snake-proof-'+(i+1)+'-'+plan.steps.length)));
  }
  const first=config.levels[0],world=rules.reset(first),result=feedback();
  advance(rules,first,world,result,'up',1);
  assert.deepEqual([result.awards,result.misses,world.ref,world.round,world.body[0]],[0,1,46,0,55]);
  assert.ok(!painted(spec,first,world).some(src=>src.includes('snake-proof')));
  advance(rules,first,world,result,'right',1);
  advance(rules,first,world,result,'up',46);
  assert.deepEqual([result.awards,result.misses,world.ref,world.round,world.body[0]],[1,1,54,1,46]);
  assert.ok(painted(spec,first,world).some(src=>src.includes('snake-54')));
});

test('depot rejects the wrong sign and shows the actually parked expression',()=>{
  const spec=game('push-pairs-to-sign-docks','sortingDepot');
  const {config,rules}=spec;
  for(const [i,level] of config.levels.entries()){
    assert.deepEqual(Array.from(level.items,item=>[item.left,item.right]),depotPairs[i]);
    for(const item of level.items)assert.equal(item.group,compare(item.left,item.right).group);
    const done=complete(spec,level,i);
    const cols=level.map[0].length;
    for(const [index,cell] of done.state.items.entries()){
      const dock=level.docks.find(d=>d.x+d.y*cols===-1-cell);
      assert.equal(dock?.group,level.items[index].group);
    }
  }
  const first=config.levels[0],world=rules.reset(first),result=feedback();
  advance(rules,first,world,result,'right');
  assert.deepEqual([result.awards,result.misses,world.wrongGroup,world.state.items[0]],[0,1,'lt',19]);
  assert.ok(!painted(spec,first,world).some(src=>src.includes('depot-proof')));
  for(const key of ['up','right','down','down'])advance(rules,first,world,result,key);
  assert.deepEqual([result.awards,result.misses,world.wrongGroup,world.state.items[0]],[1,1,null,-36]);
  assert.ok(painted(spec,first,world).some(src=>src.includes('depot-proof-32-45')));
  advance(rules,first,world,result,'left');
  assert.ok(painted(spec,first,world).some(src=>src.includes('depot-proof-32-45')));
  advance(rules,first,world,result,'action');
  assert.ok(painted(spec,first,world).some(src=>src.includes('depot-proof-32-45')));
  advance(rules,first,world,result,'action');
  assert.equal(world.state.items[0],19);
  assert.ok(!painted(spec,first,world).some(src=>src.includes('depot-proof')));
});
