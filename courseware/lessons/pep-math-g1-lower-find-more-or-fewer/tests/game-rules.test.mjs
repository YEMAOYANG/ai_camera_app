import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = file => readFileSync(new URL(file, import.meta.url), 'utf8');
const cards = JSON.parse(source('../asset-sources.json')).assets;
const bot = (...pressed) => ({
  press: key => pressed.includes(key),
  held: key => pressed.includes(key),
});

function loadGame(template, lessonPage) {
  let loaded;
  const stage = {append() {}};
  const element = () => ({
    setAttribute() {},
    getAttribute() { return ''; },
    style: {},
  });
  const Classic = {
    box() {}, text() {}, sprite() {}, token() {}, center() {},
    create(config, mechanic) {
      loaded = {config, mechanic};
      return {draw() {}};
    },
    bot,
    ease(_current, target) { return target; },
    validToken: value => typeof value === 'string' || Number.isFinite(value),
    match: (left, right, level) => level.matches(left, right),
  };
  const K = {
    gameTemplates: {}, ready() {}, game() {}, stage: () => stage, $: element, el: element,
  };
  const context = vm.createContext({K, Classic});
  vm.runInContext(source(`../../../kit/game_templates/${template}.js`), context);
  vm.runInContext(source(`../pages/${lessonPage}.js`), context);
  return loaded;
}

function exerciseGame(game) {
  const {config, mechanic} = game;
  for (const level of config.levels) mechanic.validate(level);
  for (let attempt = 0; attempt < 2; attempt++) {
    for (const level of config.levels) {
      const world = mechanic.reset(level);
      let progress = 0;
      let misses = 0;
      const feedback = {
        fx() {}, move() {}, drop() {},
        award() { progress++; },
        lost() {
          misses++;
          mechanic.adapt(world, misses);
        },
      };
      const dt = .03;
      if (attempt === 0 && level === config.levels[1]) {
        mechanic.update(world, level, bot('action'), dt, feedback);
        assert.equal(progress, 0, 'A wrong action cannot count as success.');
        assert.equal(misses, 1);
      }
      for (let tick = 0; tick < 6000 && progress < mechanic.goal(level); tick++) {
        mechanic.update(world, level, mechanic.pilot(world, level, dt), dt, feedback);
      }
      assert.equal(progress, mechanic.goal(level), 'The template can complete a reset level.');
    }
  }
}

test('falling cards match only the result of their pictured comparison', () => {
  const game = loadGame('fallingTiles', 'arrange-prop-tiles');
  for (const level of game.config.levels) {
    assert.equal(level.matches(undefined, undefined), false);
    for (const order of level.pieces) {
      const {reference, signedGap} = cards[order].semantics;
      const answers = level.bottom.filter(total => level.matches(order, total));
      assert.deepEqual(Array.from(answers), [reference + signedGap]);
      assert.equal(level.matches(order, reference), false);
    }
  }
  exerciseGame(game);
});

test('each delivery chooses the pictured result before its separately announced window', () => {
  const game = loadGame('listenDelivery', 'deliver-the-right-count');
  game.config.levels.forEach((level, levelIndex) => {
    const cue = game.config.cues[levelIndex];
    assert.equal(cue.steps.length, level.orders.length * 2);
    level.orders.forEach(([total, window], orderIndex) => {
      const order = level.comparisons[orderIndex];
      const {reference, signedGap} = cards[order].semantics;
      assert.equal(total, reference + signedGap);
      assert.equal(cue.steps[2 * orderIndex], order);
      assert.equal(cue.steps[2 * orderIndex + 1], 'take-to-' + window);
      assert.equal(cards[`delivery-total-${total}`].semantics.value, total);
    });
  });
  exerciseGame(game);
});

test('the six quiz answers follow the pictured geometry and are unique', () => {
  const lesson = JSON.parse(source('../lesson.json'));
  const questions = lesson.scenes.filter(scene => scene.type === 'quiz').flatMap(scene => scene.questions);
  const predicates = [
    spec => spec.bracket[0] === 1 && spec.bracket[1] === 0 && spec.bracket[2] === 7 + 4,
    spec => spec.rows[1][1] === 13 - 5 && spec.rows[1][2] === 5,
    spec => spec.value === 28 + 7,
    spec => spec.value === 21 - 8,
    spec => spec.rows[0][1] === 34 + 12 && spec.rows[1][1] === 34 && spec.rows[2][1] === 34 - 6,
    spec => spec.rows[0][1] - spec.rows[1][1] === 6 && spec.rows[1][1] === 19 && spec.bracket[3] === 6,
  ];
  assert.equal(questions.length, predicates.length);
  questions.forEach((question, index) => {
    const valid = Object.entries(question.options)
      .filter(([, option]) => predicates[index](cards[option.visual.image].semantics))
      .map(([letter]) => letter);
    assert.deepEqual(valid, question.answer);
  });
});
