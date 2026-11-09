const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
function rules(file, name) {
  const window = { __RULES_ONLY__: true };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../pages', file + '.js'), 'utf8'), { window });
  return window[name];
}
test('bell: first wrong action keeps the scene playable; correct action finishes once; reset is clean', () => {
  const r = rules('bell', 'BellRules');
  const wrong = r.choose(r.fresh(), 'play');
  assert.equal(wrong.done, false); assert.equal(wrong.misses, 1);
  const done = r.choose(wrong, 'walk');
  assert.equal(done.done, true); assert.equal(r.choose(done, 'walk'), done);
  assert.equal(r.fresh().done, false); assert.equal(r.fresh().misses, 0);
});
test('desk: wrong item and wrong position never move objects or award progress', () => {
  const r = rules('desk', 'DeskRules');
  let s = r.drop(r.fresh(), 'case', 'case');
  assert.equal(s.placed.length, 0);
  s = r.drop(s, 'book', 'case'); assert.equal(s.placed.length, 0);
  s = r.drop(s, 'book', 'stack'); assert.equal(s.placed.join(','), 'book');
  s = r.drop(s, 'book', 'stack'); assert.equal(s.placed.join(','), 'book');
  s = r.drop(s, 'note', 'stack'); s = r.drop(s, 'case', 'case');
  assert.equal(s.placed.join(','), 'book,note,case');
  assert.equal(r.drop(s, 'case', 'case'), s); assert.equal(r.fresh().placed.length, 0);
});
test('turn: speaking early never advances; used cards cannot count twice; full sequence and replay work', () => {
  const r = rules('turn', 'TurnRules');
  let s = r.choose(r.fresh(), 'speak'); assert.equal(s.steps.length, 0);
  s = r.choose(s, 'listen'); assert.equal(s.steps.join(','), 'listen');
  const used = r.choose(s, 'listen'); assert.equal(used, s);
  s = r.choose(s, 'speak'); assert.equal(s.steps.join(','), 'listen');
  s = r.choose(s, 'hand'); s = r.choose(s, 'speak');
  assert.equal(s.steps.join(','), 'listen,hand,speak');
  assert.equal(r.choose(s, 'speak'), s); assert.equal(r.fresh().steps.length, 0);
});
