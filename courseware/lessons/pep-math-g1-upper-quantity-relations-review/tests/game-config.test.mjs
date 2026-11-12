import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read=path=>fs.readFileSync(new URL(path,import.meta.url),'utf8');
const no=()=>{};
const bot=(...keys)=>({press:key=>keys.includes(key),held:key=>keys.includes(key)});

function load(page,template){
  let options,rules;
  const context=vm.createContext({
    K:{gameTemplates:{},ready:no,game:no,$:()=>({}),stage:()=>({appendChild:no})},
    Classic:{
      bot,ease:(_,value)=>value,
      clamp:(value,min,max)=>Math.max(min,Math.min(max,value)),
      validToken:token=>typeof token==='string'&&/^[a-z0-9-]+$/.test(token),
      match:(a,b,l)=>l.pairs.some(([first,second])=>a===first&&b===second),
      create(config,mechanic){
        options=config;rules=mechanic;options.levels.forEach(rules.validate);return {draw:no};
      },
    },
  });
  vm.runInContext(read(`../../../kit/game_templates/${template}.js`),context);
  vm.runInContext(read(`../pages/${page}.js`),context);
  return {options,rules};
}

function drive(game,level,input,frames=9000){
  const {rules}=game,dt=1/30,world=rules.reset(level);
  const state={awards:0,misses:0,firstMissAwarded:null};
  const feedback={fx:no,move:no,drop:no,jump:no,resetCheckpoint:no,
    award:()=>{state.awards++;},
    lost:()=>{state.misses++;state.firstMissAwarded??=state.awards;rules.adapt(world,state.misses);}};
  for(let frame=0;frame<frames&&state.awards<rules.goal(level);frame++)
    rules.update(world,level,input(world,level,dt,state),dt,feedback);
  return state;
}

test('sort each whole or part question into a matching tray',()=>{
  const game=load('choose-the-operation','sortingDepot');
  const {options,rules}=game;
  for(const level of options.levels){
    for(const item of level.items){
      assert.equal(item.group,item.token.split('-')[1]);
      assert.ok(level.docks.some(d=>d.group===item.group&&d.sample==='dock-'+item.group));
      assert.ok(options.art.icons[item.token]);
    }
    assert.equal(drive(game,level,rules.pilot).awards,level.items.length);
  }
});

test('the marble game requires the correct operation as well as the number',()=>{
  const game=load('repair-the-model','magnetMarbles');
  const {options,rules}=game;
  for(const level of options.levels){
    for(const [id,correct] of level.pairs){
      const [op,a,b]=id.split('-');
      assert.equal(correct,op+'-'+(op==='add'?Number(a)+Number(b):Number(a)-Number(b)));
      assert.ok(options.art.icons[correct]);
    }
    assert.equal(drive(game,level,rules.pilot).awards,level.queue.length);
  }
  const wrong=drive(game,options.levels[0],(w,l,dt,state)=>{
    if(w.i===0)return rules.pilot(w,l,dt);
    if(w.delay>0||w.air||state.misses>0)return bot();
    if(w.angle<.69)return bot('right');
    return bot('action');
  },280);
  assert.equal(wrong.firstMissAwarded,1);
  assert.equal(wrong.awards,1);
});
