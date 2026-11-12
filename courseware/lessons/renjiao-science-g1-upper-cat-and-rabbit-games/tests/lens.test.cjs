const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {test} = require('node:test');
const vm = require('node:vm');

test('the observation lens follows the body in either facing direction', () => {
  let plan;
  vm.runInNewContext(readFileSync(join(__dirname, '../pages/lens.js'), 'utf8'), {
    K: {ready() {}, game(config) { plan = config; }, gameTemplates: {trace: config => config}}
  });
  assert.deepEqual(Array.from(plan.levels, l => l.rounds.length), [1, 2]);
  const [cat, white, mirroredBrown] = plan.levels.flatMap(l => l.rounds);
  for (const round of [cat, white, mirroredBrown]) {
    const [route] = round.strokes;
    assert.equal(round.vehicle, 'lens');
    assert.equal(route.length, 8);
    for (const [x, y] of route) {
      assert.ok(x >= 160 && x <= 1120 && y >= 220 && y <= 640);
    }
    assert.ok(route[4][1] > route[2][1] && route[5][1] > route[2][1], 'visit legs below the trunk');
  }
  assert.ok(cat.strokes[0][0][0] < cat.strokes[0].at(-1)[0], 'cat faces left');
  assert.ok(white.strokes[0][0][0] < white.strokes[0].at(-1)[0], 'white rabbit faces left');
  assert.equal(mirroredBrown.mirrorImage, true);
  assert.ok(mirroredBrown.strokes[0][0][0] > mirroredBrown.strokes[0].at(-1)[0], 'brown rabbit faces right');
});
