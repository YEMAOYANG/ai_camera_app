const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const test = require('node:test');
const {runInNewContext} = require('node:vm');

const root = join(__dirname, '..');
const kit = join(root, '..', '..', 'kit', 'game_templates');
const lesson = JSON.parse(readFileSync(join(root, 'lesson.json'), 'utf8'));
const bot = (...keys) => ({held: key => keys.includes(key), press: key => keys.includes(key)});

function game(page, template) {
  let result;
  const K = {gameTemplates: {}, ready() {}, game(value) { result = value; }};
  const Classic = {
    create: (config, logic) => ({config, logic}), bot,
    ease: (_value, target) => target,
    clamp: (value, min, max) => Math.max(min, Math.min(max, value)),
    center: (x, y, w, h) => ({x, y, w, h}),
    validToken: value => /^[a-z0-9-]+$/.test(value),
  };
  const context = {K, Classic};
  runInNewContext(readFileSync(join(kit, template + '.js'), 'utf8'), context);
  runInNewContext(readFileSync(join(root, 'pages', page + '.js'), 'utf8'), context);
  result.config.levels.forEach(result.logic.validate);
  return result;
}

function feedback(onAward = () => {}) {
  const events = {awards: 0, misses: 0, observations: []};
  const fb = {
    move() {}, fx() {}, drop() {},
    lost() { events.misses++; },
    award() { events.awards++; onAward(); },
    observe(trial, views) { events.observations.push({trial, ...views}); },
  };
  return {events, fb};
}

test('camera feedback clears the requested-angle card and its shutter controls', () => {
  const {bubbleAt, logic} = game('photograph-neat-storage', 'shutterScout');
  const goal = logic.goalAnchor();
  const bubble = bubbleAt();
  assert.equal(bubble.x, goal.x);
  assert.ok(bubble.y - 34 - 2 >= 0);
  assert.ok(bubble.y + 52 < goal.y - goal.h / 2);
  assert.ok(bubble.y + 52 < 609);
});

test('wrong item and wrong pocket both leave order incomplete', () => {
  const {config, logic} = game('carry-to-the-pocket', 'listenDelivery');
  const first = config.levels[0], world = logic.reset(first);
  const {events, fb} = feedback();
  logic.update(world, first, bot('right'), .016, fb);
  logic.update(world, first, bot('action'), .35, fb);
  assert.equal(world.col, 5);
  assert.equal(world.goods.get('eraser'), world.col);
  assert.equal(events.misses, 1);
  assert.equal(events.awards, 0);
  assert.equal(world.carried, null);
  assert.equal(world.order, 0);

  logic.update(world, first, bot('left'), .35, fb);
  logic.update(world, first, bot('action'), .35, fb);
  assert.equal(world.carried, 'album');
  assert.equal(events.awards, 1);
  assert.equal(world.delivered.size, 0);
  for (let frames = 0; frames < 4000 && world.row !== 0; frames++)
    logic.update(world, first, logic.pilot(world, first, .016), .016, fb);
  assert.equal(world.row, 0);
  for (let moves = 0; moves < 7 && world.col < 6; moves++)
    logic.update(world, first, bot('right'), .35, fb);
  logic.update(world, first, bot('action'), .35, fb);
  assert.equal(world.col, world.recipients.get('zip-pocket'));
  assert.equal(events.misses, 2);
  assert.equal(events.awards, 1);
  assert.equal(world.carried, 'album');
  assert.equal(world.delivered.size, 0);
  assert.equal(world.order, 0);
});

test('each actual pickup changes the target to its corresponding pocket, then delivers', () => {
  const {config, logic} = game('carry-to-the-pocket', 'listenDelivery');
  const expectations = [
    [['album', 'main-pocket']],
    [['bottle', 'side-pocket'], ['tape', 'zip-pocket']],
    [['foldmap', 'main-pocket'], ['tape', 'zip-pocket'], ['bottle', 'side-pocket']],
  ];
  for (const [i, level] of config.levels.entries()) {
    const world = logic.reset(level), reached = [];
    const {events, fb} = feedback(() => {
      const [good, pocket] = expectations[i][Math.floor(reached.length / 2)];
      if (reached.length % 2 === 0) {
        assert.equal(world.carried, good);
        assert.equal(logic.target(world, level).x, 253 + (world.recipients.get(pocket) + .5) * 86);
        reached.push([good, 'pickup']);
      } else {
        assert.equal(world.carried, null);
        assert.equal(world.delivered.get(pocket), good);
        reached.push([pocket, 'delivery']);
      }
    });
    for (let frames = 0; frames < 8000 && events.awards < logic.goal(level); frames++)
      logic.update(world, level, logic.pilot(world, level, .016), .016, fb);
    assert.deepEqual(reached, expectations[i].flatMap(([good, pocket]) => [[good, 'pickup'], [pocket, 'delivery']]));
    assert.equal(world.order, expectations[i].length);
  }
});

test('teacher delivery demonstration takes the album as its first action', () => {
  const {config, logic} = game('carry-to-the-pocket', 'listenDelivery');
  const first = config.levels[0], world = logic.reset(first);
  const {events, fb} = feedback();
  assert.equal(logic.player(world).x, 640);
  assert.equal(logic.target(world, first).y, 536);
  logic.update(world, first, logic.pilot(world, first, .016), .016, fb);
  assert.equal(events.awards, 1);
  assert.equal(world.carried, 'album');
  assert.equal(world.delivered.size, 0);
  assert.equal(logic.target(world, first).x, 554);
  assert.equal(logic.target(world, first).y, 192);
});

test('wrong photo is rejected and each round emits only its completed pair', () => {
  const {config, logic} = game('photograph-neat-storage', 'shutterScout');
  const scene = lesson.scenes.find(scene => scene.key === 'photograph-neat-storage');
  const images = {icons: new Map(Object.keys(config.art.icons).map(id => [id, {complete: true, naturalWidth: 100}]))};
  const first = config.levels[0], start = logic.reset(first), wrong = feedback();
  logic.update(start, first, bot(), 1.45, wrong.fb, images);
  logic.update(start, first, bot('action'), .016, wrong.fb, images);
  assert.equal(wrong.events.misses, 1);
  assert.equal(wrong.events.awards, 0);
  assert.equal(start.photos.length, 0);
  assert.equal(wrong.events.observations.length, 0);

  for (const [i, level] of config.levels.entries()) {
    const world = logic.reset(level), {events, fb} = feedback();
    for (let frames = 0; frames < 8000 && events.awards < logic.goal(level); frames++) {
      logic.update(world, level, logic.pilot(world, level), .016, fb, images);
      if (events.awards < logic.goal(level)) assert.equal(events.observations.length, 0);
    }
    assert.equal(events.awards, logic.goal(level));
    assert.equal(events.misses, 0);
    assert.equal(events.observations.length, 1);
    assert.deepEqual(Array.from(world.photos, photo => photo.state), Array.from(level.shots));
    const [capture] = events.observations, declared = scene.observationCard.levels[i].trials[0];
    assert.equal(capture.trial, 'same-storage-two-views');
    assert.equal(declared.id, capture.trial);
    for (const direction of ['top', 'side']) {
      assert.equal(capture[direction], level.photoViews[direction]);
      assert.equal(capture[direction], config.observation.trials[capture.trial][direction][i]);
      assert.deepEqual(Object.keys(declared[direction]), [capture[direction]]);
      assert.equal(declared[direction][capture[direction]].image, capture[direction]);
    }
    assert.equal(capture.top.replace('-top-', '-side-'), capture.side);
  }
});
