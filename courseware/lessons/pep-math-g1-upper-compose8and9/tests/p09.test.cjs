const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const source = path.resolve(__dirname, '..');
const fromStudentWeb = createRequire(path.resolve(source, '../../../student-web/package.json'));
const {JSDOM} = fromStudentWeb('jsdom');

function page(id = 'p09') {
  const html = '<div id="star-n">0</div>' + fs.readFileSync(path.join(source, `pages/${id}.html`), 'utf8');
  const dom = new JSDOM(html, {runScripts: 'outside-only'});
  const w = dom.window, d = w.document, timers = [];
  w.setTimeout = fn => {timers.push(fn); return timers.length;};
  w.clearTimeout = () => {};
  w.K = {
    $: s => d.querySelector(s),
    el(tag, cls, html, parent) {
      const el = d.createElement(tag); el.className = cls;
      if (html != null) el.innerHTML = html;
      if (parent) parent.appendChild(el);
      return el;
    },
    hud() {}, owl() {}, ready() {}, levels() {}, say(text) {w.lastSay = text;}, highlight() {}, stars: 0,
    star(n) {this.stars += n;},
    finish(options) {w.finished = options;},
    shuffle: array => array,
    drag(el, options) {el.click = () => options.onTap();},
    sfx: {no() {}, ok() {}, drop() {}, pick() {}},
  };
  w.eval(fs.readFileSync(path.join(source, `pages/${id}.js`), 'utf8'));
  return {w, d, timers, close: () => w.close()};
}

function assertWholeToParts(d) {
  const nodes = [...d.querySelectorAll('#relation .node')];
  const lines = [...d.querySelectorAll('#relation line')];
  assert.equal(nodes.length, 3);
  assert.equal(lines.length, 2, 'one whole connects directly to each of the two parts');
  const whole = nodes[0];
  const center = node => [parseInt(node.style.left) + 75, parseInt(node.style.top) + 64];
  const wholePoint = center(whole);
  lines.forEach((line, i) => {
    assert.deepEqual([+line.getAttribute('x1'), +line.getAttribute('y1')], wholePoint);
    assert.deepEqual([+line.getAttribute('x2'), +line.getAttribute('y2')], center(nodes[i + 1]));
  });
}

test('every orientation keeps exactly two whole-to-part edges and resets', () => {
  const p = page();
  try {
    p.w.K.onStart();
    // Correct quantities derived independently from the displayed task order.
    for (const answer of [7, 9, 5, 4]) {
      assertWholeToParts(p.d);
      const cards = [...p.d.querySelectorAll('.quantity-card')];
      const card = cards.find(c => c.querySelectorAll('.quantity i').length === answer);
      assert.ok(card, 'correct quantity is available');
      card.click();
      assert.equal(p.d.querySelector('#missing-slot').textContent, String(answer));
      p.timers.shift()();
    }
    assert.ok(p.w.finished);
    p.w.finished.again();
    assertWholeToParts(p.d);
    assert.equal(p.d.querySelector('#missing-slot').textContent, '?');
    assert.equal(p.d.querySelector('#missing-slot').classList.contains('solved'), false);
  } finally {p.close();}
});

test('teacher demonstration uses the same two-edge relation without accepting child input', () => {
  const p = page();
  try {
    p.w.K.onState({demo: true});
    assertWholeToParts(p.d);
    p.d.querySelector('.quantity-card').click();
    assert.equal(p.d.querySelector('#missing-slot').textContent, '?');
  } finally {p.close();}
});

test('ordered splits reject skipped rows, record all seven ways and replay from one/seven', () => {
  const p = page('p02');
  try {
    p.w.K.onStart();
    p.d.querySelector('#move-one').click();
    p.d.querySelector('#save-way').click();
    assert.equal(p.d.querySelectorAll('.record.done').length, 0);
    assert.equal(p.w.K.stars, 0);
    p.d.querySelector('#move-back').click();
    for (let left = 1; left <= 7; left++) {
      assert.equal(p.d.querySelector('#left-count').textContent, String(left));
      assert.equal(p.d.querySelector('#right-count').textContent, String(8 - left));
      assert.equal(p.d.querySelectorAll('#strip .unit').length, 8);
      p.d.querySelector('#save-way').click();
      if (left < 7) p.d.querySelector('#move-one').click();
    }
    assert.equal(p.d.querySelectorAll('.record.done').length, 7);
    p.timers.shift()();
    assert.ok(p.w.finished);
    p.w.finished.again();
    assert.equal(p.d.querySelector('#left-count').textContent, '1');
    assert.equal(p.d.querySelectorAll('.record.done').length, 0);
    assert.equal(p.w.K.stars, 0);
  } finally {p.close();}
});

