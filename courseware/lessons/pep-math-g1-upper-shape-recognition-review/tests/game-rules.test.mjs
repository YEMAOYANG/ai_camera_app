import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = name => readFileSync(new URL(name, import.meta.url), 'utf8');
const dt = 1 / 60;
const geometry = JSON.parse(execFileSync(process.execPath,
  [new URL('../art-source/solid-diagrams.mjs',import.meta.url).pathname,'--describe'], {encoding:'utf8'}));

function game(page, template) {
  let instance;
  const rendered = [];
  const K = {
    ready() {},
    draw:{rr(){}},
    $: () => ({ style:{}, addEventListener(){} }),
    game: options => { instance=options; },
  };
  const scope=vm.createContext({K,Image:class {complete=true;naturalWidth=230;},
    capture:(config,rules)=>({config,rules})});
  vm.runInContext(read('../../../kit/game_templates/classic.js') +
    '\nClassic.create = capture;',scope);
  vm.runInContext(read('../../../kit/game_templates/'+template+'.js'),scope);
  vm.runInContext(read('../pages/'+page+'.js'),scope);
  return { ...instance,rendered };
}

function feedback() {
  const state={ hits:[], misses:[], fx(){}, move(){}, drop(){}, resetCheckpoint(){} };
  state.award=(x,y)=>state.hits.push([x,y]);
  state.lost=(x,y)=>state.misses.push([x,y]);
  return state;
}

function runPilot({rules},level,index) {
  rules.validate(level,index);
  const world=rules.reset(level);
  const result=feedback();
  for(let frame=0;frame<7200&&result.hits.length<rules.goal(level);frame++){
    rules.update(world,level,rules.pilot(world,level,dt),dt,result);
  }
  assert.equal(result.hits.length,rules.goal(level));
  assert.deepEqual(result.misses,[]);
  return {world,result};
}

function tap(rules,level,world,key,result,frames=32) {
  for(let frame=0;frame<frames;frame++){
    rules.update(world,level,{ held:()=>false, press:query=>frame===0&&query===key },dt,result);
  }
}

test('四种立体按外形匹配，错误的停靠点不会得分',()=>{
  const spec=game('sort-solid-blocks','sortingDepot');
  const {config,rules}=spec;
  assert.deepEqual(Array.from(config.levels,level=>level.items.length),[2,3,4]);
  for(const [index,level] of config.levels.entries()){
    assert.ok(level.items.every(item=>item.group===item.token));
    const {world,result}=runPilot(spec,level,index);
    assert.ok(world.state.items.every(position=>position<0));
    if(index===0)assert.deepEqual(result.hits[0],[757,303]);
  }
  const level=config.levels[0];
  const world=rules.reset(level);
  const result=feedback();
  for(const key of ['down','down','right','right','right','up'])tap(rules,level,world,key,result);
  assert.deepEqual([result.hits.length,result.misses.length,world.help],[0,1,false]);
});

test('补块尺寸与图中缺口相合，显示实际拼成的立体',()=>{
  const spec=game('complete-the-solid','fallingTiles');
  const {config,rules,rendered}=spec;
  assert.deepEqual(Array.from(config.levels,level=>level.pieces.length),[2,3,3]);
  for(const [index,level] of config.levels.entries()){
    for(const [pieceId,baseId] of level.pairs){
      const piece=geometry.pieces[pieceId],base=geometry.gapBoards[baseId];
      if('cylinder' in piece){
        assert.equal(piece.cylinder,base.cylinder);
      }else{
        assert.deepEqual(piece.size,[base.goal[0],base.goal[1],base.goal[2]-base.size[2]]);
      }
    }
    const {world,result}=runPilot(spec,level,index);
    assert.equal(world.board[6].filter(Boolean).length,0);
    if(index===0)assert.deepEqual(result.hits[0],[675,561]);
  }
  const level=config.levels[0];
  const world=rules.reset(level);
  const result=feedback();
  tap(rules,level,world,'action',result);
  assert.deepEqual([result.hits.length,result.misses.length,world.failureCount],[0,1,0]);
  const canvas={fill(){},drawImage(image){rendered.push(image.src);}};
  spec.drawTop({data:{level,progress:0}},canvas);
  assert.deepEqual(rendered,[]);
  spec.drawTop({data:{level,progress:1}},canvas);
  spec.drawTop({data:{level,progress:2}},canvas);
  assert.deepEqual(rendered,['__IMG:built-thin__','__IMG:built-wide__']);
});

test('图题缺口的补块坐标恰好填满，不和已有方块相交',()=>{
  const keys=cells=>cells.map(p=>p.join(',')).sort();
  assert.deepEqual(keys([...geometry.known,...geometry.remainder]),keys(geometry.target));
  assert.equal(geometry.remainder.length,4);
  assert.equal(new Set(keys(geometry.target)).size,6);
});
