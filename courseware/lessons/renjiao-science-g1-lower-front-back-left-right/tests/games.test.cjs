const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {runInNewContext} = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const root = join(__dirname, '..');
const lesson = JSON.parse(readFileSync(join(root, 'lesson.json'), 'utf8'));
function config(page, template) {
  let value;
  const K = {ready() {}, game(result) {value = result;}, gameTemplates: {[template]: options => options}};
  runInNewContext(readFileSync(join(root, 'pages', page + '.js'), 'utf8'), {K});
  return JSON.parse(JSON.stringify(value));
}

test('delivery orders switch referent, then require relative front and back', () => {
  const game = config('costume-delivery', 'listenDelivery');
  const expected = [
    [['purple-drum','orange-crate']],
    [['blue-lantern','triangle-shaker'],['orange-crate','green-flag']],
    [['purple-drum','orange-crate'],['blue-lantern','triangle-shaker']],
  ];
  assert.deepEqual(game.levels.map(level => level.orders), expected);
  for (const [index, level] of game.levels.entries()) {
    assert.match(level.pickup.find(([,col]) => col === 4)[0], /^green-ref-/);
    assert.match(level.drop.find(([,col]) => col === 4)[0], /^star-ref-/);
    assert.equal(game.cues[index].steps.length, level.orders.length * 2);
  }
});

test('camera has one allowed pose-matched pair per level and gives a family task', () => {
  const game = config('camera-compare', 'shutterScout');
  const scene = lesson.scenes.find(scene => scene.key === 'camera-compare');
  assert.equal(game.observation.sceneId, 'scene-' + scene.key);
  const ids = game.observation.trials['stage-directions'];
  for (const [index, level] of game.levels.entries()) {
    const trial = scene.observationCard.levels[index].trials[0];
    assert.deepEqual([...new Set(level.shots)].sort(), [0,1]);
    for (const view of ['top','side']) {
      const id = level.photoViews[view];
      assert.equal(ids[view][index], id);
      assert.deepEqual(Object.keys(trial[view]), [id]);
      assert.equal(trial[view][id].image, id);
      assert.ok(lesson.images[id]);
    }
  }
  assert.match(scene.observationCard.familyTask, /原地转半圈/);
});
