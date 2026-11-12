import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const frame = 1 / 60;
const image = class {
  complete = true;
  naturalWidth = 1024;
  naturalHeight = 576;
};

function loadGame(name) {
  let game;
  const K = {
    ready() {},
    draw: {},
    sfx: {pick() {}},
    game(config) { game = config; }
  };
  const script = new URL('../pages/' + name + '.js', import.meta.url);
  runInNewContext(readFileSync(script, 'utf8'), {K, Image: image});
  return game;
}

function run(game, level) {
  const g = {
    data: {}, pointer: {down: true, x: 0, y: 0}, keys: {}, level, won: false, notes: [],
    say(text, kind) { this.notes.push({text, kind}); }, sparkle() {},
    win() { this.won = true; }
  };
  game.reset(g, level);
  return g;
}

function advance(game, g, seconds, usePilot = false) {
  for (let i = 0; i < Math.ceil(seconds / frame) && !g.won; i++) {
    if (usePilot) game.autopilot(g, frame);
    game.update(g, frame);
  }
}

test('camera must settle on the correct fish region, and writes three real snapshots', () => {
  const game = loadGame('lens');
  const g = run(game, 0);
  assert.equal(g.pointer.down, false, 'handoff releases the teacher pointer');
  g.pointer = {x: 665, y: 408, down: true};
  advance(game, g, 1.9);
  assert.equal(g.data.album.shots.length, 0, 'aiming at the tail cannot satisfy the first task');
  assert.equal(g.notes.at(-1).kind, 'no');
  g.pointer = {x: 290, y: 398, down: true};
  advance(game, g, .30);
  assert.equal(g.data.album.shots.length, 0, 'passing over the right spot does not take a picture');
  advance(game, g, 1.3);
  assert.equal(g.data.album.shots.length, 1);
  assert.equal(g.data.album.shots[0].part, 0);
  assert.equal(g.data.album.shots[0].fish.facingRight, false);
  g.pointer = {x: 440, y: 403, down: true};
  advance(game, g, 1.1);
  assert.equal(g.data.album.shots.length, 2);
  g.pointer = {x: 634, y: 414, down: true};
  advance(game, g, 1.1);
  assert.equal(g.won, true);
  assert.deepEqual(Array.from(g.data.album.shots, shot => shot.part), [0, 1, 2]);
  assert(g.data.album.shots[2].fish.x < g.data.album.shots[0].fish.x, 'fish really moved between photographs');
});

test('camera robot uses the same pointer speed and exposure in all levels', () => {
  const game = loadGame('lens');
  for (let level = 0; level < game.levels; level++) {
    const g = run(game, level);
    advance(game, g, 13, true);
    assert.equal(g.won, true, 'level ' + level);
    assert.equal(g.data.album.shots.length, 3);
  }
});

test('filmer cannot record another action or store an unfinished recording', () => {
  const game = loadGame('evidence');
  const g = run(game, 0);
  assert.equal(g.pointer.down, false, 'handoff releases the teacher shutter');
  g.pointer = {x: 441, y: 620, down: false};
  advance(game, g, 2);
  g.pointer.down = true;
  advance(game, g, 2.5);
  g.pointer.down = false;
  advance(game, g, .1);
  assert.equal(g.data.film.clips.length, 0, 'feeding is not evidence of swimming');
  assert.equal(g.notes.at(-1).kind, 'no');
  advance(game, g, 2.4);
  g.pointer.down = true;
  advance(game, g, 1.1);
  g.pointer.down = false;
  advance(game, g, .03);
  assert.equal(g.data.film.clips.length, 0);
  assert.match(g.notes.at(-1).text, /松得早/);
  advance(game, g, 30, true);
  assert.equal(g.won, true);
  assert.equal(g.data.film.clips[0].kind, 'swim');
  assert.equal(g.data.film.clips[0].frames.length, 3);
});

test('filmer robot records three distinct moments and completes all three levels', () => {
  const game = loadGame('evidence');
  const expected = [['swim'], ['feed'], ['gill', 'swim']];
  for (let level = 0; level < game.levels; level++) {
    const g = run(game, level);
    advance(game, g, 40, true);
    assert.equal(g.won, true, 'level ' + level);
    assert.deepEqual(Array.from(g.data.film.clips, clip => clip.kind), expected[level]);
    for (const clip of g.data.film.clips) {
      assert(clip.frames[0] < clip.frames[1] && clip.frames[1] < clip.frames[2]);
      assert(clip.from < clip.frames[0] && clip.frames[2] < clip.until,
        'stored replay boundaries cover the actual captured frames');
    }
  }
});

test('holding across a change of action cannot enter a mixed clip into the album', () => {
  const game = loadGame('evidence');
  const g = run(game, 0);
  advance(game, g, 7.1);
  g.pointer = {x: 441, y: 620, down: true};
  advance(game, g, 5.5);
  g.pointer.down = false;
  advance(game, g, .03);
  assert.equal(g.data.film.clips.length, 0);
  assert.match(g.notes.at(-1).text, /另一个动作/);
});
