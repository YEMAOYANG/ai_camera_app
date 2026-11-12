import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = name => readFileSync(new URL('../pages/' + name + '.js', import.meta.url), 'utf8');

function gameConfig(page, template) {
  let cover, config;
  const K = {
    ready: value => { cover = value; },
    game: value => { config = value; },
    gameTemplates: { [template]: value => ({ ...value, draw() {} }) },
  };
  vm.runInNewContext(source(page), { K });
  return { cover, config };
}

test('parachute chooses an unambiguous picture partner at a reachable distance', () => {
  const { cover, config } = gameConfig('dui-parachute', 'parachute');
  const families = { rain: 'weather', wind: 'weather', flower: 'plant', tree: 'plant',
    bird: 'animal', insect: 'animal' };
  const category = visual => families[visual.image.match(/^__IMG:([^_]+)__$/)?.[1]];
  assert.equal(cover.img, '__IMG:duet__');
  assert.equal(config.levels.length, 2);
  assert.equal(config.levels[0].rounds[0].options.length, 2);
  assert.equal(config.levels[1].rounds[0].options.length, 4);
  for (const level of config.levels) {
    for (const round of [...level.rounds, ...(level.demoRounds ?? [])]) {
      const goal = category(round.goal);
      assert.ok(goal, 'A registered image identifies the goal');
      const matches = Array.from(round.options, (option, i) => category(option) === goal ? i : -1)
        .filter(i => i >= 0);
      assert.deepEqual(matches, [round.answer]);
      assert.ok(1280 / round.options.length - 2 * 27 > 148, 'Moving picture cards do not overlap');
      const fallSecondsAtFastestLevel = (570 - 289) / (94 + 16);
      assert.ok(500 * fallSecondsAtFastestLevel > 640, 'The basket can reach either side before landing');
    }
  }
});

test('rain motion cues mark the registered rain image only', () => {
  const { config } = gameConfig('dui-parachute', 'parachute');
  const { demoRounds, rounds } = config.levels[0];
  const starts = [];
  const c = { save() {}, restore() {}, beginPath() {}, lineTo() {}, stroke() {},
    moveTo: (x, y) => starts.push([x, y]) };
  const world = { centers: [320, 960], y: 330, age: 0.8, rest: 0 };
  const draw = (plan, round) => config.draw({ t: 2, data: { plan: { rounds: plan }, round, world } }, c);
  draw(demoRounds, 0);
  assert.equal(starts.length, 3);
  assert.ok(starts.every(([x, y]) => Math.abs(x - 640) <= 14 && y < 130));
  starts.length = 0;
  draw(rounds, 0);
  assert.deepEqual(starts, []);
  draw(rounds, 1);
  assert.equal(starts.length, 3);
  assert.ok(starts.every(([x, y]) => Math.abs(x - 320) <= 14 && y < 330));
});

test('trace starts with a standalone 提 and keeps each of 虫’s six paths inside the grid', () => {
  const { cover, config } = gameConfig('dui-trace', 'trace');
  assert.equal(cover.img, '__IMG:duet__');
  const [lift, bug] = Array.from(config.levels, level => level.rounds[0]);
  assert.equal(lift.goal, '提');
  assert.equal(lift.strokes.length, 1);
  assert.equal(bug.goal, '虫');
  assert.equal(bug.strokes.length, 6);
  for (const round of [lift, bug]) {
    const [x, y, size] = round.gridBox;
    for (const stroke of round.strokes) {
      assert.ok(stroke.length >= 2);
      for (const [px, py] of stroke) {
        assert.ok(Math.abs(px - x) <= size / 2 && Math.abs(py - y) <= size / 2);
      }
      assert.ok(Math.hypot(stroke.at(-1)[0] - stroke[0][0], stroke.at(-1)[1] - stroke[0][1]) > 24);
    }
  }
  for (const stroke of [lift.strokes[0], bug.strokes[4]]) {
    assert.ok(stroke.at(-1)[0] > stroke[0][0] && stroke.at(-1)[1] < stroke[0][1],
      'The writing direction goes from the lower left to the upper right');
  }
});
