const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../pages/p03.js'), 'utf8');

function classroom(goal) {
  function element(dataset = {}) {
    const classes = new Set();
    return { dataset, style: {}, hidden: true, textContent: '', classList: {
      add(...names) { names.forEach(name => classes.add(name)); },
      remove(...names) { names.forEach(name => classes.delete(name)); },
      toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
      contains(name) { return classes.has(name); }
    }};
  }
  const elements = Object.fromEntries(['bird-lab', 'bird-token', 'hat-shell', 'star-n', 'picture-error'].map(id => [id, element()]));
  elements['bird-lab'].dataset.goal = goal;
  const landings = ['in', 'on', 'under'].map(relation => element({relation}));
  const pictures = [element(), element(), element()];
  const timers = new Map();
  let timerId = 0;
  const messages = [], highlights = [];
  const K = {
    stars: 0,
    $(selector) { return elements[selector.slice(1)]; },
    $$(selector) { return selector === '.landing' ? landings : pictures; },
    hud() {}, owl() {}, ready() {}, levels() {},
    say(text) { messages.push(text); }, highlight(target) { highlights.push(target); },
    star(count) { K.stars += count; },
    sfx: {no() {}, ok() {}, pick() {}},
    drag(bird, options) { K.dragOptions = options; },
    finish(options) { K.finishOptions = options; }
  };
  const window = {};
  vm.runInNewContext(source, {K, window, setTimeout(callback) { const id = ++timerId; timers.set(id, callback); return id; }, clearTimeout(id) { timers.delete(id); }});
  return {K, window, elements, landings, pictures, messages, highlights,
    tick() { const pending = [...timers.values()]; timers.clear(); pending.forEach(callback => callback()); }};
}

for (const goal of ['in', 'on', 'under']) {
  test(`${goal}: teacher demonstration is not student evidence`, () => {
    const c = classroom(goal), lesson = c.window.lessonPosition;
    c.K.onStart();
    c.K.onState({demo: goal});
    lesson.attempt(goal);
    assert.equal(lesson.state().stars, 0);
    assert.equal(lesson.state().playing, false);
    assert.equal(c.K.dragOptions.enabled(), false);
    c.K.onState({play: true});
    assert.equal(lesson.state().relation, 'start');
    assert.equal(c.K.dragOptions.enabled(), true);
  });

  test(`${goal}: first error gives no answer and retry changes the bird`, () => {
    const c = classroom(goal), lesson = c.window.lessonPosition;
    const wrong = ['in', 'on', 'under'].find(value => value !== goal);
    c.K.onState({play: true});
    lesson.attempt(wrong);
    assert.equal(lesson.state().relation, wrong);
    assert.equal(lesson.state().stars, 0);
    assert.equal(lesson.state().misses, 1);
    assert.equal(c.messages.at(-1), '再看看小鸟与帽子的位置。');
    assert.deepEqual(c.highlights, []);
    lesson.attempt(goal);
    assert.equal(lesson.state().relation, goal);
    assert.equal(lesson.state().stars, 1);
    c.tick();
    assert.ok(c.K.finishOptions);
    c.K.finishOptions.again();
    assert.equal(lesson.state().relation, 'start');
    assert.equal(lesson.state().stars, 0);
    assert.equal(lesson.state().misses, 0);
    assert.equal(lesson.state().playing, true);
  });

  test(`${goal}: third hint demonstrates without a score and resets`, () => {
    const c = classroom(goal), lesson = c.window.lessonPosition;
    const wrong = ['in', 'on', 'under'].find(value => value !== goal);
    c.K.onState({play: true});
    lesson.attempt(wrong); lesson.attempt(wrong); lesson.attempt(wrong);
    assert.equal(lesson.state().busy, true);
    c.tick();
    assert.equal(lesson.state().relation, goal);
    assert.equal(lesson.state().stars, 0);
    c.tick();
    assert.equal(lesson.state().relation, 'start');
    assert.equal(lesson.state().stars, 0);
    assert.equal(lesson.state().busy, false);
  });
}

test('a failed formal picture locks the game and shows a recovery state', () => {
  const c = classroom('in');
  c.K.onState({play: true});
  c.pictures[0].onerror();
  assert.equal(c.window.lessonPosition.state().playing, false);
  assert.equal(c.elements['picture-error'].hidden, false);
  assert.equal(c.elements['bird-lab'].classList.contains('locked'), true);
});
