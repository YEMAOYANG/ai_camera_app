import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const geometry=JSON.parse(execFileSync(process.execPath,
  [fileURLToPath(new URL('../art-source/plane-diagrams.mjs',import.meta.url)),'--describe'],{encoding:'utf8'}));
const dt=1/60;
const epsilon=1e-8;

function signedArea(polygon){
  return polygon.reduce((sum,p,i)=>{
    const q=polygon[(i+1)%polygon.length];
    return sum+p[0]*q[1]-p[1]*q[0];
  },0)/2;
}

function overlap(subject,boundary){
  const boundaryOrder=signedArea(boundary)>0?boundary:[...boundary].reverse();
  let points=subject;
  for(const [index,a] of boundaryOrder.entries()){
    const b=boundaryOrder[(index+1)%boundaryOrder.length];
    const side=p=>(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]);
    const next=[];
    for(const [i,q] of points.entries()){
      const p=points[(i+points.length-1)%points.length];
      const from=side(p),to=side(q);
      if((from>=-epsilon)!==(to>=-epsilon)){
        const t=from/(from-to);
        next.push([p[0]+(q[0]-p[0])*t,p[1]+(q[1]-p[1])*t]);
      }
      if(to>=-epsilon)next.push(q);
    }
    points=next;
  }
  return Math.abs(signedArea(points));
}

function partition(outline,parts){
  for(const [i,part] of parts.entries()){
    const area=Math.abs(signedArea(part));
    assert.ok(Math.abs(area-overlap(part,outline))<epsilon);
    for(const other of parts.slice(i+1))assert.ok(overlap(part,other)<epsilon);
  }
  const total=parts.reduce((sum,p)=>sum+Math.abs(signedArea(p)),0);
  assert.ok(Math.abs(total-Math.abs(signedArea(outline)))<epsilon);
}

function game(page,template){
  let options;
  const K={ready(){},$(){return {style:{},addEventListener(){}};},draw:{rr(){}},
    game(value){options=value;}};
  const scope=vm.createContext({K,Image:class {complete=true;naturalWidth=220;},
    capture:(config,rules)=>({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js')+'\nClassic.create = capture;',scope);
  vm.runInContext(read('../../../kit/game_templates/'+template+'.js'),scope);
  vm.runInContext(read('../pages/'+page+'.js'),scope);
  return options;
}

function feedback(){
  const f={hits:[],misses:[],move(){},drop(){},jump(){},fx(){}};
  f.award=(x,y)=>f.hits.push([x,y]);
  f.lost=(x,y)=>f.misses.push([x,y]);
  return f;
}

function pilot({rules},level){
  rules.validate(level);
  const world=rules.reset(level);
  const result=feedback();
  for(let frame=0;frame<7200&&result.hits.length<rules.goal(level);frame++){
    rules.update(world,level,rules.pilot(world,level,dt),dt,result);
  }
  assert.equal(result.hits.length,rules.goal(level));
  assert.deepEqual(result.misses,[]);
  return {world,result};
}

function tryWithoutAiming(rules,level){
  const world=rules.reset(level);
  const result=feedback();
  for(let frame=0;frame<62;frame++){
    rules.update(world,level,{held:()=>false,press:key=>frame===0&&key==='action'},dt,result);
  }
  assert.deepEqual([result.hits.length,result.misses.length,world.help],[0,1,false]);
}

test('教学图和补形题内每片都在目标轮廓内，片间不重叠且面积恰好覆盖',()=>{
  for(const {outline,parts} of Object.values(geometry.samples))partition(outline,parts);
  for(const {outline,given,patch} of Object.values(geometry.patchSets))partition(outline,[...given,patch]);
  const {outline,given,patch}=geometry.quizTri;
  partition(outline,[...given,patch]);
});

test('拼桥按当前方向与格位补上，三关都走真实旋转和落下规则',()=>{
  const spec=game('replace-the-tile','shapeBridge');
  assert.deepEqual(Array.from(spec.config.levels,level=>level.slots.length),[2,2,3]);
  for(const [index,level] of spec.config.levels.entries()){
    const {world,result}=pilot(spec,level);
    assert.equal(world.filled.size,level.slots.length);
    if(index===0)assert.deepEqual(result.hits[0],[673,413]);
  }
  tryWithoutAiming(spec.rules,spec.config.levels[0]);
});

test('弹珠命中的是对应边长和朝向的缺口，保留实际完成图',()=>{
  const spec=game('matching-missing-piece','magnetMarbles');
  assert.deepEqual(Array.from(spec.config.levels,level=>level.queue.length),[2,2,3]);
  for(const [index,level] of spec.config.levels.entries()){
    for(const value of level.queue){
      const key=value.slice(2);
      assert.ok(geometry.patchSets[key]);
      assert.deepEqual(Array.from(level.pairs.filter(p=>p[0]===value),p=>p[1]),['g-'+key]);
    }
    assert.equal(spec.config.cues[index].steps.length,level.queue.length);
    const {world}=pilot(spec,level);
    assert.equal(world.targets.filter(t=>t.used).length,level.queue.length);
  }
  tryWithoutAiming(spec.rules,spec.config.levels[0]);
  const rendered=[];
  const context={fill(){},drawImage(p){rendered.push(p.src);}};
  spec.drawTop({auto:true,state:'between',data:{level:spec.config.levels[0],progress:1}},context);
  assert.deepEqual(rendered,['__IMG:filled-narrow__']);
});