test('exchange preserves both parts, including the equal-part case, and replays', () => {
  const p = page('p04');
  try {
    p.w.K.onStart();
    const quantities = selector => [...p.d.querySelectorAll(selector + ' .quantity')].map(g => g.querySelectorAll('i').length);
    const expected = [[6, 2], [5, 4], [4, 4], [6, 3]];
    const wrong = [...p.d.querySelectorAll('.pair-option')].find(b => quantities('#' + b.id).join() !== expected[0].join());
    wrong.click();
    assert.equal(p.w.K.stars, 0);
    assert.equal(p.d.querySelectorAll('#source-pair .bead').length, 8);
    for (const pair of expected) {
      const card = [...p.d.querySelectorAll('.pair-option')].find(b => quantities('#' + b.id).join() === pair.join());
      assert.ok(card);
      card.click();
      assert.deepEqual([...p.d.querySelectorAll('#source-pair .part')].map(g => g.querySelectorAll('.bead').length), pair);
      p.timers.shift()();
    }
    assert.ok(p.w.finished);
    assert.equal(p.w.K.stars, 4);
    p.w.finished.again();
    assert.equal(p.w.K.stars, 0);
    assert.equal(p.d.querySelector('#whole-total').textContent, '8');
  } finally {p.close();}
});

test('one extra item changes only the chosen part; mistaken placement can be undone and replay resets', () => {
  const p = page('p07');
  try {
    p.w.K.onStart();
    p.d.querySelector('#tray-right').click();
    p.d.querySelector('#check-extra').click();
    assert.equal(p.w.K.stars, 0);
    p.d.querySelector('#reset-extra').click();
    assert.equal(p.d.querySelector('#whole-total').textContent, '8');
    const expected = [[0, 4, 5], [1, 6, 3], [0, 2, 7]];
    for (const [side, a, b] of expected) {
      p.d.querySelector(side ? '#tray-right' : '#tray-left').click();
      assert.equal(p.d.querySelector('#whole-total').textContent, '9');
      assert.equal(p.d.querySelectorAll('#tray-left .bead').length, a);
      assert.equal(p.d.querySelectorAll('#tray-right .bead').length, b);
      assert.equal(p.d.querySelectorAll('#tray-left .bead,#tray-right .bead').length, 9);
      p.d.querySelector('#check-extra').click();
      p.timers.shift()();
    }
    assert.ok(p.w.finished);
    p.w.finished.again();
    assert.equal(p.d.querySelector('#whole-total').textContent, '8');
    assert.equal(p.d.querySelector('#extra-bead').classList.contains('placed'), false);
    assert.equal(p.w.K.stars, 0);
  } finally {p.close();}
});

test('add-one teacher demonstration updates its footer instead of retaining the child task goal', () => {
  const p = page('p07');
  try {
    p.w.K.onStart();
    assert.match(p.w.lastSay, /左边要有4片/);
    p.w.K.onState({demo: true});
    assert.match(p.d.querySelector('#goal-part').textContent, /3/);
    assert.match(p.w.lastSay, /左边两片、右边六片/);
    p.w.K.onState({demoPlaced: true});
    assert.match(p.w.lastSay, /左边变成三片，右边仍是六片/);
    p.w.K.onState({play: true});
    assert.match(p.w.lastSay, /左边要有4片/);
  } finally {p.close();}
});

