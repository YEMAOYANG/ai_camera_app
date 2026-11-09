const test = require('node:test');
const assert = require('node:assert/strict');
const { makeChoice } = require('../pages/p02.js');
const { makePlacement: onPlacement } = require('../pages/p04.js');
const { makePlacement: underPlacement } = require('../pages/p07.js');
const { makeCounter } = require('../pages/p05.js');

test('colour discrimination keeps a first error retryable and resets success', () => {
  const game = makeChoice();
  assert.equal(game.choose('white'), 'wrong');
  assert.equal(game.done, false);
  assert.equal(game.choose('black'), 'wrong');
  assert.equal(game.choose('orange'), 'correct');
  assert.equal(game.choose('orange'), 'ignored');
  game.reset();
  assert.equal(game.done, false);
  assert.equal(game.wrongs, 0);
});

test('on and under remain distinct relative positions in both activities', () => {
  for (const [make, answer, wrong] of [[onPlacement, 'place-on', 'place-under'], [underPlacement, 'place-under', 'place-on']]) {
    const game = make(answer);
    assert.equal(game.place(wrong), 'wrong');
    assert.equal(game.place('place-in'), 'wrong');
    assert.equal(game.done, false);
    assert.equal(game.place(answer), 'correct');
    assert.equal(game.place(answer), 'ignored');
    game.reset();
    assert.equal(game.done, false);
    assert.equal(game.wrongs, 0);
  }
});

test('each cat counts once; eleven is not twelve; replay starts at zero', () => {
  const game = makeCounter(12);
  for (let id = 1; id <= 11; id++) assert.equal(game.touch(id), true);
  assert.equal(game.count(), 11);
  assert.equal(game.done(), false);
  assert.equal(game.touch(11), false);
  assert.equal(game.count(), 11);
  assert.equal(game.touch(12), true);
  assert.equal(game.done(), true);
  for (const bad of [0, -1, 13, '1', 1.5]) assert.equal(game.touch(bad), false);
  game.reset();
  assert.equal(game.count(), 0);
  assert.equal(game.done(), false);
  assert.equal(game.touch(12), true);
});
