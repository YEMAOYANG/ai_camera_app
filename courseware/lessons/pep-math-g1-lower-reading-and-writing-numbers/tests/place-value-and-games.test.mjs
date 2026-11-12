import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { definitions, placeValue } from '../art-source/place-value-diagrams.mjs';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const dt=1/60;

function game(page,template){
  let options;
  const K={ready(){},$(){return {style:{},addEventListener(){}};},draw:{rr(){}},
    game(value){options=value;}};
  const scope=vm.createContext({K,Image:class {complete=true;naturalWidth=200;naturalHeight=190;},
    capture:(config,rules)=>({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js')+'\nClassic.create = capture;',scope);
  vm.runInContext(read('../../../kit/game_templates/'+template+'.js'),scope);
  vm.runInContext(read('../pages/'+page+'.js'),scope);
  return options;
}
function feedback(){
  const result={awards:0,misses:0,move(){},drop(){},jump(){},fx(){}};
  result.award=()=>result.awards++;
  result.lost=()=>result.misses++;
  return result;
}
function press(key){
  return {held:()=>false,press:value=>value===key};
}
function step(rules,world,level,key,result){
  rules.update(world,level,press(key),dt,result);
  for(let i=0;i<30;i++)rules.update(world,level,press(),dt,result);
}
function complete({rules},level){
  rules.validate(level);
  const world=rules.reset(level),result=feedback();
  for(let frame=0;frame<14400&&result.awards<rules.goal(level);frame++){
    rules.update(world,level,rules.pilot(world,level,dt),dt,result);
  }
  assert.equal(result.awards,rules.goal(level));
  assert.equal(result.misses,0);
  return world;
}
function visibleImages(options,level,w){
  const images=[];
  options.drawTop({data:{level,w}},{drawImage:(img,x,y)=>images.push([img.src,x,y]),save(){},stroke(){},restore(){}});
  return images;
}

test('two exact places represent tens and ones and preserve a written zero',()=>{
  for(let n=0;n<=99;n++){
    const {tens,ones,groupSize}=placeValue(n);
    assert.equal(groupSize,10);
    assert.equal(tens*groupSize+ones,n);
    assert.equal(tens,Math.floor(n/10));
  }
  for(const n of [-1,.4,100,NaN,'42'])assert.throws(()=>placeValue(n),RangeError);
  assert.deepEqual(definitions['compare-50-and-5'].quantity,[placeValue(50),placeValue(5)]);
  assert.deepEqual(definitions['q-amount-73'].quantity,placeValue(73));
  assert.deepEqual(definitions['q-amount-37'].quantity,placeValue(37));
  assert.equal(definitions['q-tens-88'].quantity.selection,'tens');
});

test('the maze rejects ones first, then records both places and the actual zero',()=>{
  const spec=game('take-the-number-cards','bubbleMaze');
  const {config,rules}=spec;
  for(const level of config.levels){
    const targetDigits=Array.from(level.route,token=>Number(config.art.icons[token].match(/digit-(\d)/)[1]));
    assert.deepEqual(targetDigits,Array.from(level.amounts).flatMap(n=>[placeValue(n).tens,placeValue(n).ones]));
    const done=complete(spec,level);
    assert.equal(done.i,level.route.length+1);
    assert.equal(done.map[done.y][done.x],'E');
  }
  const first=config.levels[0],world=rules.reset(first),result=feedback();
  step(rules,world,first,'left',result);
  assert.deepEqual([result.awards,result.misses,world.i,world.map[1][1]],[0,1,0,'4']);
  const wrong=visibleImages(spec,first,world);
  assert.ok(!wrong.some(([src])=>src.includes('digit-')));
  assert.ok(wrong.some(([src])=>src.includes('postal-arch')));
  step(rules,world,first,'right',result);
  step(rules,world,first,'right',result);
  assert.deepEqual([result.awards,result.misses,world.i],[1,1,1]);
  assert.ok(visibleImages(spec,first,world).some(([src,x])=>src.includes('digit-3')&&x===1069));
  const second=config.levels[1],whole=rules.reset(second),scored=feedback();
  for(const key of ['right','left','left'])step(rules,whole,second,key,scored);
  assert.equal(whole.i,2);
  const drawings=visibleImages(spec,second,whole);
  assert.ok(drawings.some(([src,x,y])=>src.includes('digit-0')&&x===1151&&y===399));
  assert.ok(drawings.some(([src])=>src.includes('maze-72')));
});

test('the delivery rejects swapped cargo and the wrong box before recording the matching order',()=>{
  const spec=game('deliver-by-number','listenDelivery');
  const {config,rules}=spec;
  for(const level of config.levels){
    const done=complete(spec,level);
    assert.equal(done.delivered.size,level.orders.length);
    for(const [good,box] of level.orders){
      assert.equal(good.slice(2),box.slice(2));
      assert.equal(done.delivered.get(box),good);
    }
  }
  const first=config.levels[0],world=rules.reset(first),result=feedback();
  assert.ok(visibleImages(spec,first,world).some(([src,x,y])=>src.includes('goods-13')&&x===36&&y===365));
  step(rules,world,first,'action',result);
  assert.deepEqual([result.awards,result.misses,world.carried],[0,1,null]);
  step(rules,world,first,'right',result);
  step(rules,world,first,'action',result);
  assert.deepEqual([result.awards,result.misses,world.carried],[1,1,'g-31']);
  Object.assign(world,{row:0,col:3,safeRow:0,safeCol:3});
  step(rules,world,first,'action',result);
  assert.deepEqual([result.awards,result.misses,world.carried,world.delivered.size],[1,2,'g-31',0]);
  for(const key of ['right','right','action'])step(rules,world,first,key,result);
  assert.deepEqual([result.awards,result.misses,world.carried,world.delivered.get('b-31')],[2,2,null,'g-31']);
  assert.ok(visibleImages(spec,first,world).some(([src,x])=>src.includes('box-31')&&x===1072));
});
