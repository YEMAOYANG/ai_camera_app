import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const {definitions,data}=JSON.parse(execFileSync(process.execPath,
  [fileURLToPath(new URL('../art-source/clip-diagrams.mjs',import.meta.url)),'--describe'],{encoding:'utf8'}));
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

test('减五、减二及固定量和同差的图都对应精确数量',()=>{
  const broken=quantity('five-from-ten'),chain=quantity('then-take-three');
  assert.deepEqual([broken.total,broken.takenTray,broken.takenLoose,broken.left],[12,5,0,7]);
  assert.deepEqual([chain.total,chain.takenTray,chain.takenLoose,chain.left],[12,3,2,7]);
  const two=quantity('break-for-two'),twoSteps=quantity('chain-for-two');
  assert.deepEqual([two.takenTray,two.takenLoose,two.left],[2,0,9]);
  assert.deepEqual([twoSteps.takenTray,twoSteps.takenLoose,twoSteps.left],[1,1,9]);
  for(const [name,expected] of [['same-three',[8,9,10]],['same-twelve',[9,8,7]],
                                ['same-eleven',[9,8,7]],['all-nine',[9,9,9]]]){
    assert.deepEqual(quantity(name).examples.map(e=>e.left),expected);
  }
  assert.equal(quantity('three-from-units').takenTray,0);
  assert.equal(quantity('q-flower-b').count,14-5);
  assert.equal(quantity('q-tag-a').count+5,11);
  assert.deepEqual(quantity('q-boat-c'),{left:10,right:11});
  assert.equal(quantity('q-biscuit-b').count,7);
  assert.deepEqual(quantity('q-crayon-c'),{left:13,right:12});
  assert.equal(quantity('q-seed-a').left,quantity('q-seed-prompt').left);
  const quizExpressions=[[14,5],[11,5],[14,4],[15,4],[16,3],[16,4],[16,5]];
  const practiced=[data.worked,[13,3],...data.tiles,...data.marble.flatMap(([n,ks])=>ks.map(k=>[n,k]))];
  assert.ok(!quizExpressions.some(pair=>practiced.some(p=>p[0]===pair[0]&&p[1]===pair[1])));
});

test('同一借出量只可命中能合回原数的靶，并画实际合回状态',()=>{
  const spec=game('choose-the-missing-part','magnetMarbles');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.queue.length),[3,3,2]);
  for(const [i,level] of spec.config.levels.entries()){
    const w=pilot(spec,level);
    assert.deepEqual(Array.from(w.targets.filter(t=>t.used),t=>t.value).sort(),
                     Array.from(level.queue,v=>level.total-v).sort());
    assert.equal(spec.config.cues[i].steps.length,level.queue.length);
  }
  const level=spec.config.levels[0],w=spec.rules.reset(level),f=feedback();
  for(let i=0;i<48;i++){
    spec.rules.update(w,level,oneKey(i===0?'action':null),dt,f);
    if(f.misses.length)break;
  }
  assert.deepEqual([f.hits.length,f.misses.length,w.i,w.help,w.locked],[0,1,0,false,null]);
  assert.ok(Math.abs(f.misses[0][0]-640)<1);
  const drawn=[];
  spec.drawTop({auto:true,state:'between',data:{level,progress:1}},
    {fill(){},drawImage(img){drawn.push(img.src);}});
  assert.deepEqual(drawn,['__IMG:marble-total-11__','__IMG:joined-11-2__']);
});

test('底卡必须是另一操作却同差，落错不移除底卡',()=>{
  const spec=game('pair-the-trays','fallingTiles');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.pieces.length),[2,3,3]);
  for(const level of spec.config.levels){
    for(const [a,b] of level.pairs){
      assert.notEqual(a,b);
      assert.equal(quantity('clip-card-'+a).left,quantity('clip-card-'+b).left);
    }
    const w=pilot(spec,level);
    assert.equal(w.i,level.pieces.length);
  }
  const level=spec.config.levels[0],w=spec.rules.reset(level),f=feedback();
  spec.rules.update(w,level,oneKey('action'),dt,f);
  assert.deepEqual([f.hits.length,f.misses.length,w.i,w.board[6][0],w.board[6][3]],[0,1,0,'11-2','11-3']);
  const drawn=[];
  spec.drawTop({auto:true,state:'between',data:{level,progress:1}},
    {fill(){},drawImage(img){drawn.push(img.src);}});
  assert.deepEqual(drawn,['__IMG:clip-amount-9__']);
});
