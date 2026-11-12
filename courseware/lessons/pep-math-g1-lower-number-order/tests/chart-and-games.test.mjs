import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {chart,definitions,hops,matches,location,neighbor} from '../art-source/number-chart.mjs';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const dt=1/60;

function game(page,template){
  let options;
  const K={ready(){},$(){return {style:{},addEventListener(){}};},game(value){options=value;}};
  const scope=vm.createContext({K,Image:class {complete=true;naturalWidth=200;},capture:(config,rules)=>({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js')+'\nClassic.create=capture;',scope);
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
function press(key){return {held:()=>false,press:value=>value===key};}
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
function pictured(spec,level,w){
  const found=[];
  spec.drawTop({data:{level,w}},{drawImage:img=>found.push(img.src)});
  return found;
}

test('hundred chart respects row endings, every vertical neighbor and both diagonal boundaries',()=>{
  assert.deepEqual(chart.flat(),Array.from({length:100},(_,i)=>i+1));
  for(const n of chart.flat()){
    const [r,c]=location(n);
    assert.equal(chart[r][c],n);
    assert.equal(neighbor(n,0,1),c===9?null:n+1);
    assert.equal(neighbor(n,1,0),r===9?null:n+10);
    assert.equal(neighbor(n,1,-1),r===9||c===0?null:n+9);
    assert.equal(neighbor(n,1,1),r===9||c===9?null:n+11);
  }
  for(const n of [0,101,4.5,'31'])assert.throws(()=>location(n),RangeError);
  assert.deepEqual(location(50),[4,9]);
  assert.deepEqual(location(51),[5,0]);
  const {marks}=definitions['three-digit-marks'];
  assert.deepEqual(marks[4],['ones']);
  assert.deepEqual(marks[40],['tens']);
  assert.deepEqual(marks[44],['tens','ones','same']);
  assert.equal(marks[100],undefined);
  assert.equal(neighbor(neighbor(55,0,1),1,0),neighbor(neighbor(55,1,0),0,1));
});

test('number routes reject an actual wrong platform, then require every correct landing',()=>{
  const spec=game('counting-platforms','platformHop');
  for(const [i,l] of spec.config.levels.entries()){
    const expected=hops[i];
    assert.equal(l.startLabel,expected.start);
    assert.deepEqual(Array.from(l.route),expected.route);
    let n=l.startLabel,position=l.platforms.find(p=>p[3]==='start')[0];
    for(const next of l.route){
      assert.equal(next-n,expected.sign);
      const x=l.platforms.find(p=>p[3]===next)[0];
      assert.equal(Math.sign(x-position),expected.sign);
      n=next;position=x;
    }
    const done=complete(spec,l);
    assert.equal(done.checkpoint[3],l.route.at(-1));
    assert.ok(pictured(spec,l,done).some(src=>src.includes('hop-proof-'+done.checkpoint[3])));
  }
  const l=spec.config.levels[0],w=spec.rules.reset(l),result=feedback();
  for(let i=0;i<55&&!result.misses;i++){
    spec.rules.update(w,l,{held:key=>i<20&&key==='right',press:key=>i===0&&key==='action'},dt,result);
  }
  assert.deepEqual([result.awards,result.misses,w.platform[3],w.checkpoint[3]],[0,1,20,'start']);
});

test('only a vertical neighbor is valid; actual wrong placement does not reveal the answer',()=>{
  const spec=game('match-the-next-floor','fallingTiles');
  const {rules,config}=spec;
  for(const [i,l] of config.levels.entries()){
    const expected=matches[i];
    assert.deepEqual(Array.from(l.bottom).filter(n=>n!=null),expected.bottom);
    assert.deepEqual(Array.from(l.pieces),expected.pieces);
    for(const [falling,base] of l.pairs)assert.equal(neighbor(base,expected.down,0),falling);
    const done=complete(spec,l);
    assert.equal(done.i,l.pieces.length);
    assert.ok(l.pairs.every(([,base])=>!done.board[6].includes(base)));
    assert.ok(pictured(spec,l,done).some(src=>src.includes('tile-proof-'+l.pieces.at(-1))));
  }
  const l=config.levels[0],w=rules.reset(l),f=feedback();
  rules.update(w,l,press('right'),dt,f);
  rules.update(w,l,press('action'),dt,f);
  assert.deepEqual([f.awards,f.misses,w.i,w.board[6][3],w.board[6][4]],[0,1,0,34,26]);
  assert.deepEqual(pictured(spec,l,w),[]);
  const correct=rules.reset(l),ok=feedback();
  rules.update(correct,l,press('action'),dt,ok);
  assert.deepEqual([ok.awards,ok.misses,correct.i,correct.board[6][1]],[1,0,1,null]);
  assert.deepEqual(pictured(spec,l,correct),['__IMG:tile-proof-34__']);
});
