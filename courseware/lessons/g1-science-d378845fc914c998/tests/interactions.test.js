const test = require('node:test');
const assert = require('node:assert/strict');
const surface = require('../pages/surface-lab.js');
const nested = require('../pages/nested-lab.js');
const wind = require('../pages/wind-lab.js');
const tool = require('../pages/tool-lab.js');

test('surface exploration requires all four different places and preserves the prior observation', () => {
  const initial = [];
  let seen = surface.visit(initial, 'table');
  seen = surface.visit(seen, 'table');
  assert.deepEqual(initial, []);
  assert.deepEqual(seen, ['table']);
  assert.equal(surface.complete(seen), false);
  assert.deepEqual(surface.visit(seen, 'floor'), ['table']);
  for (const place of ['cloth', 'water', 'ball']) seen = surface.visit(seen, place);
  assert.equal(surface.complete(seen), true);
  assert.equal(surface.complete([]), false);
});

test('nested bubble activity never grants progress for skipped preparation or touching the edge', () => {
  for (const target of ['inner', 'edge', 'outside', 'table']) assert.equal(nested.next(0, target), 0);
  let step = nested.next(0, 'wet');
  assert.equal(nested.next(step, 'inner'), 1);
  step = nested.next(step, 'table');
  assert.equal(nested.next(step, 'edge'), 2);
  assert.equal(nested.next(step, 'outside'), 2);
  step = nested.next(step, 'inner');
  assert.equal(step, 3);
  assert.equal(nested.next(step, 'table'), 3);
  assert.equal(nested.next(0, 'inner'), 0);
});

test('wind prediction is relative to the current wind and rejects an invalid drop', () => {
  assert.equal(wind.correct(1, 'right'), true);
  assert.equal(wind.correct(1, 'left'), false);
  assert.equal(wind.correct(-1, 'left'), true);
  assert.equal(wind.correct(-1, 'right'), false);
  assert.equal(wind.correct(1, ''), false);
  assert.equal(wind.correct(0, 'left'), false);
});

test('each tool must be dipped itself and repeating one tool cannot count as comparison', () => {
  const initial = { dipped: null, used: [] };
  assert.deepEqual(tool.release(initial, 'round'), initial);
  let state = tool.dip(initial, 'round');
  assert.deepEqual(initial, { dipped: null, used: [] });
  assert.deepEqual(tool.release(state, 'square'), state);
  state = tool.release(state, 'round');
  state = tool.release(tool.dip(state, 'round'), 'round');
  assert.deepEqual(state, { dipped: null, used: ['round'] });
  state = tool.release(tool.dip(state, 'square'), 'square');
  assert.deepEqual(state, { dipped: null, used: ['round', 'square'] });
  assert.deepEqual(tool.dip(initial, 'unknown'), initial);
});
