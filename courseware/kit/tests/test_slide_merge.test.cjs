const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const kit = path.join(__dirname, '..');
const {levels} = JSON.parse(fs.readFileSync(path.join(kit, 'examples/classic-arcade/pinyin-slide.json'), 'utf8'));

function gameFor(level) {
  const K = {gameTemplates: {}};
  const Classic = {
    create: (_, mechanic) => mechanic,
    bot: direction => direction,
    validToken: value => typeof value === 'string' && value.length > 0 || Number.isFinite(value),
    box() {}, sprite() {}, token() {}, text() {},
  };
  vm.runInNewContext(fs.readFileSync(path.join(kit, 'game_templates/slideMerge.js'), 'utf8'), {K, Classic});
  const game = K.gameTemplates.slideMerge({});
  game.validate(level, 0);
  const world = game.reset(level);
  let misses = 0;
  let score = 0;
  return {
    world, game,
    get misses() { return misses; },
    get score() { return score; },
    press(key) {
      game.update(world, level, {press: name => name === key}, .5, {
        lost() { misses++; game.adapt(world, misses); },
        award() { score++; },
        resetCheckpoint() { score = 0; },
        move() {}, fx() {},
      });
    },
  };
}

test('each goal needs its own pair, even when another pair could form a different syllable', () => {
  const level = structuredClone(levels[1]);
  level.pairs.push(['p', 'ā', 'pā']);
  const play = gameFor(level);
  play.press('right');
  assert.equal(play.score, 1);
  assert.deepEqual(Array.from(play.world.remaining), ['bā', 'pō', null]);
  assert.equal(play.world.board[3], 'ā');
  assert.equal(play.world.board[2], 'p');
});

test('a wall splits the lane, and a numeric recipe works without any syllable data', () => {
  const level = {
    board: [[1, null, 2, null], ...Array.from({length: 3}, () => Array(4).fill(null))],
    walls: [1], pairs: [[1, 2, 3]], targets: [3], seconds: .30,
  };
  const play = gameFor(level);
  play.press('right');
  assert.equal(play.score, 0);
  assert.equal(play.world.board[0], 1);
  assert.equal(play.world.board[3], 2);
  play.press('down');
  play.press('left');
  assert.deepEqual(Array.from(play.world.remaining), [null]);
  assert.equal(play.score, 1);
});

test('two blocked moves unlock a route hint and restarting clears the collection', () => {
  const play = gameFor(levels[0]);
  play.press('up');
  play.press('up');
  assert.equal(play.world.help, false);
  play.press('up');
  assert.equal(play.misses, 2);
  assert.equal(play.world.help, true);
  assert.equal(play.world.suggestion, 'left');
  play.press('left');
  assert.equal(play.score, 1);
  play.press('action');
  assert.deepEqual(Array.from(play.world.remaining), ['bā']);
  assert.equal(play.score, 0);
  assert.equal(play.world.help, true);
});

test('a combining tone is centered on the marked letter rather than the whole syllable', () => {
  const level = levels[0];
  const {game, world} = gameFor(level);
  const strokes = [];
  let path;
  const canvas = {
    save() {}, restore() {},
    measureText: value => ({width: value.length * 24}),
    beginPath() { path = []; },
    moveTo(x) { path.push(x); }, lineTo(x) { path.push(x); },
    stroke() { strokes.push(path); },
  };
  game.draw(world, level, canvas, {frames: [], icons: new Map()}, {t: 0});
  assert.equal(strokes.length, 2);
  const centers = strokes.map(([left, right]) => (left + right) / 2);
  assert.deepEqual(centers, [570, 884]); // Base letter on the board, last letter of bɑ on the shelf.
});
