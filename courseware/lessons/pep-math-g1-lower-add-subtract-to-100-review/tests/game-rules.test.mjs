import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import {test} from 'node:test';

const lesson = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const kit = path.resolve(lesson, '../../kit/game_templates');
const read = (root, file) => fs.readFileSync(path.join(root, file), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));

function load(template, page) {
  let captured;
  const scope = vm.createContext({K: {
    ready() {},
    $(id) {
      return {id, attributes: {}, getAttribute(key) {return this.attributes[key];},
        setAttribute(key, value) {this.attributes[key] = value;}};
    },
    game(game) {
      captured = {...game, followers: new Map(), follow(selector, locate) {
        this.followers.set(typeof selector === 'string' ? selector : selector.id, locate);
      }};
      return captured;
    }
  }});
  vm.runInContext(read(kit, 'classic.js'), scope);
  // Exercise the real template validate/reset/update/pilot logic with no browser UI.
  vm.runInContext('Classic.create = (config, rules) => ({config, rules, input: Classic.bot})', scope);
  vm.runInContext(read(kit, template + '.js'), scope);
  vm.runInContext(read(lesson, 'pages/' + page + '.js'), scope);
  captured.config.levels.forEach(captured.rules.validate);
  return captured;
}

function play(game, level, drive, target = game.rules.goal(level)) {
  const state = game.rules.reset(level);
  const awards = [];
  const misses = [];
  const nothing = () => {};
  const fb = {award: (x, y) => awards.push([x, y]), lost: (x, y) => misses.push([x, y]),
    fx: nothing, resetCheckpoint: nothing, move: nothing, jump: nothing, drop: nothing};
  let tick = 0;
  for (; tick < 2800 && awards.length < target; tick++) {
    game.rules.update(state, level, drive(state, tick), 1 / 60, fb);
  }
  return {awards, misses, state, tick};
}

test('sorting uses the sign, carry and borrow conditions with real shared movement', () => {
  const game = load('sortingDepot', 'send-cards');
  game.config.levels.forEach((level, i) => {
    const category = (token) => {
      const [sign, first, second] = token.split('-');
      assert.equal(sign, i === 1 ? 'add' : i === 2 ? 'sub' : sign);
      if (i === 0) return sign === 'add' ? 'plus' : 'minus';
      if (i === 1) return Number(first) % 10 + Number(second) >= 10 ? 'carry' : 'keep-add';
      return Number(first) % 10 < Number(second) ? 'borrow' : 'keep-sub';
    };
    for (const item of level.items) assert.equal(item.group, category(item.token));
    for (const dock of level.docks) assert.equal(dock.group, dock.sample);
  });
  const first = game.config.levels[0];
  const wrongRoute = ['up', 'right', 'right', 'down', 'down', 'left', 'left',
    'up', 'up', 'right', 'down', 'left', 'down', 'right', 'right'];
  const wrong = play(game, first, (_w, tick) => game.input(
    ...(tick % 24 === 0 ? wrongRoute.slice(tick / 24, tick / 24 + 1) : [])
  ));
  assert.equal(wrong.awards.length, 0);
  assert(wrong.misses.length > 0);
  const demo = play(game, first, world => game.rules.pilot(world, first), 1);
  const dock = game.followers.get('#first-operation-dock')({level: 0});
  assert.deepEqual(demo.awards[0], [dock.x + dock.w / 2, dock.y + dock.h / 2]);
  assert(demo.tick / 60 < 30);
  for (let round = 0; round < 2; round++) {
    for (const level of game.config.levels) {
      const result = play(game, level, world => game.rules.pilot(world, level));
      assert.equal(result.awards.length, game.rules.goal(level));
      assert.equal(result.misses.length, 0);
    }
  }
});

test('marbles require exact quantities and update the problem after each matching shot', () => {
  const game = load('magnetMarbles', 'match-picture-result');
  const answer = new Map([['more-tens', 38 + 20], ['more-ones', 38 + 1], ['carry-first', 27 + 9],
    ['carry-next', 56 + 8], ['borrow-first', 61 - 8], ['borrow-next', 74 - 6]]);
  for (const level of game.config.levels) {
    assert.deepEqual(plain(level.pairs), Array.from(level.queue, key => [key, answer.get(key)]));
    for (const [key, result] of level.pairs) {
      assert.equal(level.targets.filter(target => target.value === answer.get(key)).length, 1);
      assert.equal(game.config.art.icons[result], '__IMG:value-' + result + '__');
    }
  }
  const first = game.config.levels[0];
  const wrong = play(game, first, (_w, tick) => game.input(...(tick === 0 ? ['action'] : [])));
  assert.equal(wrong.awards.length, 0);
  assert.equal(wrong.misses.length, 1);
  const demo = play(game, first, world => game.rules.pilot(world, first), 1);
  assert.equal(demo.state.locked.value, 58);
  assert(demo.tick / 60 < 30);
  assert.equal(game.rules.reset(first).locked, null);
  for (let round = 0; round < 2; round++) {
    for (const level of game.config.levels) {
      const result = play(game, level, world => game.rules.pilot(world, level));
      assert.equal(result.awards.length, game.rules.goal(level));
      assert.equal(result.misses.length, 0);
      assert.equal(result.state.locked.value, level.pairs.at(-1)[1]);
    }
  }
});
