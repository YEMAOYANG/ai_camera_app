import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const no = () => {};
const bot = (...keys) => ({press:key=>keys.includes(key),held:key=>keys.includes(key)});

function load(page,template) {
  let options,rules;
  const context=vm.createContext({
    K:{gameTemplates:{},ready:no,game:no,$:()=>({}),stage:()=>({appendChild:no})},
    Classic:{
      bot,
      ease:(_,value)=>value,
      validToken:token=>typeof token==='string'&&/^[a-z0-9-]+$/.test(token),
      match:(a,b,l)=>l.pairs.some(([first,second])=>first===a&&second===b),
      create(config,mechanic){
        options=config;rules=mechanic;options.levels.forEach(rules.validate);return {draw:no};
      },
    },
  });
  vm.runInContext(read(`../../../kit/game_templates/${template}.js`),context);
  vm.runInContext(read(`../pages/${page}.js`),context);
  return {options,rules};
}

function drive(game,level,input,frames=9000) {
  const {rules}=game,dt=1/30;
  const world=rules.reset(level);
  const state={awards:0,misses:0,firstMissAwarded:null};
  const feedback={fx:no,move:no,drop:no,
    award:()=>{state.awards++;},
    lost:()=>{
      state.misses++;
      state.firstMissAwarded??=state.awards;
      rules.adapt(world,state.misses);
    }};
  for(let frame=0;frame<frames&&state.awards<rules.goal(level);frame++)
    rules.update(world,level,input(world,level,dt,frame),dt,feedback);
  return {state,world};
}

test('each nursery order must return its sent group to its specific remaining group',()=>{
  const game=load('bring-the-parts-back','listenDelivery');
  const {options,rules}=game;
  for(const [i,level] of options.levels.entries()){
    assert.equal(options.cues[i].steps.join(),level.orders.flat().map(id=>'return-'+id).join());
    for(const [sent,left] of level.orders){
      assert.ok(sent.startsWith('sent-')&&left.startsWith('left-'));
      assert.ok(options.art.icons[sent]&&options.art.icons[left]);
    }
    const result=drive(game,level,rules.pilot);
    assert.equal(result.state.awards,level.orders.length*2);
    for(const [sent,left] of level.orders)assert.equal(result.world.delivered.get(left),sent);
  }
  const wrong=drive(game,options.levels[0],
    (w,_,__,frame)=>frame>85?bot():w.col<6?bot('right'):bot('action'),90);
  assert.equal(wrong.state.firstMissAwarded,0);
  assert.equal(wrong.world.carried,null);
});

test('tile match requires both the sum and a before-action card',()=>{
  const game=load('restore-pair','fallingTiles');
  const {options,rules}=game;
  for(const level of options.levels){
    for(const [key,target] of level.pairs){
      const [,a,b]=key.split('-');
      assert.equal(target,'past-'+(Number(a)+Number(b)));
      assert.ok(options.art.icons[key]&&options.art.icons[target]);
    }
    assert.equal(drive(game,level,rules.pilot).state.awards,level.pieces.length);
  }
  const challenge=options.levels[2];
  assert.ok(challenge.bottom.includes('after-13')&&challenge.bottom.includes('past-13'));
  const wrong=drive(game,challenge,(w,_,__,frame)=>{
    if(frame===0)return bot('action'); // Accept 9 + 8 by the 17 card.
    if(w.i===1&&w.delay<=0&&w.x===2)return bot('left');
    if(w.i===1&&w.delay<=0&&w.x===1)return bot('action'); // Lands beside the later 13.
    return bot();
  },34);
  assert.equal(wrong.state.firstMissAwarded,1);
  assert.equal(wrong.state.awards,1);
});
