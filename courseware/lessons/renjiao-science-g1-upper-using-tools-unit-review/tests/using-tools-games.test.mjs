import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const read = name => readFileSync(new URL(name, import.meta.url), 'utf8');

function mechanic(page, template) {
  let game;
  const K = {
    ready() {},
    $: () => ({ prepend() {}, content: { cloneNode() {} } }),
    game: value => { game = value; },
  };
  const scope = vm.createContext({ K, capture: (config, rules) => ({ config, rules }) });
  vm.runInContext(read('../../../kit/game_templates/classic.js') + '\nClassic.create = capture;', scope);
  vm.runInContext(read('../../../kit/game_templates/' + template + '.js'), scope);
  vm.runInContext(read('../pages/' + page + '.js'), scope);
  return game;
}

function play(config, rules, level, number) {
  rules.validate(level, number);
  const world = rules.reset(level);
  const hits = [], observations = [];
  const feedback = {
    move() {}, drop() {}, fx() {}, resetCheckpoint() {},
    award(x, y) { hits.push([x, y]); },
    observe(id, pair) { observations.push({ id, ...pair }); },
    lost() { assert.fail('The pilot triggered a miss'); },
  };
  const imgs = { icons: new Map(Object.keys(config.art.icons).map(key => [key, { complete: true, naturalWidth: 320 }])) };
  const goal = rules.goal(level);
  for (let frame = 0; frame < 3600 && hits.length < goal; frame++) {
    rules.update(world, level, rules.pilot(world, level), 1 / 60, feedback, imgs);
  }
  assert.equal(hits.length, goal);
  return { hits, observations };
}

test('the tool depot routes each tool to its pictured task on three levels', () => {
  const { config, rules } = mechanic('sort-tools', 'sortingDepot');
  const group = { scissors: 'cut', tongs: 'grip', driver: 'turn', stencil: 'trace' };
  const tasks = { cut: 'cut', ring: 'grip', screw: 'turn', triangle: 'trace' };
  assert.deepEqual(Array.from(config.levels, level => level.items.length), [2, 3, 4]);
  for (const [number, level] of config.levels.entries()) {
    for (const item of level.items) assert.equal(item.group, group[item.token]);
    for (const dock of level.docks) assert.equal(dock.group, tasks[dock.sample]);
    const { hits } = play(config, rules, level, number);
    if (number === 0) assert.deepEqual(hits[0], [781, 342]);
  }
});

test('the camera saves the exact two views listed on each level of the observation card', () => {
  const { config, rules } = mechanic('tool-camera', 'shutterScout');
  const lesson = JSON.parse(read('../lesson.json'));
  const camera = lesson.scenes.find(scene => scene.key === 'tool-camera');
  assert.equal(config.observation.sceneId, 'scene-' + camera.key);
  for (const [number, level] of config.levels.entries()) {
    const trial = camera.observationCard.levels[number].trials[0];
    const { observations } = play(config, rules, level, number);
    assert.deepEqual(observations, [{ id: trial.id, top: level.photoViews.top, side: level.photoViews.side }]);
    for (const view of ['top', 'side']) {
      const id = level.photoViews[view];
      assert.equal(trial[view][id].image, id);
      assert.equal(config.art.icons[id], `__IMG:${id}__`);
    }
  }
});
