import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

function canvasLog() {
  const calls = [];
  const methods = {
    createLinearGradient() { return {addColorStop() {}}; },
    globalCompositeOperation: 'source-over',
    drawImage(source, ...bounds) {
      calls.push(['image', source.src, this.globalCompositeOperation, ...bounds]);
    }
  };
  const context = new Proxy(methods, {
    get(target, key) {
      return key in target ? target[key] : (...args) => calls.push([key, ...args]);
    }
  });
  return {calls, context};
}

function drawing(page) {
  let game;
  const board = canvasLog();
  const sheet = canvasLog();
  const K = {
    ready() {},
    draw: {rr() {}, text() {}, circle() {}},
    game(config) { game = config; }
  };
  const Image = class {
    complete = true;
    naturalWidth = 1672;
    naturalHeight = 941;
  };
  const document = {createElement: () => ({src: 'tail-sheet', getContext: () => sheet.context})};
  const source = new URL('../pages/' + page + '.js', import.meta.url);
  runInNewContext(readFileSync(source, 'utf8'), {K, Image, document});
  return {game, board, sheet};
}

test('the fish and the magnifier both use the registered artwork with normal alpha', () => {
  const {game, board} = drawing('lens');
  const g = {pointer: {}, data: {}, level: 0};
  game.reset(g, 0);
  game.draw(g, board.context);
  const images = board.calls.filter(([name]) => name === 'image');
  const uses = key => images.filter(([, src]) => src === '__IMG:' + key + '__');
  assert.equal(uses('aquarium-water').length, 2, 'the lens magnifies the water behind the fish too');
  assert.equal(uses('fish-orange').length, 2);
  assert(uses('fish-orange').every(([, , mode]) => mode === 'source-over'));
  for (const key of ['clue-head', 'clue-scales', 'clue-tail']) assert.equal(uses(key).length, 1);
});

test('tail animation bends only the back third on a cleared transparent sheet', () => {
  const {game, board, sheet} = drawing('evidence');
  const g = {pointer: {}, data: {}, level: 0};
  game.reset(g, 0);
  g.data.film.time = 6.8;
  game.draw(g, board.context);
  assert.deepEqual(sheet.calls[0], ['clearRect', 0, 0, 512, 332]);
  assert.equal(sheet.calls.some(([name]) => name === 'fillRect'), false);
  const body = sheet.calls[1];
  assert.equal(body[1], '__IMG:fish-orange__');
  assert.deepEqual(body.slice(-4), [0, 22, 333, 288]);
  assert(sheet.calls.slice(2).every(call => call[7] >= 333));
  assert(board.calls.some(([name, source, mode]) =>
    name === 'image' && source === 'tail-sheet' && mode === 'source-over'));
});

test('the feeding and breathing motions sit at the illustrated mouth and gill cover', () => {
  const {game, board} = drawing('evidence');
  const g = {pointer: {}, data: {}, level: 0};
  game.reset(g, 0);
  g.data.film.time = 3.34;
  game.draw(g, board.context);
  const mouth = board.calls.find(([name]) => name === 'ellipse');
  assert(mouth && mouth[1] > 249 && mouth[1] < 260 && mouth[2] > 207 && mouth[2] < 215);
  g.level = 1;
  game.reset(g, 1);
  board.calls.length = 0;
  g.data.film.time = 1.04 + 4.25 / 6;
  game.draw(g, board.context);
  const covers = board.calls.filter(([name, x, y]) => name === 'quadraticCurveTo' && x > 250 && y > 180);
  assert(covers.some(([, , , endX, endY]) => endX > 215 && endX < 230 && endY > 272 && endY < 286));
});
