const test = require('node:test');
const assert = require('node:assert/strict');
const { makeCount } = require('../pages/p03.js');
const { makeSelection } = require('../pages/p05.js');
const { makePlacement } = require('../pages/p07.js');

test('one bird contributes once and the final stamp counts twelve', () => {
  const count = makeCount();
  assert.equal(count.mark(5), 1);
  assert.equal(count.mark(5), 0);
  assert.equal(count.mark(12), 0);
  for (const index of [0, 1, 2, 3, 4, 6, 7, 8, 9, 10]) count.mark(index);
  assert.equal(count.mark(11), 12);
  count.reset();
  assert.equal(count.mark(5), 1);
});

test('other colours never enter the green count and replay clears selections', () => {
  const selection = makeSelection();
  assert.equal(selection.select(0), 0);
  assert.equal(selection.select(3), 0);
  assert.equal(selection.select(1), 1);
  assert.equal(selection.select(1), 0);
  for (const index of [2, 4, 6]) selection.select(index);
  assert.equal(selection.select(7), 5);
  selection.reset();
  assert.equal(selection.select(7), 1);
});

test('under must be placed before a false on-table claim can be rejected', () => {
  const placement = makePlacement();
  assert.equal(placement.confirm('no'), false);
  assert.equal(placement.drop('on'), false);
  assert.equal(placement.drop('under'), true);
  assert.equal(placement.confirm('yes'), false);
  assert.equal(placement.confirm('no'), true);
  assert.equal(placement.current(), 'complete');
  assert.equal(placement.confirm('no'), false);
  placement.reset();
  assert.equal(placement.current(), 'place');
});
