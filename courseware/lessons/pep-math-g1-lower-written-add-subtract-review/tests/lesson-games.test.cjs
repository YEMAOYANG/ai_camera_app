const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const lesson = path.resolve(__dirname, '..');
const templates = path.resolve(lesson, '../../kit/game_templates');
const dt = 1 / 60;

function load(page, template) {
  const follows = new Map();
  const picture = {
    src: '',
    getAttribute() { return this.src; },
    setAttribute(_, value) { this.src = value; },
  };
  const K = {
    gameTemplates: {},
    ready() {},
    $: () => picture,
    game(definition) {
      return Object.assign(definition, {follow: (target, update) => follows.set(target, update)});
    },
  };
  const Classic = {
    create(config, mechanic) {
      config.levels.forEach(mechanic.validate);
      return {config, mechanic};
    },
    bot: (...keys) => ({press: key => keys.includes(key), held: key => keys.includes(key)}),
    validToken: value => typeof value === 'string' && value.length > 0,
    match: (a, b, level) => level.pairs.some(([left, right]) => a === left && b === right),
    ease: (from, to) => to,
  };
  const context = vm.createContext({K, Classic});
  vm.runInContext(fs.readFileSync(path.join(templates, template + '.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(lesson, 'pages', page + '.js'), 'utf8'), context);
  const game = vm.runInContext(template === 'sortingDepot' ? 'sortGame' : 'repairGame', context);
  return {...game, picture, follows};
}

function play(mechanic, level, goal = mechanic.goal(level)) {
  const world = mechanic.reset(level);
  const awards = [];
  const feedback = {
    move() {}, fx() {}, drop() {}, resetCheckpoint() {},
    award(x, y) { awards.push({x, y}); },
    lost() { assert.fail('The pilot should complete a route without taking a wrong action'); },
  };
  for (let frame = 0; frame < 1800 && awards.length < goal; frame++) {
    mechanic.update(world, level, mechanic.pilot(world, level), dt, feedback);
  }
  assert.equal(awards.length, goal);
  return {world, awards};
}

test('the first legal delivery lands within the shown teaching anchor', () => {
  const {config, mechanic, follows} = load('sort-four-rules', 'sortingDepot');
  const anchor = follows.get('#first-written-dock')({level: 0});
  const {awards: [award]} = play(mechanic, config.levels[0], 1);
  assert.ok(award.x > anchor.x && award.x < anchor.x + anchor.w);
  assert.ok(award.y > anchor.y && award.y < anchor.y + anchor.h);
});

test('both lesson layouts complete all three stages twice through the approved rules', () => {
  for (const [page, template] of [['sort-four-rules', 'sortingDepot'], ['repair-pair', 'fallingTiles']]) {
    const {config, mechanic} = load(page, template);
    assert.equal(config.levels.length, 3);
    for (let replay = 0; replay < 2; replay++) {
      for (const level of config.levels) play(mechanic, level);
    }
  }
});

test('the original record stays paired to the demonstrated match and advances with the next falling tile', () => {
  const {config, mechanic, picture, follows} = load('repair-pair', 'fallingTiles');
  const level = config.levels[0];
  const follow = follows.get(picture);
  const {world} = play(mechanic, level, 1);
  follow({level: 0, data: {w: world}});
  assert.equal(picture.src, '__IMG:repair-copy-plus__');

  // A second tile appears after the success delay. A later miss has a longer delay
  // and must keep the second original visible during the wrong-answer flash.
  const next = {...world, delay: 0};
  follow({level: 0, data: {w: next}});
  assert.equal(picture.src, '__IMG:repair-copy-minus__');
  follow({level: 0, data: {w: {...next, delay: .12, flash: .05}}});
  assert.equal(picture.src, '__IMG:repair-copy-minus__');
});