test('missing-whole teaching example keeps the total below both visible parts and explains nine', () => {
  const p = page();
  try {
    p.w.K.onState({demoWhole: true});
    assertWholeToParts(p.d);
    assert.equal(p.d.querySelector('#missing-slot').classList.contains('whole-node'), true);
    assert.equal(p.d.querySelectorAll('#node-a .bead').length, 3);
    assert.equal(p.d.querySelectorAll('#node-b .bead').length, 6);
    assert.ok(parseInt(p.d.querySelector('#missing-slot').style.top) > parseInt(p.d.querySelector('#node-a').style.top));
    p.w.K.onState({demoWholeSolved: true});
    assert.equal(p.d.querySelector('#missing-slot').textContent, '9');
    assert.match(p.w.lastSay, /三和六组成九/);
    p.w.K.onState({play: true});
    assert.equal(p.d.querySelector('#missing-slot').classList.contains('whole-node'), false);
    assert.equal(p.d.querySelector('#missing-slot').textContent, '?');
  } finally {p.close();}
});

test('teacher result states reconstruct the correct example even when replay starts at that action', () => {
  const addition = page('p07'), whole = page();
  try {
    addition.w.K.onState({demoPlaced: true});
    assert.equal(addition.d.querySelectorAll('#tray-left .bead').length, 3);
    assert.equal(addition.d.querySelectorAll('#tray-right .bead').length, 6);
    whole.w.K.onState({demoWholeSolved: true});
    assertWholeToParts(whole.d);
    assert.equal(whole.d.querySelector('#missing-slot').classList.contains('whole-node'), true);
    assert.equal(whole.d.querySelector('#missing-slot').textContent, '9');
  } finally {addition.close();whole.close();}
});

test('ordered teacher states visibly transfer one item while preserving eight before restoring the missing part', () => {
  const p = page();
  try {
    for (const [state, a, b] of [['demoOrderStart', 1, 7], ['demoOrderNext', 2, 6]]) {
      p.w.K.onState({[state]: true});
      assertWholeToParts(p.d);
      assert.equal(p.d.querySelectorAll('#node-a .bead').length, a);
      assert.equal(p.d.querySelectorAll('#node-b .bead').length, b);
      assert.equal(p.d.querySelectorAll('#relation .bead').length, 8);
      assert.equal(p.d.querySelector('#node-whole').textContent, '8');
      assert.equal(p.d.querySelector('#missing-slot'), null);
      assert.equal(p.d.querySelectorAll('.quantity-card').length, 0);
    }
    p.w.K.onState({demo: true});
    assert.equal(p.d.querySelector('#missing-slot').textContent, '?');
    assert.equal(p.d.querySelectorAll('#node-a .bead').length, 2);
    assert.equal(p.d.querySelectorAll('.quantity-card').length, 3);
  } finally {p.close();}
});

test('teacher demonstration resets prior child feedback and progress instead of displaying an old success message', () => {
  for (const [key, state, footer] of [['p02', {demoLeft: 2}, /示范：左边2片，右边6片/], ['p04', {demo: true}, /示范：原来左边三片、右边五片/], ['p09', {demo: true}, /示范：整体八，一个部分两片/]]) {
    const p = page(key);
    try {
      p.w.K.onStart();
      if (key === 'p02') p.d.querySelector('#save-way').click();
      p.w.K.stars = 3;
      p.w.lastSay = '旧的成功提示';
      p.w.K.onState(state);
      assert.match(p.w.lastSay, footer);
      assert.equal(p.w.K.stars, 0);
      if (key === 'p02') assert.equal(p.d.querySelectorAll('#records .done').length, 0);
    } finally {p.close();}
  }
});

test('all teacher entry states clear child reward animations and stars during replay', () => {
  for (const [key, states] of [['p02', [{demoLeft: 2}]], ['p04', [{demo: true}]], ['p07', [{demo: true}, {demoPlaced: true}]], ['p09', [{demo: true}, {demoOrderStart: true}, {demoOrderNext: true}, {demoWhole: true}, {demoWholeSolved: true}]]]) {
    const p = page(key);
    try {
      for (const state of states) {
        p.w.K.stars = 2;
        p.d.querySelector('#star-n').textContent = '2';
        for (const cls of ['flystar', 'cf']) {
          const el = p.d.createElement('div'); el.className = cls; p.d.body.appendChild(el);
        }
        p.w.K.onState(state);
        assert.equal(p.w.K.stars, 0);
        assert.equal(p.d.querySelector('#star-n').textContent, '0');
        assert.equal(p.d.querySelector('.flystar,.cf'), null);
      }
    } finally {p.close();}
  }
});
