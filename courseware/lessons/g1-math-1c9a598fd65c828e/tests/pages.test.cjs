const assert = require('node:assert/strict');
const test = require('node:test');
const { createBirdGame } = require('../pages/count-birds.js');
const { createMarkGame } = require('../pages/mark-butterflies.js');
const { createShapeGame } = require('../pages/shape-sort.js');

test('point counting never counts the same bird twice and requires all five', () => {
  const game = createBirdGame(5);
  assert.equal(game.pick(2), true); assert.equal(game.pick(2), false);
  assert.equal(game.pick(-1), false); assert.equal(game.pick(5), false);
  assert.equal(game.count(), 1); assert.equal(game.complete(), false);
  for (const id of [4, 0, 3, 1]) assert.equal(game.pick(id), true);
  assert.equal(game.count(), 5); assert.equal(game.complete(), true);
  game.reset(); assert.equal(game.count(), 0); assert.equal(game.has(2), false);
});

test('persistent marks prevent repetition and cannot finish with a missing butterfly', () => {
  const game = createMarkGame(10);
  for (const id of [8, 0, 9, 2, 4, 7, 3, 6, 1]) assert.equal(game.mark(id), true);
  assert.equal(game.mark(8), false); assert.equal(game.count(), 9);
  assert.equal(game.complete(), false); assert.equal(game.mark(5), true);
  assert.equal(game.complete(), true); game.reset();
  assert.equal(game.count(), 0); assert.equal(game.complete(), false);
});

test('first wrong shape move preserves the task and does not reveal an answer', () => {
  const game = createShapeGame();
  const wrong = game.place('ball', 'long');
  assert.equal(wrong.ok, false); assert.equal(game.count(), 0);
  assert.equal(wrong.hint, '再看看外边的样子。');
  assert.equal(/球|书|圆|长方/.test(wrong.hint), false);
  assert.equal(game.place('ball', 'round').ok, true);
  assert.equal(game.place('ball', 'round').duplicate, true);
  assert.equal(game.complete(), false);
  assert.equal(game.place('book', 'long').ok, true);
  assert.equal(game.complete(), true); game.reset();
  assert.equal(game.count(), 0); assert.equal(game.has('book'), false);
});
