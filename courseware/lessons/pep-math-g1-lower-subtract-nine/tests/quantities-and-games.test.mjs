import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const {definitions,data}=JSON.parse(execFileSync(process.execPath,
  [fileURLToPath(new URL('../art-source/quantity-diagrams.mjs',import.meta.url)),'--describe'],{encoding:'utf8'}));
const quantity=id=>definitions[id].quantity;
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

test('两种减法保留同样的余量，六道题的数量不复用课堂算例',()=>{
  const original=quantity('fourteen-before');
  const breakTen=quantity('take-nine-from-ten'), first=quantity('take-loose-first');
  const chain=quantity('take-five-next');
  assert.equal(original.total,data.worked);
  assert.deepEqual([breakTen.takenTray,breakTen.takenLoose,breakTen.left],[9,0,5]);
  assert.deepEqual([first.takenTray,first.takenLoose,first.left],[0,4,10]);
  assert.deepEqual([chain.takenTray,chain.takenLoose,chain.taken,chain.left],[5,4,9,5]);
  assert.equal(quantity('join-fourteen').packed+breakTen.left,original.total);
  assert.deepEqual(quantity('compare-after-nine').remainders,[2,3,4]);
  assert.equal(quantity('q-sixteen-b').count,16-9);
  const combine=quantity('q-seventeen-c');
  assert.equal(combine.trayRemainder+combine.loose,17-9);
  assert.deepEqual([quantity('q-nineteen-a').taken,quantity('q-nineteen-a').left],[9,10]);
  assert.equal(quantity('q-eighteen-b').total,18);
  assert.equal(quantity('q-compare-a').extra,1);
  const display=quantity('q-display-slots');
  assert.equal(display.capacities.reduce((a,b)=>a+b)-display.placed,quantity('q-display-c').count);
  assert.ok(!data.tileTotals.some(n=>data.quizTotals.includes(n)));
});

test('横移后只消同余量，演示结果使用实际匹配图',()=>{
  const spec=game('match-the-remainder','fallingTiles');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.pieces.length),[2,2,3]);
  for(const level of spec.config.levels){
    for(const [key,rem] of level.pairs){
      const a=quantity('tile-state-'+key.slice(2));
      assert.equal(a.left,quantity('tile-left-'+rem.slice(2)).left);
    }
    const finished=pilot(spec,level);
    assert.equal(finished.i,level.pieces.length);
  }
  const level=spec.config.levels[0],w=spec.rules.reset(level),f=feedback();
  spec.rules.update(w,level,oneKey('action'),dt,f);
  assert.deepEqual([f.hits.length,f.misses.length,w.i,w.board[6][3]],[0,1,0,'r-4']);
  spec.rules.adapt(w,1);
  assert.equal(w.failureCount,1);
  const drawn=[];
  spec.drawTop({auto:true,state:'between',data:{level,progress:1}},{fill(){},drawImage(img){drawn.push(img.src);}});
  assert.deepEqual(drawn,['__IMG:tile-left-2__']);
});

test('实际装货和交付均按九加补量验证，只显示真实完成的总量',()=>{
  const spec=game('return-the-quantity','listenDelivery');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.orders.length),[1,2,3]);
  for(const level of spec.config.levels){
    const w=pilot(spec,level);
    assert.equal(w.order,level.orders.length);
    for(const [good,target] of level.orders){
      const total=Number(target.slice(2)), rest=Number(good.slice(2));
      assert.equal(total,9+rest);
      assert.equal(w.delivered.get(target),good);
      assert.equal(quantity('delivery-job-'+total).unfilled,rest);
    }
  }
  const level=spec.config.levels[0],w=spec.rules.reset(level),f=feedback();
  spec.rules.update(w,level,oneKey('action'),dt,f);
  assert.deepEqual([f.misses.length,f.hits.length,w.carried,w.order,w.help],[1,0,null,0,false]);
  const drawn=[];
  const ctx={fill(){},drawImage(img){drawn.push(img.src);}};
  spec.drawTop({data:{w,level}},ctx);
  assert.deepEqual(drawn,['__IMG:delivery-job-11__']);
  drawn.length=0;
  spec.drawTop({data:{w:pilot(spec,level),level}},ctx);
  assert.deepEqual(drawn,['__IMG:delivery-proof-11__']);
});

