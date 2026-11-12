import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const script = readFileSync(new URL('../game_templates/trace.js', import.meta.url), 'utf8');

test('pointer can continue through a corner reached within floating point precision', () => {
  const pointer = {down: true};
  const messages = [];
  let trace;
  const tools = {
    register: (_, mechanic) => { trace = mechanic; },
    distance: (a, b) => Math.hypot(a.x - b.x, a.y - b.y),
    clamp: (value, lower, upper) => Math.min(upper, Math.max(lower, value)),
    getInput: () => ({pointer}),
    hint: () => messages.push('hint'),
    success: () => messages.push('success')
  };
  runInNewContext(script, {K: {gameTemplates: {tools}}});

  const round = {strokes: [[[200, 240], [245, 294], [312, 372]]]};
  const world = trace.reset(round, 1);
  function drag(x, y) {
    Object.assign(pointer, {x, y});
    trace.update({}, world, round, 1 / 60);
  }

  drag(200, 240);
  const almostThere = 1 - 1e-15;
  for (let frame = 1; frame <= 18; frame++) {
    const ratio = almostThere * frame / 18;
    drag(200 + 45 * ratio, 240 + 54 * ratio);
  }
  const corner = Math.hypot(45, 54);
  assert(world.s < corner && corner - world.s < 1e-10);

  for (let frame = 1; frame <= 30; frame++) {
    const ratio = Math.min(1, (0.5 + frame / 50));
    drag(245 + 67 * ratio, 294 + 78 * ratio);
    if (messages.length) break;
  }
  assert.deepEqual(messages, ['success']);
});
