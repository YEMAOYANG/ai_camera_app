import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { runInNewContext } from 'node:vm';

test('the last completed order keeps its matched target for the teacher', () => {
  const context = {
    K: { gameTemplates: {}, ready() {}, $: () => null, game: () => ({ follow() {} }) },
    Classic: {
      bot: (...keys) => ({ held: key => keys.includes(key), press: key => keys.includes(key) }),
      center: (x, y, width, height) => ({ x, y, width, height }),
      clamp: (value, min, max) => Math.max(min, Math.min(max, value)),
      validToken: value => typeof value === 'string' || Number.isFinite(value),
      match: (order, value, level) => level.matches(order, value),
      create(config, mechanic) {
        context.level = config.levels[0];
        context.mechanic = mechanic;
      },
    },
  };
  for (const path of ['../../../kit/game_templates/magnetMarbles.js', '../pages/aim-at-the-remainder.js']) {
    runInNewContext(readFileSync(new URL(path, import.meta.url), 'utf8'), context);
  }

  const { level, mechanic } = context;
  mechanic.validate(level);
  const world = mechanic.reset(level);
  let awards = 0;
  const feedback = {
    award: () => { awards += 1; },
    move() {}, jump() {}, drop() {}, fx() {},
    lost: () => assert.fail('the first demo shot should match its order'),
  };
  for (let frame = 0; frame < 120 && awards === 0; frame += 1) {
    mechanic.update(world, level, mechanic.pilot(world, level), 1 / 60, feedback);
  }

  assert.equal(awards, 1);
  assert.equal(world.i, level.queue.length);
  assert.equal(world.locked.value, 50);
  assert.deepEqual(mechanic.target(world, level), { x: 785, y: 229, width: 141, height: 113 });
});
