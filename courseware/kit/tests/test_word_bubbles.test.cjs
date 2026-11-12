const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const kit = path.join(__dirname, '..');
const read = file => JSON.parse(fs.readFileSync(path.join(kit, file), 'utf8'));
const words = read('examples/classic-arcade/word-bubbles.json');
const shapes = read('examples/alternate/word-bubbles-pictures.json');
const script = fs.readFileSync(path.join(kit, 'game_templates/wordBubbles.js'), 'utf8');
const dt = 1 / 60;

function play(level){
  const K = {gameTemplates:{}, draw:{circle(){}}};
  const drawn = [];
  const Classic = {
    create: (_, mechanic) => mechanic,
    bot: (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)}),
    clamp: (value, min, max) => Math.min(max, Math.max(min, value)),
    validToken: value => typeof value === 'string' && Boolean(value),
    box(){}, token(){},
    sprite(_, frame, x, y, width, height, {angle}){
      drawn.push({frame,x,angle});
      return true;
    }
  };
  vm.runInNewContext(script, {K, Classic});
  const rules = K.gameTemplates.wordBubbles({});
  rules.validate(level);
  const world = rules.reset(level);
  let awards = 0, misses = 0, shots = 0;
  const feedback = {
    award(){awards++;},
    lost(){rules.adapt(world, ++misses);},
    move(){}, fx(){}, drop(){shots++;}
  };
  const step = input => rules.update(world, level, input, dt, feedback);
  return {
    world,
    get awards(){return awards;},
    get misses(){return misses;},
    get shots(){return shots;},
    hold(key, frames){for(let i=0;i<frames;i++)step(Classic.bot(key));},
    draw(){
      drawn.length = 0;
      const context = {beginPath(){}, moveTo(){}, bezierCurveTo(){}, stroke(){}, ellipse(){}, fill(){}};
      rules.draw(world,level,context,{frames:['idle','fire']},{reduce:true});
      return drawn[0];
    },
    pilot(){
      for(let i=0;i<800&&awards<rules.goal(level);i++)step(rules.pilot(world,level));
    }
  };
}

test('the pilot can land the right bubbles for words and shapes with player inputs',()=>{
  for(const sample of [words, shapes]){
    for(const level of sample.levels){
      const game=play(level);
      game.pilot();
      assert.equal(game.awards,level.rounds.length);
      assert.equal(game.shots,level.rounds.length);
      assert.equal(game.misses,0);
    }
  }
});

test('hitting the other card costs the streak and the second miss slows the drift',()=>{
  const level=words.levels[0];
  const game=play({...level,drift:0});
  game.hold('right',23);
  game.hold('action',1);
  game.hold(null,33);
  assert.equal(game.awards,0);
  assert.equal(game.misses,1);
  assert.equal(game.world.round,0);
  game.hold('action',1);
  game.hold(null,33);
  assert.equal(game.misses,2);
  assert.equal(game.world.help,true);
  const before=game.world.t;
  game.hold(null,60);
  assert.ok(game.world.t-before<.6);
  game.pilot();
  assert.equal(game.awards,level.rounds.length);
});

test('a cue must identify exactly one displayed picture',()=>{
  const level=words.levels[0];
  const invalid=round=>({...level,rounds:[round,level.rounds[1]]});
  assert.throws(()=>play(invalid({target:'apple',cards:['apple','apple']})),/distinct cards/);
  assert.throws(()=>play(invalid({target:'cat',cards:['apple','banana']})),/with a target/);
});

test('both boat frames face upward along the bubble flight path',()=>{
  const game=play(words.levels[0]);
  assert.deepEqual(game.draw(),{frame:'idle',x:game.world.x,angle:-Math.PI/2});
  game.hold('action',1);
  const launch=game.world.shot;
  assert.deepEqual(game.draw(),{frame:'fire',x:launch.x,angle:-Math.PI/2});
  const y=launch.y;
  game.hold(null,1);
  assert.ok(game.world.shot.y<y);
});
