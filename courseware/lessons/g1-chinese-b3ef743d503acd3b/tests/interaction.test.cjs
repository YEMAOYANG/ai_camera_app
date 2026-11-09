const test = require('node:test');
const assert = require('node:assert/strict');
const compose = require('../pages/p03.js');
const badge = require('../pages/p06.js');
const sort = require('../pages/p08.js');
const trace = require('../pages/p10.js');
test('composition never advances on a wrong or repeated part; all four complete', () => {
 const m = new compose.Model();
 for (const round of compose.rounds) {
  const before = m.round;
  assert.equal(m.choose('氏'), 'wrong');
  assert.equal(m.advance(), false);
  assert.deepEqual(m.parts, []);
  assert.equal(m.choose(round.parts[0]), 'accepted');
  assert.equal(m.choose(round.parts[0]), 'duplicate');
  assert.equal(m.choose(round.parts[1]), 'complete');
  assert.equal(m.round, before);
  assert.equal(m.advance(), true);
 }
 assert.equal(m.round, 4);
 assert.deepEqual(new compose.Model().parts, []);
});
test('name badge only accepts the explicit fictional surname and cannot score twice', () => {
 const m = new badge.Model();
 for (const [, surname] of badge.names) {
  assert.equal(m.choose('氏'), 'wrong');
  assert.equal(m.done, false);
  assert.equal(m.advance(), false);
  assert.equal(m.choose(surname), 'complete');
  assert.equal(m.choose(surname), 'duplicate');
  assert.equal(m.advance(), true);
 }
 assert.equal(m.round, 4);
});
test('whole compound surname remains one card; wrong home leaves both homes unchanged', () => {
 const m = new sort.Model();
 for (const card of sort.cards) {
  const expected = card.length === 1 ? 0 : 1;
  const before = JSON.stringify(m.homes);
  assert.equal(m.choose(1-expected), false);
  assert.equal(JSON.stringify(m.homes), before);
  assert.equal(m.choose(expected), true);
 }
 assert.equal(m.index, 8);
 assert.deepEqual(m.homes[1], ['欧阳','诸葛','东方','上官']);
 assert.deepEqual(new sort.Model().homes, [[],[]]);
});
test('trace records attempts only after real movement; clear and replay reset every observation', () => {
 const m = new trace.Model();
 m.addInk(NaN);m.addInk(-50);m.addInk(0);
 assert.equal(m.record(), false);
 m.addInk(1000000);
 assert.equal(m.record(), false);
 m.addInk(30);m.addInk(30);
 assert.equal(m.record(), true);
 assert.equal(m.record(), false);
 m.clear();assert.equal(m.ink[0], 0);assert.equal(m.recorded[0], false);
 for (let i=0;i<6;i++) {m.index=i;for(let k=0;k<3;k++)m.addInk(30);assert.equal(m.record(),true);}
 assert.equal(m.finished(),true);
 const replay=new trace.Model();assert.equal(replay.finished(),false);assert.deepEqual(replay.ink,[0,0,0,0,0,0]);
});
