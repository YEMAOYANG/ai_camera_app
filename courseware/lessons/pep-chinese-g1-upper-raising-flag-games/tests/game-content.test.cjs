const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const read = rel => fs.readFileSync(path.join(root, rel), 'utf8');

function template(page, name) {
  let config;
  vm.runInNewContext(read(`pages/${page}.js`), {
    K: {ready() {}, game(spec) { config = spec; }, gameTemplates: {[name]: spec => spec}}
  });
  return config;
}

test('the crane carries an outer frame only to fully enclosed characters', () => {
  const config = template('frame-crane', 'crane');
  const enclosed = new Set(['国', '回']);
  assert.deepEqual(Array.from(config.levels, level => level.rounds.length), [1, 2, 2]);
  for (const level of config.levels) {
    for (const round of [...level.rounds, ...(level.demoRounds || [])]) {
      const expected = Array.from(round.cars, (char, index) => enclosed.has(char) ? index : null)
        .filter(index => index !== null);
      assert.deepEqual(Array.from(round.drop), expected);
      assert.equal(round.cargo, '囗');
    }
  }
});

test('the writing game routes are identical to the five teaching diagrams', () => {
  const config = template('stroke-route', 'trace');
  const expected = {
    中: ['center-grid', 4], 五: ['five-grid', 4], 风: ['wind-grid', 4],
    立: ['upright-grid', 5], 正: ['correct-grid', 5]
  };
  for (const round of config.levels.flatMap(level => level.rounds)) {
    const [diagram, count] = expected[round.goal];
    const svg = read(`diagrams/${diagram}.svg`);
    assert.equal(round.strokes.length, count);
    assert.deepEqual(Array.from(round.gridBox), [640, 450, 396]);
    for (const stroke of round.strokes) {
      assert.ok(svg.includes(`points="${stroke.map(point => point.join(',')).join(' ')}"`));
      for (const [x, y] of stroke) {
        assert.ok(x > 442 && x < 838 && y > 252 && y < 648);
      }
    }
    if (round.goal === '风') {
      const hook = round.strokes[1];
      assert.ok(hook[1][0] > hook[0][0] && hook.at(-2)[1] > hook[1][1]);
      assert.ok(hook.at(-1)[1] < hook.at(-2)[1]);
      assert.ok(read('diagrams/stroke-up-hook.svg').includes(hook.map(p => p.join(',')).join(' ')));
    }
  }
});

test('the flag drawing includes one large five-point star and four inward-facing small stars', () => {
  const svg = read('diagrams/flag-close.svg');
  const polygons = [...svg.matchAll(/<polygon points="([^"]+)" fill="#FFFF00"/g)];
  const flagScale = 20;
  const centers = [[5, 5], [10, 2], [12, 4], [12, 7], [10, 9]];
  assert.ok(svg.includes('viewBox="0 0 600 400"'));
  assert.equal(polygons.length, centers.length);
  for (let i = 0; i < centers.length; i++) {
    const [cx, cy] = centers[i];
    const polygon = polygons[i][1].split(' ').map(point => point.split(',').map(Number));
    assert.equal(polygon.length, 10);
    const radius = Math.hypot(polygon[0][0] / flagScale - cx, polygon[0][1] / flagScale - cy);
    assert.ok(Math.abs(radius - (i === 0 ? 3 : 1)) < 0.001);
    const desired = i === 0 ? -Math.PI / 2 : Math.atan2(5 - cy, 5 - cx);
    const actual = Math.atan2(polygon[0][1] / flagScale - cy, polygon[0][0] / flagScale - cx);
    assert.ok(Math.abs(desired - actual) < 0.001);
  }
});

function camera() {
  let config;
  const clicks = {};
  const controls = Object.fromEntries(['#camera-shutter', '#camera-restart'].map(id => [id, {
    addEventListener(name, action) {
      assert.equal(name, 'click');
      clicks[id] = action;
    }
  }]));
  const context = new Proxy({}, {get(object, key) { return object[key] ?? (() => {}); }});
  const sandbox = {
    K: {ready() {}, game(spec) { config = spec; }, $: id => controls[id],
      sfx: {ok() {}}, draw: {rr() {}, circle() {}}},
    Image: class { complete = true; naturalWidth = 1280; naturalHeight = 720; },
    document: {createElement() { return {getContext: () => context}; }}
  };
  const world = vm.createContext(sandbox);
  vm.runInContext(read('pages/ceremony-camera.js'), world);
  const script = vm.runInContext('({currentShot, flagMotion, focus})', world);
  const messages = [];
  const game = {level: 0, taps: [], keys: {}, pointer: {}, data: {}, after(_time, action) { action(); },
    win() { this.won = true; }, say(text, kind) { messages.push({text, kind}); }, follow() {},
    start(level) { this.level = level; config.reset(this); }};
  config.setup(game);
  config.reset(game);
  function step(seconds = 1 / 60) {
    config.update(game, seconds);
    game.taps.length = 0;
  }
  function aim(x, y) {
    game.taps.push({x, y});
    Object.assign(game.pointer, {x, y, down: true});
    for (let i = 0; i < 100; i++) step();
    game.pointer.down = false;
    step();
  }
  return {game, config, script, click: clicks['#camera-shutter'], restart: clicks['#camera-restart'], step, aim, messages};
}

test('a press without framing or the target moment earns no photo and costs no attempt', () => {
  const c = camera();
  c.click();
  c.step();
  assert.equal(c.game.data.photos.length, 0);
  assert.equal(c.messages.at(-1).kind, 'no');
  assert.equal(c.messages.at(-1).text, '先让旗进取景框。');

  c.aim(262, 396);
  c.click();
  c.step();
  assert.equal(c.game.data.photos.length, 1);
  assert.equal(c.script.currentShot(c.game), 'high');

  c.aim(262, 258);
  c.click();
  c.step();
  assert.equal(c.game.data.photos.length, 1);
  assert.equal(c.messages.at(-1).text, '再看旗的位置。');

  for (let i = 0; i < 170; i++) c.step();
  c.click();
  c.step();
  assert.equal(c.game.data.photos.length, 2);
  assert.ok(c.game.won);
  assert.equal(c.script.flagMotion(c.game).y, 168);
});

test('camera autopilot finishes all levels using the same input loop, retaining its snapshots', () => {
  const c = camera();
  for (let level = 0; level < c.config.levels; level++) {
    c.game.won = false;
    c.game.level = level;
    c.config.reset(c.game);
    const modes = new Set();
    for (let i = 0; i < 1600 && !c.game.won; i++) {
      modes.add(c.script.currentShot(c.game));
      c.config.autopilot(c.game);
      c.step();
    }
    assert.ok(c.game.won, `level ${level + 1} should finish`);
    assert.deepEqual([...modes], [['low', 'high'], ['curl', 'lift'], ['high', 'lift', 'people']][level]);
    assert.equal(c.game.data.photos.length, level === 2 ? 3 : 2);
    assert.ok(c.game.data.photos.every(picture => picture.width === 384 && picture.height === 258));
    c.restart();
    assert.equal(c.game.level, level);
    assert.equal(c.game.data.photos.length, 0);
    assert.equal(c.game.data.hinted.size, 0);
  }
});
