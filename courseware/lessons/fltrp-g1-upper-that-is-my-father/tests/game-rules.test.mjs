import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = name => readFileSync(new URL(name, import.meta.url), 'utf8');

function mechanic(page, template) {
  let game;
  const K = {
    ready() {},
    $: () => ({ style: {}, addEventListener() {} }),
    game: value => { game = value; },
  };
  const scope = vm.createContext({ K, capture: (config, rules) => ({ config, rules }) });
  vm.runInContext(read('../../../kit/game_templates/classic.js') + '\nClassic.create = capture;', scope);
  vm.runInContext(read('../../../kit/game_templates/' + template + '.js'), scope);
  vm.runInContext(read('../pages/' + page + '.js'), scope);
  return game;
}

const dt = 1 / 60;
const action = { held: () => false, press: key => key === 'action' };

function play(config, rules, level) {
  rules.validate(level);
  const world = rules.reset(level);
  const hits = [];
  const feedback = {
    move() {}, drop() {}, fx() {},
    award(x, y) { hits.push([x, y]); },
    lost() { assert.fail('The pilot triggered a miss'); },
  };
  const goal = rules.goal(level);
  for (let frame = 0; frame < 7200 && hits.length < goal; frame++) {
    const input = rules.pilot(world, level, dt);
    rules.update(world, level, input, dt, feedback);
  }
  assert.equal(hits.length, goal);
  assert.equal(config.stepVoiceLead, true);
  return { hits, world };
}

function rejectStart(rules, level) {
  let misses = 0;
  rules.update(rules.reset(level), level, action, dt, {
    move() {}, drop() {}, fx() {},
    award() { assert.fail('Dropping or picking at the starting point must not score'); },
    lost() { misses++; },
  });
  assert.equal(misses, 1);
}

test('falling tiles pair the recorded relation with the current speaker', () => {
  const { config, rules } = mechanic('family-cards', 'fallingTiles');
  const levels = config.levels;
  assert.equal(config.art.icons['a-father'], config.art.icons['a-mother']);
  assert.equal(config.art.icons['a-grandpa'], config.art.icons['a-grandma']);
  assert.notEqual(config.art.icons['a-grandpa'], config.art.icons['mother-father']);
  assert.notEqual(config.art.icons['mother-father'], config.art.icons['b-father']);

  const targets = [
    ['link-father-a', 'link-mother-a'],
    ['link-grandpa-a', 'link-grandma-a', 'link-friend-a'],
    ['link-father-mother', 'link-father-b', 'link-grandpa-a'],
  ];
  for (const [index, level] of levels.entries()) {
    const expected = targets[index];
    assert.equal(level.pieces.length, expected.length);
    for (const [step, token] of level.pieces.entries()) {
      assert.deepEqual(Array.from(level.pairs.filter(pair => pair[0] === token), pair => pair[1]),
        [expected[step]]);
      assert.equal(config.cues[index].steps[step], token);
    }
    const { hits, world } = play(config, rules, level);
    if (index === 0) assert.deepEqual(hits[0], [675, 561]);
    assert.equal(world.board[6].filter(Boolean).length, 0);
  }
  rejectStart(rules, levels[0]);
});

test('delivery requires both the correct visitor and the speaker-relative station', () => {
  const { config, rules } = mechanic('deliver-introductions', 'listenDelivery');
  const levels = config.levels;
  assert.equal(new Map(levels[0].drop).get('near-a'), 1);
  assert.equal(new Map(levels[1].drop).get('near-a'), 7);
  const expected = [
    [['near-a','father-a']],
    [['far-a','grandma-a'],['near-a','friend-a']],
    [['far-mother','grandpa-a'],['near-b','father-b'],['far-b','father-b']],
  ];
  for (const [index, level] of levels.entries()) {
    const { world, hits } = play(config, rules, level);
    if (index === 0) assert.deepEqual(hits[0], [726, 536]);
    assert.deepEqual(Array.from(world.delivered, entry => Array.from(entry)), expected[index]);
    assert.equal(config.cues[index].steps.length, expected[index].length * 2);
    assert.equal(world.carried, null);
  }
  rejectStart(rules, levels[0]);
});
