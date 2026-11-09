const assert = require('node:assert/strict');
const test = require('node:test');
const shore = require('../pages/shore-move.js');
const basket = require('../pages/basket.js');

test('shore order cannot skip ahead and accepts a retry', () => {
  let state = shore.next(shore.initial(), 'touch');
  assert.deepEqual(state, { step: 0, misses: 1, finished: false });
  state = ['come', 'touch', 'return'].reduce(shore.next, state);
  assert.deepEqual(state, { step: 3, misses: 1, finished: true });
  assert.deepEqual(shore.next(state, 'reset'), shore.initial());
});

test('teacher demonstrations do not advance either learner state', () => {
  for (const activity of [shore, basket]) {
    const state = activity.initial();
    assert.strictEqual(activity.next(state, 'demo'), state);
  }
});

test('basket accepts both gift orders, with one occupied slot per distinct item', () => {
  for (const items of [['shell', 'shrimp'], ['shrimp', 'shell']]) {
    let state = basket.next(basket.initial(), 'extra');
    assert.deepEqual(state, { placed: [], misses: 1, finished: false });
    state = basket.next(state, items[0]);
    assert.strictEqual(basket.next(state, items[0]), state);
    assert.equal(basket.next(state, 'extra').finished, false);
    state = basket.next(state, items[1]);
    assert.deepEqual(state.placed, items);
    state = basket.next(state, 'extra');
    assert.equal(state.finished, true);
    assert.deepEqual(state.placed, items);
    assert.deepEqual(basket.next(state, 'reset'), basket.initial());
  }
});
