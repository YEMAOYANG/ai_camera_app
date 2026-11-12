import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const read=name=>readFileSync(new URL(name,import.meta.url),'utf8');
const geometry=JSON.parse(execFileSync(process.execPath,
  [fileURLToPath(new URL('../art-source/tangram-diagrams.mjs',import.meta.url)),'--describe'],{encoding:'utf8'}));
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

function signature(poly){
  return poly.flatMap((p,i)=>poly.slice(i+1).map(q=>(p[0]-q[0])**2+(p[1]-q[1])**2))
    .sort((a,b)=>a-b);
}

test('完整七块、二三四块和方形变换保持原板尺寸且铺满外框',()=>{
  const checkParts=parts=>{
    assert.equal(new Set(parts.map(t=>t.id)).size,parts.length);
    for(const [i,{id,poly}] of parts.entries()){
      assert.deepEqual(signature(poly),signature(geometry.canonical[id]));
      for(const other of parts.slice(i+1))assert.ok(overlap(poly,other.poly)<epsilon);
    }
  };
  for(const {outline,parts} of Object.values(geometry.examples)){
    checkParts(parts);
    partition(outline,parts.map(t=>t.poly));
  }
  const {threeSquare,fourTriangle}=geometry.examples;
  assert.deepEqual(fourTriangle.parts.slice(0,3),threeSquare.parts.map(({id,poly})=>({id,poly:poly.map(([x,y])=>[2-y,x])})));
  checkParts(geometry.house);
  assert.deepEqual(geometry.house.map(t=>t.id).sort(),Object.keys(geometry.canonical).sort());
  assert.equal(geometry.house.reduce((n,t)=>n+Math.abs(signedArea(t.poly)),0),8);
  assert.ok(geometry.fourGap[3].poly.every(p=>p[0]>2));
  assert.ok(geometry.fourOverlap.slice(0,3).some(t=>overlap(t.poly,geometry.fourOverlap[3].poly)>epsilon));
});

test('同形不同大小的缺口不能混用，实际命中保留精确拼合图',()=>{
  const spec=game('aim-to-complete','magnetMarbles');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.queue.length),[2,2,3]);
  for(const [index,level] of spec.config.levels.entries()){
    const {world}=pilot(spec,level);
    assert.equal(world.targets.filter(t=>t.used).length,level.queue.length);
    assert.ok(spec.config.cues[index].goal);
    for(const p of level.queue){
      const key=p.slice(2),model=geometry.patches[key];
      assert.ok(model&&model.example.parts[model.missing]);
      assert.deepEqual(Array.from(level.pairs.filter(t=>t[0]===p),t=>t[1]),['g-'+key]);
    }
  }
  const l=spec.config.levels[0],w=spec.rules.reset(l),result=feedback();
  for(let frame=0;frame<71;frame++){
    spec.rules.update(w,l,{held:key=>frame<20&&key==='right',press:key=>frame===20&&key==='action'},dt,result);
    if(result.misses.length)break;
  }
  assert.deepEqual([result.misses.length,result.hits.length,w.i,w.help],[1,0,0,false]);
  assert.ok(Math.abs(result.misses[0][0]-846)<l.targetWidth/2);
  const drawn=[];
  spec.drawTop({auto:true,state:'between',data:{level:l,progress:1}},
               {fill(){},drawImage(img){drawn.push(img.src);}});
  assert.deepEqual(drawn,['__IMG:finished-large__']);
});

test('小蛇实走后更新参照图，同一外轮廓容许换板和转向',()=>{
  const spec=game('trace-outer-outline','compareSnake');
  assert.deepEqual(Array.from(spec.config.levels,l=>l.rounds.length),[2,3,3]);
  for(const level of spec.config.levels){
    const {world,result}=pilot(spec,level);
    assert.equal(result.hits.length,level.rounds.length);
    assert.equal(level.groups[world.ref],level.groups[level.start]);
  }
  const l=spec.config.levels[0],w=spec.rules.reset(l),result=feedback();
  for(let frame=0;frame<61;frame++){
    spec.rules.update(w,l,{held:()=>false,press:key=>frame===0&&key==='right'||frame===1&&key==='up'},dt,result);
    if(result.misses.length)break;
  }
  assert.deepEqual([result.misses.length,result.hits.length,w.round,w.ref,w.help],[1,0,0,'r-tri',false]);
});
