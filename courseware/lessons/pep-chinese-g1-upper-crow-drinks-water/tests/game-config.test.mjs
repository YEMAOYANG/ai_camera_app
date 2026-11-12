import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8');
const no = () => {};
const bot = (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)});

function load(page, template) {
  let options, rules;
  const context = vm.createContext({
    K: {gameTemplates: {}, ready: no, game: no},
    Classic: {
      bot,
      clamp: (value, min, max) => Math.min(max, Math.max(min, value)),
      ease: (_, value) => value,
      validToken: token => typeof token === 'string' && /^[a-z0-9-]+$/.test(token),
      create(config, mechanic) {
        options = config;
        rules = mechanic;
        config.levels.forEach(mechanic.validate);
        return {draw: no};
      },
    },
  });
  vm.runInContext(read(`../../../kit/game_templates/${template}.js`), context);
  vm.runInContext(read(`../pages/${page}.js`), context);
  return {options, rules};
}

function drive(game, level, input, frames) {
  const {rules} = game;
  const world = rules.reset(level);
  const state = {awards: 0, misses: 0, firstMissAwarded: null};
  const feedback = {
    fx: no, move: no, jump: no, drop: no,
    award: () => { state.awards++; },
    lost: () => {
      state.misses++;
      state.firstMissAwarded ??= state.awards;
      rules.adapt(world, state.misses);
    },
  };
  for (let i = 0; i < frames && state.awards < rules.goal(level); i++) {
    rules.update(world, level, input(world, level, i), 1 / 30, feedback);
  }
  return {state, world};
}

test('word pictures and voiced meaning are registered for all rounds', () => {
  const game = load('word-scenes', 'wordBubbles');
  const {options, rules} = game;
  for (const [i, level] of options.levels.entries()) {
    assert.equal(options.cues[i].steps.length, level.rounds.length);
    for (const [j, round] of level.rounds.entries()) {
      assert.equal(options.cues[i].steps[j], 'crow-word-'+round.target);
      assert.ok(round.cards.every(card => options.art.icons[card]));
    }
    assert.equal(drive(game, level, rules.pilot, 4000).state.awards, rules.goal(level));
  }
  const wrong = drive(game, options.levels[0],
    (_world, _level, frame) => frame < 12 ? bot('right') : frame === 12 ? bot('action') : bot(), 35);
  assert.equal(wrong.state.firstMissAwarded, 0);
  assert.equal(wrong.world.help, false);
});

test('retell checkpoints retain the intended order and a later scene gives no first award', () => {
  const game = load('retell-route', 'bubbleMaze');
  const {options, rules} = game;
  assert.deepEqual(options.levels.map(v => v.route.join('')).join('/'), 'AD/ACD/ABCD');
  for (const [i, level] of options.levels.entries()) {
    assert.ok(level.listenOnly && level.route.every(card => options.art.icons[card]));
    assert.equal(options.cues[i].steps.length, level.route.length + 1);
    assert.equal(options.cues[i].steps.at(-1), 'crow-route-exit');
    assert.equal(drive(game, level, rules.pilot, 9000).state.awards, rules.goal(level));
  }
  const wrong = drive(game, options.levels[0],
    (_world, _level, frame) => frame < 21 ? bot('down') : bot('right'), 80);
  assert.equal(wrong.state.firstMissAwarded, 0);
});
