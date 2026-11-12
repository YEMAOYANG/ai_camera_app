import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const kit = new URL('../../../kit/game_templates/', import.meta.url);
const pages = new URL('../pages/', import.meta.url);
const read = (base, name) => readFileSync(new URL(name, base), 'utf8');

function loadGame(page, template) {
  let game;
  const removed = [];
  const states = [];
  const K = {
    ready() {},
    $: selector => selector === '#demo-flower'
      ? { classList: { remove: value => removed.push([selector, value]) } }
      : { prepend() {}, content: { cloneNode() {} } },
    $$: selector => {
      assert.equal(selector, '.teach-hl');
      return [{ classList: { remove: value => removed.push(value) } }];
    },
    onState: state => states.push(state),
    game: value => { game = value; },
  };
  const context = vm.createContext({ K, capture: (config, rules) => ({ config, rules }) });
  vm.runInContext(read(kit, 'classic.js') + '\nClassic.create = capture;', context);
  vm.runInContext(read(kit, template + '.js'), context);
  vm.runInContext(read(pages, page + '.js'), context);
  return { ...game, K, removed, states };
}

test('handing either game to the child clears the teacher highlight without skipping the shared reset', () => {
  for (const [page, template] of [['dui-falling-tiles', 'fallingTiles'], ['dui-sorting-depot', 'sortingDepot']]) {
    const { K, removed, states } = loadGame(page, template);
    K.onState({ demo: true, level: 1 });
    assert.deepEqual(removed, []);
    K.onState({ demo: false, level: 1 });
    assert.deepEqual(removed, ['teach-hl']);
    assert.deepEqual(states, [{ demo: true, level: 1 }, { demo: false, level: 1 }]);
  }
});

test('the depot removes the fixed flower highlight as the demonstration starts moving', () => {
  const { K, removed } = loadGame('dui-sorting-depot', 'sortingDepot');
  K.onState({ demo: true, level: 1, pause: true });
  assert.deepEqual(removed, []);
  K.onState({ pause: false });
  assert.deepEqual(removed, [['#demo-flower', 'teach-hl']]);
});

function play(rules, level, index) {
  rules.validate(level, index);
  const world = rules.reset(level);
  const hits = [];
  const feedback = {
    move() {}, drop() {}, fx() {}, resetCheckpoint() {},
    award(x, y) { hits.push([x, y]); },
    lost() { assert.fail('The pilot used a nonmatching picture'); },
  };
  const goal = rules.goal(level);
  for (let frame = 0; frame < 3600 && hits.length < goal; frame++) {
    rules.update(world, level, rules.pilot(world, level), 1 / 60, feedback);
  }
  assert.equal(hits.length, goal, 'The template must reach every lesson goal using its own rule');
  return hits;
}

function coverIncludes(page, pictures) {
  const cover = read(pages, page + '.html');
  for (const picture of pictures) assert.ok(cover.includes(`src="__IMG:${picture}__"`));
}

test('picture partners match on all three levels and the first move lands next to the highlighted tree', () => {
  const page = 'dui-falling-tiles';
  const { config, rules } = loadGame(page, 'fallingTiles');
  assert.deepEqual(Array.from(config.levels, level => level.pieces.length), [1, 2, 3]);
  for (const [index, level] of config.levels.entries()) {
    for (const picture of [...level.pieces, ...level.bottom.filter(Boolean)]) {
      assert.equal(config.art.icons[picture], `__IMG:${picture}__`);
    }
    const hits = play(rules, level, index);
    if (index === 0) assert.deepEqual(hits, [[675, 561]]);
  }
  coverIncludes(page, ['flower', 'tree', 'wind']);
});

test('picture depots use distinct categories and the first push goes to the highlighted plant tray', () => {
  const page = 'dui-sorting-depot';
  const { config, rules } = loadGame(page, 'sortingDepot');
  const groups = { flower: 'plant', tree: 'plant', bird: 'animal', insect: 'animal', rain: 'weather', wind: 'weather' };
  assert.deepEqual(Array.from(config.levels, level => level.items.length), [2, 3, 4]);
  for (const [index, level] of config.levels.entries()) {
    for (const item of [...level.items, ...level.docks]) {
      const picture = item.token ?? item.sample;
      assert.equal(item.group, groups[picture]);
      assert.equal(config.art.icons[picture], `__IMG:${picture}__`);
    }
    const hits = play(rules, level, index);
    if (index === 0) assert.deepEqual(hits[0], [781, 342]);
  }
  coverIncludes(page, ['trace-car', 'flower', 'tree', 'wind']);
});
