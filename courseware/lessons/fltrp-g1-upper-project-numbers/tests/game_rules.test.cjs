const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const kit = path.resolve(lesson, '../../kit/game_templates');
const read = file => fs.readFileSync(file, 'utf8');
const dt = 1 / 60;

function mechanics(template, page) {
  const context = vm.createContext({K: {ready() {}, game() {}}});
  vm.runInContext(read(path.join(kit, 'classic.js')), context);
  vm.runInContext('globalThis.capture = {...Classic, create(config, engine) {globalThis.game = {config, engine}; return {};}}', context);
  vm.runInContext(read(path.join(kit, template + '.js')).replace(/=\s*Classic;/, '=capture;'), context);
  vm.runInContext(read(path.join(lesson, 'pages', page + '.js')), context);
  return context.game;
}

function play(engine, level, choose, stop) {
  engine.validate(level);
  const world = engine.reset(level);
  const state = {world, correct: 0, wrong: 0, resets: 0};
  const feedback = {
    fx() {}, move() {}, drop() {}, jump() {},
    award() { state.correct++; },
    lost() { state.wrong++; engine.adapt(world, state.wrong); },
    resetCheckpoint() { state.correct = 0; state.resets++; },
  };
  for (let frame = 0; frame < 4200 && !stop(state); frame++) {
    engine.update(world, level, choose(world, frame), dt, feedback);
  }
  return state;
}

function input(...keys) {
  return {held: key => keys.includes(key), press: key => keys.includes(key)};
}

for (const [template,page] of [['orchardCatch','catch-and-fill'],['listenDelivery','deliver-collage-tiles']]) {
  test(page + ' follows both approved game rules through three levels twice', () => {
    const {config, engine} = mechanics(template,page);
    const lessonSource = JSON.parse(read(path.join(lesson,'lesson.json')));
    const scene = lessonSource.scenes.find(s => s.key === page);
    const cues = config.cues.flatMap(level => Object.values(level).flat());
    assert.deepEqual([...new Set(cues)].sort(),Object.keys(scene.gameAudio).sort());
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) {
        const target = engine.goal(level);
        const state = play(engine,level,world => engine.pilot(world,level,dt),s => s.correct === target);
        assert.equal(state.correct,target);
        if (level.capacity) {
          assert.deepEqual(Array.from(state.world.fill),Array.from(level.capacity));
        } else {
          for (const [cargo, station] of level.orders) assert.equal(state.world.delivered.get(station),cargo);
        }
      }
    }
  });
}

test('missing the first falling bunch does not consume it or fill a basket', () => {
  const {config,engine} = mechanics('orchardCatch','catch-and-fill');
  const state = play(engine,config.levels[0],() => input(),s => s.wrong===1);
  assert.equal(state.correct,0);
  assert.equal(state.world.index,0);
  assert.deepEqual(Array.from(state.world.fill),[0,0]);
});

test('the wrong first group cannot be picked up for the two-books order', () => {
  const {config,engine} = mechanics('listenDelivery','deliver-collage-tiles');
  const state = play(engine,config.levels[0],w => w.col < 6 ? input('right') : input('action'),s => s.wrong===1);
  assert.equal(state.correct,0);
  assert.equal(state.world.carried,null);
  assert.equal(state.world.order,0);
});

test('all delivery orders use the same object and count in pickup and exhibit graphics', () => {
  const {config} = mechanics('listenDelivery','deliver-collage-tiles');
  for (const level of config.levels) {
    for (const [cargo,station] of level.orders) {
      assert.equal(cargo.replace(/^cargo-/,'display-'),station);
    }
  }
});
