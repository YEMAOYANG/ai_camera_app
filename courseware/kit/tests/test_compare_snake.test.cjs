const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const kit = path.join(__dirname, '..');
const read = file => JSON.parse(fs.readFileSync(path.join(kit, file), 'utf8'));
const sample = read('examples/classic-arcade/compare-snake.json');
const shapes = read('examples/alternate/compare-snake-shapes.json');
const source = fs.readFileSync(path.join(kit, 'game_templates/compareSnake.js'), 'utf8');
const dt = 1 / 60;

function gameFor(level) {
  const dots = [];
  const K = {gameTemplates: {}, draw: {circle(context, x, y) {
    if (context.fillStyle === '#9c4b2a') dots.push([x, y]);
  }}};
  const Classic = {
    create: (_, mechanic) => mechanic,
    bot: (...keys) => ({press: key => keys.includes(key)}),
    validToken: value => typeof value === 'string' && value.length > 0 || Number.isFinite(value),
    box() {}, center: (x, y, w, h) => [x, y, w, h], sprite() { return false; }, text() {}, token() {},
  };
  vm.runInNewContext(source, {K, Classic});
  const game = K.gameTemplates.compareSnake({});
  game.validate(level, 0);
  const world = game.reset(level);
  let progress = 0;
  let misses = 0;
  function advance(input) {
    game.update(world, level, input, dt, {
      award() { progress++; },
      lost() { misses++; game.adapt(world, misses); },
      fx() {}, move() {},
    });
  }
  return {
    world, game, dots,
    get progress() { return progress; },
    get misses() { return misses; },
    press: key => advance(Classic.bot(key)),
    idle: frames => { for (let i = 0; i < frames; i++) advance(Classic.bot()); },
    autopilot() {
      for (let i = 0; i < 7200 && progress < game.goal(level); i++) advance(game.pilot(world, level, dt));
    },
  };
}

test('a legal bite grows the snake and replaces the reference with the quantity it ate', () => {
  const play = gameFor(sample.levels[0]);
  play.press('up');
  play.idle(48);
  assert.equal(play.progress, 1);
  assert.equal(play.world.ref, 4);
  assert.equal(play.world.body.length, 3);
  play.press('action');
  assert.equal(play.world.body[0], 55);
  assert.equal(play.world.body.length, 3);
  assert.equal(play.world.ref, 4);
  assert.equal(play.progress, 1);
  play.autopilot();
  assert.equal(play.progress, 2);
  assert.equal(play.world.ref, 6);
  assert.equal(play.misses, 0);
});

test('a smaller food is rejected twice, and the next move runs at the assisted speed', () => {
  const level = structuredClone(sample.levels[0]);
  level.rounds[0].foods[1] = [5, 4, 1];
  const play = gameFor(level);
  play.press('up');
  assert.equal(play.world.help, false);
  play.press('up');
  assert.equal(play.misses, 2);
  assert.equal(play.world.help, true);
  assert.equal(play.world.body.length, 2);
  assert.equal(play.world.ref, 2);
  assert.equal(play.progress, 0);
  play.press('right');
  assert.ok(play.world.cooldown > level.seconds);
  play.autopilot();
  assert.equal(play.progress, 2);
});

test('the compare board draws the exact number of filled marks on each quantity card', () => {
  const level = sample.levels[0];
  const play = gameFor(level);
  const context = {save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}};
  play.game.draw(play.world, level, context, {frames: []}, {t: 0});
  const groups = [play.dots.filter(([x]) => x > 1040).length,
    play.dots.filter(([x]) => x > 590 && x < 677).length,
    play.dots.filter(([x]) => x > 765 && x < 833).length];
  assert.deepEqual(groups, [2, 4, 1]);
  assert.deepEqual(Array.from(play.game.goalAnchor()), [1127, 277, 135, 90]);
  assert.deepEqual(Array.from(play.game.target(play.world)), [634, 376, 70, 54]);
});

test('a food card stays above the body when a round places food on an occupied tile', () => {
  const level = sample.levels[0];
  const play = gameFor(level);
  play.world.body = [45, 35];
  play.world.previous = play.world.body;
  const context = {save() {}, restore() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}};
  play.game.draw(play.world, level, context, {frames: []}, {t: 0});
  const card = play.dots.filter(([x]) => x > 590 && x < 677);
  assert.equal(card.length, 4);
  assert.ok(card.every(([, y]) => y < 370));
  assert.deepEqual(Array.from(play.game.target(play.world)), [634, 358, 70, 38]);
});

test('the alternate example groups rotated triangles while rejecting a different shape', () => {
  const play = gameFor(shapes.levels[0]);
  play.press('up');
  play.idle(48);
  assert.equal(play.progress, 1);
  assert.equal(play.world.ref, 'triangle-b');
  for (const level of shapes.levels) {
    const shapePlay = gameFor(level);
    shapePlay.autopilot();
    assert.equal(shapePlay.progress, level.rounds.length);
    assert.equal(shapePlay.misses, 0);
  }
});
