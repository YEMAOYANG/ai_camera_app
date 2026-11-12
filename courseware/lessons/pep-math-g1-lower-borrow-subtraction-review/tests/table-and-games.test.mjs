import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const model=JSON.parse(execFileSync(process.execPath,
  [fileURLToPath(new URL('../art-source/review-diagrams.mjs',import.meta.url)),'--describe'],{encoding:'utf8'}));
const quantity=id=>model.definitions[id].quantity;
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
  const f={hits:[],misses:[],move(){},drop(){},jump(){},fx(){},resetCheckpoint(){}};
  f.award=(x,y)=>f.hits.push([x,y]);
  f.lost=(x,y)=>f.misses.push([x,y]);
  return f;
}
function pilot({rules},level){
  rules.validate(level);
  const world=rules.reset(level), result=feedback();
  for(let frame=0;frame<14400&&result.hits.length<rules.goal(level);frame++){
    rules.update(world,level,rules.pilot(world,level,dt),dt,result);
  }
  assert.equal(result.hits.length,rules.goal(level));
  assert.deepEqual(result.misses,[]);
  return world;
}
function oneKey(key){
  return {held:()=>false,press:which=>which===key};
}

test('完整45格无漏项，三方向路径与表的行列规则一致',()=>{
  assert.equal(model.table.flat().length,45);
  assert.deepEqual(model.table.map(row=>row.length),[9,8,7,6,5,4,3,2,1]);
  assert.deepEqual(model.table[0][8],[10,1]);
  assert.deepEqual(model.table[8][0],[18,9]);
  const present=(n,k)=>model.table.some(row=>row.some(pair=>pair[0]===n&&pair[1]===k));
  for(let n=10;n<=19;n++){
    for(let k=1;k<=9;k++)assert.equal(present(n,k),k>n-10);
  }
  for(const {mode,start,route} of model.hops){
    let before=start;
    for(const pair of route){
      const [n,k]=pair;
      const [m,j]=before;
      assert.ok(present(n,k));
      assert.deepEqual([n-m,k-j],mode==='column'?[1,0]:mode==='row'?[0,-1]:[1,1]);
      before=pair;
    }
  }
  assert.deepEqual([model.methods.breakTen.taken,model.methods.breakTen.left,model.methods.chain.taken,model.methods.chain.left],[8,6,8,6]);
  assert.equal(quantity('q-line-stem').total-quantity('q-line-stem').left-1,quantity('q-line-a').count);
  assert.equal(quantity('q-plants-stem').total-quantity('q-plants-stem').known,quantity('q-plants-c').count);
});

test('跳到错误的候选台不推进，实际落到按顺序的算式才推进',()=>{
  const spec=game('hop-along-the-table','platformHop');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.route.length),[3,3,3]);
  for(const [i,level] of spec.config.levels.entries()){
    const done=pilot(spec,level);
    assert.equal(done.checkpoint[3],level.route.at(-1));
    assert.deepEqual(Array.from(level.route),model.hops[i].route.map(row=>row.join('-')));
  }
  const level=spec.config.levels[0],w=spec.rules.reset(level),f=feedback();
  for(let i=0;i<55;i++){
    spec.rules.update(w,level,{held:key=>i<20&&key==='right',press:key=>i===0&&key==='action'},dt,f);
    if(f.misses.length)break;
  }
  assert.deepEqual([f.hits.length,f.misses.length,w.i,w.checkpoint[3],w.platform[3]],[0,1,0,'start','13-7']);
});

test('推箱按未知或余量分组，错站拒绝，首个示范只进五的格',()=>{
  const spec=game('move-to-the-right-result','sortingDepot');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.items.length),[2,2,3]);
  for(const p of Object.values(model.puzzles)){
    const result=p.kind==='minus'?p.taken+p.left:p.kind==='compare'?p.larger-p.smaller:
      p.kind==='steps'?p.total-p.taken-p.extraTaken:p.total-p.known;
    assert.equal(p.result,result);
  }
  for(const level of spec.config.levels){
    const done=pilot(spec,level);
    assert.ok(done.state.items.every(p=>p<0));
    for(const item of level.items)assert.equal(item.group,model.puzzles[item.token].result);
  }
  const level=spec.config.levels[0],w=spec.rules.reset(level),f=feedback();
  spec.rules.update(w,level,oneKey('right'),dt,f);
  assert.deepEqual([f.hits.length,f.misses.length,w.wrongGroup],[0,1,5]);
  const demo=spec.rules.reset(level),one=feedback();
  for(let i=0;i<500&&!one.hits.length;i++)spec.rules.update(demo,level,spec.rules.pilot(demo,level,dt),dt,one);
  assert.equal(one.hits.length,1);
  assert.ok(demo.state.items[0]<0&&demo.state.items[1]>=0);
});
