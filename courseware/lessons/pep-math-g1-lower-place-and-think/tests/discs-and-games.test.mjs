import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {arrangement,arrangements,definitions,depotPlans,mazePlans} from '../art-source/disc-diagrams.mjs';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const dt=1/60;
function game(page,template){
  let options;
  const K={ready(){},$(){return {style:{},addEventListener(){}};},game(value){options=value;}};
  const scope=vm.createContext({K,Image:class {complete=true;naturalWidth=200;},
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
function step(rules,l,w,f,key,frames=35){
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
function painted(spec,level,w){
  const images=[];
  spec.drawTop({data:{level,w}},{drawImage:(img,x,y)=>images.push([img.src,x,y])});
  return images;
}

test('fixed budgets have exactly the valid combinations from both ends, including the limit at ten',()=>{
  for(let discs=0;discs<=18;discs++){
    const rows=arrangements(discs);
    const exact=[];
    for(let tens=0;tens<10;tens++){
      for(let ones=0;ones<10;ones++){
        if(tens+ones===discs)exact.push({tens,ones,discs,value:10*tens+ones});
      }
    }
    assert.deepEqual(rows,exact);
    assert.equal(new Set(rows.map(x=>x.value)).size,rows.length);
    assert.ok(rows.slice(1).every((x,i)=>x.value-rows[i].value===9));
  }
  assert.deepEqual(arrangements(2).map(x=>x.value),[2,11,20]);
  assert.equal(arrangements(9).length,10);
  assert.deepEqual(arrangements(10).map(x=>x.value),[19,28,37,46,55,64,73,82,91]);
  assert.throws(()=>arrangement(0,10),RangeError);
  assert.throws(()=>arrangement(10,0),RangeError);
  assert.equal(definitions['q-eleven-a'].legal,true);
  assert.equal(definitions['q-eleven-b'].legal,false);
  assert.equal(definitions['q-eleven-c'].legal,false);
  assert.deepEqual(definitions['six-record-error'].spoiled,[[33,34]]);
  assert.deepEqual(definitions['six-record-error'].hidden,[51]);
});

test('maze must actually collect the legal next move and retains the previous arrangement',()=>{
  const spec=game('follow-the-disc-route','bubbleMaze');
  const {rules,config}=spec;
  for(const [i,l] of config.levels.entries()){
    const {discs,step:direction}=mazePlans[i];
    const states=arrangements(discs).map(x=>x.value);
    if(direction<0)states.reverse();
    assert.equal(l.start,states[0]);
    const route=Array.from(l.route,symbol=>Number(config.art.icons[symbol].match(/mat-(\d+)/)[1]));
    assert.deepEqual(route,states.slice(1));
    const done=complete(spec,l,i);
    assert.equal(done.i,l.route.length+1);
    assert.equal(done.map[done.y][done.x],'E');
  }
  const first=config.levels[0],world=rules.reset(first),result=feedback();
  step(rules,first,world,result,'left');
  assert.deepEqual([result.awards,result.misses,world.i,world.map[1][1]],[0,1,0,'B']);
  assert.ok(painted(spec,first,world).some(([src])=>src.includes('large-mat-2__')));
  assert.ok(painted(spec,first,world).some(([src])=>src.includes('maze-exit__')));
  step(rules,first,world,result,'right');
  step(rules,first,world,result,'right');
  assert.deepEqual([result.awards,result.misses,world.i],[1,1,1]);
  const visible=painted(spec,first,world);
  assert.ok(visible.some(([src,x])=>src.includes('large-mat-11')&&x===35));
  assert.ok(visible.some(([src,x])=>src.includes('large-mat-2')&&x===1048));
});

test('depot classifies the budget rather than the displayed number and clears a full restart',()=>{
  const spec=game('sort-the-disc-budgets','sortingDepot');
  const {rules,config}=spec;
  for(const [i,l] of config.levels.entries()){
    assert.deepEqual(Array.from(l.items,item=>[item.tens,item.ones]),depotPlans[i]);
    for(const item of l.items){
      const model=arrangement(item.tens,item.ones);
      assert.equal(item.group,model.discs);
      assert.equal(item.token,model.value);
    }
    const done=complete(spec,l,i);
    const width=l.map[0].length;
    for(const [j,cell] of done.state.items.entries()){
      const dock=l.docks.find(d=>d.x+d.y*width===-1-cell);
      assert.equal(dock?.group,l.items[j].group);
    }
  }
  const first=config.levels[0],world=rules.reset(first),result=feedback();
  step(rules,first,world,result,'right');
  assert.deepEqual([result.awards,result.misses,world.wrongGroup,world.state.items[0]],[0,1,3,19]);
  assert.ok(!painted(spec,first,world).some(([,x])=>x===1012));
  for(const key of ['up','right','down','down'])step(rules,first,world,result,key);
  assert.deepEqual([result.awards,result.misses,world.state.items[0]],[1,1,-36]);
  const parked=painted(spec,first,world);
  assert.ok(parked.some(([src,x])=>src.includes('large-mat-12')&&x===1012));
  assert.ok(parked.some(([src,x])=>src.includes('budget-3')&&x===1066));
  step(rules,first,world,result,'action');
  assert.equal(world.state.items[0],19);
  assert.ok(!painted(spec,first,world).some(([,x])=>x===1012||x===1066));
});
