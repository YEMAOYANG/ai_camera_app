const test = require('node:test');
const assert = require('node:assert/strict');
const surface = require('../pages/p02.js');
const nest = require('../pages/p06.js');
const wind = require('../pages/p08.js');
const tools = require('../pages/p10.js');

test('surface records require a loaded surface and an actual observation', () => {
  let state = surface.initial();
  state = surface.transition(state, 'record');
  assert.equal(state.records.length, 0);
  assert.equal(state.misses, 1);
  for (const key of ['table', 'cloth', 'ball', 'water']) {
    state = surface.transition(state, 'load', key);
    const premature = surface.transition(state, 'record');
    assert.equal(premature.records.length, state.records.length);
    state = surface.transition(state, 'blow');
    assert.equal(state.observed, true);
    state = surface.transition(state, 'record');
    assert.equal(state.object, null);
    assert.equal(state.observed, false);
  }
  assert.deepEqual(state.records, ['table', 'cloth', 'ball', 'water']);
  const duplicate = surface.transition(state, 'load', 'table');
  assert.equal(duplicate.object, null);
  assert.equal(duplicate.records.length, 4);
});

test('an active observation cannot be replaced before it is recorded', () => {
  let state = surface.transition(surface.initial(), 'load', 'water');
  state = surface.transition(state, 'blow');
  const replacement = surface.transition(state, 'load', 'ball');
  assert.equal(replacement.object, 'water');
  assert.equal(replacement.observed, true);
  assert.deepEqual(surface.transition(replacement, 'record').records, ['water']);
});

test('nested bubbles follow wet surface, outer bubble, careful straw insertion, inner bubble', () => {
  let state = nest.initial();
  for (const [event, target] of [['water'], ['large'], ['straw', 'center'], ['small']]) {
    state = nest.transition(state, event, target);
  }
  assert.equal(state.step, 4);
  assert.equal(state.misses, 0);
  assert.deepEqual(nest.initial(), { step: 0, misses: 0, popped: false });
});

test('wrong or premature nested actions preserve a retry and do not mark completion', () => {
  const premature = nest.transition(nest.initial(), 'small');
  assert.equal(premature.step, 0);
  let state = nest.transition(nest.transition(nest.initial(), 'water'), 'large');
  assert.equal(state.step, 2, 'transitions must not mutate prior snapshots');
  const edge = nest.transition(state, 'straw', 'edge');
  assert.equal(edge.popped, true);
  assert.equal(edge.step, 1);
  state = nest.transition(edge, 'large');
  state = nest.transition(state, 'straw', 'center');
  state = nest.transition(state, 'small');
  assert.equal(state.step, 4);
});

test('wind direction changes, so repeating the previous window does not pass', () => {
  assert.equal(wind.attempt(0, 'right'), true);
  assert.equal(wind.attempt(0, 'left'), false);
  assert.equal(wind.attempt(1, 'right'), false);
  assert.equal(wind.attempt(1, 'left'), true);
});

test('tool comparisons need observed results and three distinct tools', () => {
  let state = tools.initial();
  state = tools.transition(state, 'choose', 'sphere');
  assert.equal(state.records.length, 0);
  for (const key of ['heart', 'circle', 'star']) {
    state = tools.transition(state, 'load', key);
    const unseen = tools.transition(state, 'choose', 'sphere');
    assert.equal(unseen.records.length, state.records.length);
    state = tools.transition(state, 'blow');
    const mistaken = tools.transition(state, 'choose', 'rectangle');
    assert.equal(mistaken.blown, true, 'a wrong answer keeps the observed bubble available');
    assert.equal(mistaken.records.length, state.records.length);
    state = tools.transition(mistaken, 'choose', 'sphere');
  }
  assert.deepEqual(state.records, ['heart', 'circle', 'star']);
  const duplicate = tools.transition(state, 'load', 'circle');
  assert.equal(duplicate.tool, null);
  assert.equal(duplicate.records.length, 3);
});

test('changing tools cannot erase a result waiting to be recorded', () => {
  let state = tools.transition(tools.initial(), 'load', 'heart');
  state = tools.transition(state, 'blow');
  const replacement = tools.transition(state, 'load', 'star');
  assert.equal(replacement.tool, 'heart');
  assert.equal(replacement.blown, true);
  assert.deepEqual(tools.transition(replacement, 'choose', 'sphere').records, ['heart']);
});
