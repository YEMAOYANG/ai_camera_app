const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const lesson = require('../lesson.json');

const root=path.join(__dirname,'..');
const dt=1/60;

function load(template,page) {
  const bot=(...keys)=>({press:key=>keys.includes(key),held:key=>keys.includes(key)});
  let game;
  const K={gameTemplates:{},ready(){},stage:()=>({append(){}}),$(){},game(activity){game=activity;}};
  const Classic={
    bot,create:(config,rules)=>({config,rules}),ease:(_,next)=>next,
    validToken:value=>typeof value==='string'&&Boolean(value),
    clamp:(n,min,max)=>Math.min(max,Math.max(min,n))
  };
  const context=vm.createContext({K,Classic});
  for (const file of [`../../kit/game_templates/${template}.js`, `pages/${page}.js`]) {
    vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
  }
  const audio=lesson.scenes.find(s=>s.page===page).gameAudio;
  const speech=cue=>{
    const id=audio[cue];
    const separator=id.lastIndexOf('-');
    const scene=lesson.scenes.find(s=>s.key===id.slice(0,separator));
    return scene.script[Number(id.slice(separator+1))-1].say;
  };
  return {...game,bot,speech};
}

function play(game,index) {
  const {rules,config,bot}=game;
  const level=config.levels[index];
  rules.validate(level,index);
  const world=rules.reset(level);
  const score={correct:0,misses:0};
  function update(input,seconds=dt) {
    rules.update(world,level,input,seconds,{
      award(){score.correct++;},
      lost(){score.misses++;rules.adapt(world,score.misses);},
      fx(){},move(){},drop(){},jump(){},resetCheckpoint(){}
    });
  }
  function finish() {
    for (let frame=0;frame<3600&&score.correct<rules.goal(level);frame++) {
      update(rules.pilot(world,level,dt));
    }
    assert.equal(score.correct,rules.goal(level));
  }
  return {world,score,finish,press:(key,seconds)=>update(bot(key),seconds)};
}

test('fish, cow and swallow must match their tail actions, and the final gecko matches discovery',()=>{
  const game=load('sortingDepot','sort-the-tail-use');
  const groups={fish:'water',cow:'flies',swallow:'turn',gecko:'home'};
  const first=play(game,0);
  const wrong=['up','right','right','down','down','left','right','up','up','left','left',
    'down','right','up','right','down','left','down','right'];
  for (const step of wrong) first.press(step,.35);
  assert.deepEqual(first.score,{correct:0,misses:1});
  assert.equal(first.world.wrongGroup,'water');
  assert.equal(first.world.help,false);
  assert.match(game.speech(game.config.cues[0].goal),/小鱼和老牛.*拨水、赶苍蝇/);
  assert.match(game.speech(game.config.cues[1].goal),/燕子.*改变方向/);
  assert.match(game.speech(game.config.cues[2].goal),/转身发现新尾/);
  for (const [i,level] of game.config.levels.entries()) {
    for (const card of level.items) {
      assert.equal(card.group,groups[card.token]);
      assert.equal(level.docks.filter(dock=>dock.group===card.group).length,1);
    }
    const fresh=play(game,i);
    fresh.finish();
    assert.ok(fresh.world.state.items.every(pos=>pos<0));
  }
});

test('ordered jumps keep the return, reminder and discovery separate',()=>{
  const game=load('platformHop','jump-the-journey');
  const routes=[['A','B','C'],['C','D','E'],['D','E','F','G']];
  const words={A:/墙角挣断/,B:/小鱼借尾巴/,C:/树下吃草/,D:/房檐下/,E:/回家路/,F:/妈妈提醒/,G:/看到新尾后高兴/};
  const miss=play(game,0);
  miss.press('action');
  for (let frame=0;frame<25;frame++) miss.press('left');
  for (let frame=0;frame<36;frame++) miss.press();
  assert.deepEqual(miss.score,{correct:0,misses:1});
  assert.equal(miss.world.i,0);
  assert.equal(miss.world.help,false);
  for (const [i,level] of game.config.levels.entries()) {
    assert.deepEqual([...level.route],routes[i]);
    assert.equal(level.prompt,'scroll');
    level.route.forEach((token,j)=>assert.match(game.speech(game.config.cues[i].steps[j]),words[token]));
    play(game,i).finish();
  }
});
