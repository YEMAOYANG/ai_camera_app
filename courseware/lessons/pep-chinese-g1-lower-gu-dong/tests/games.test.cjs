const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const lesson = require('../lesson.json');

const root = path.join(__dirname, '..');
const dt = 1 / 60;

function load(template, page) {
  const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});
  let game;
  let pictures;
  const strip = {replaceChildren(...frames) {pictures = frames.map(frame => frame.src);}};
  const K = {gameTemplates:{},ready(){},stage:()=>({append(){}}),$:()=>strip,game(activity){game=activity;}};
  const Classic = {
    bot,create:(config,rules)=>({config,rules,draw(){}}),ease:(_,next)=>next,
    validToken:value=>typeof value==='string'&&Boolean(value)
  };
  const context = vm.createContext({K,Classic,document:{createElement:()=>({})}});
  for (const file of [`../../kit/game_templates/${template}.js`, `pages/${page}.js`]) {
    vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
  }
  const audio = lesson.scenes.find(s=>s.page===page).gameAudio;
  const speech = cue => {
    const id=audio[cue];
    const separator=id.lastIndexOf('-');
    const scene=lesson.scenes.find(s=>s.key===id.slice(0,separator));
    return scene.script[Number(id.slice(separator+1))-1].say;
  };
  return {...game,bot,speech,pictures:()=>pictures};
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
  return {world,level,score,finish,press:(key,seconds)=>update(bot(key),seconds)};
}

test('scene order is enforced; real images stay in the filmstrip and clear on replay',()=>{
  const game=load('bubbleMaze','order-the-frames');
  const run=play(game,0);
  run.press('down',.35);
  run.press('down',.35);
  game.draw({data:{w:run.world,level:run.level}});
  assert.deepEqual(run.score,{correct:0,misses:1});
  assert.deepEqual(game.pictures(),[]);
  assert.equal(run.world.help,false);
  const lines=[
    [/木瓜掉进湖/,/兔子.*转身跑/,/小猴跟上/,/小旗/],
    [/小猴跟上/,/狐狸、山羊和小鹿/,/野牛拦问/,/小旗/],
    [/野牛拦问/,/兔子带路/,/木瓜落水/,/笑起来/,/小旗/]
  ];
  for (const [i,level] of game.config.levels.entries()) {
    const steps=game.config.cues[i].steps;
    assert.equal(steps.length,level.route.length+1);
    steps.forEach((step,j)=>assert.match(game.speech(step),lines[i][j]));
    const fresh=play(game,i);
    fresh.finish();
    game.draw({data:{w:fresh.world,level}});
    assert.deepEqual(game.pictures(),Array.from(level.route,key=>game.config.art.icons[key]));
  }
  const replay=play(game,0);
  game.draw({data:{w:replay.world,level:replay.level}});
  assert.deepEqual(game.pictures(),[]);
});

test('actual sound, retelling and seeing the source only park in their own category',()=>{
  const game=load('sortingDepot','sort-the-clues');
  const kinds={rabbit:'heard',monkey:'told',elephant:'told',group:'seen'};
  const first=play(game,0);
  const path=['up','right','right','down','down','left','right','up','up','left','left',
    'down','right','up','right','down','left','down','right'];
  for (const key of path) first.press(key,.35);
  assert.deepEqual(first.score,{correct:0,misses:1});
  assert.equal(first.world.wrongGroup,'heard');
  assert.equal(first.world.help,false);
  assert.match(game.speech(game.config.cues[0].goal),/亲耳听到.*听兔子说/);
  assert.match(game.speech(game.config.cues[1].goal),/亲眼看见木瓜/);
  assert.match(game.speech(game.config.cues[2].goal),/大象.*听伙伴说.*伙伴在跑/);
  for (const [i,level] of game.config.levels.entries()) {
    for (const item of level.items) assert.equal(item.group,kinds[item.token]);
    for (const group of ['heard','told','seen']) {
      assert.equal(level.items.filter(item=>item.group===group).length,
        level.docks.filter(dock=>dock.group===group).length);
    }
    const run=play(game,i);
    run.finish();
    assert.ok(run.world.state.items.every(pos=>pos<0));
  }
});
