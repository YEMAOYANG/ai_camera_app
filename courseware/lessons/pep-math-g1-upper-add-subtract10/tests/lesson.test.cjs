const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const {JSDOM} = require(require.resolve('jsdom', {paths: [path.resolve(__dirname, '../../../../student-web')]}));

function startPage(id) {
  const base = path.resolve(__dirname, '../pages');
  const html = fs.readFileSync(path.join(base, id + '.html'), 'utf8');
  const dom = new JSDOM('<div id="star-n">0</div>' + html, {runScripts:'outside-only'});
  const {document} = dom.window;
  const K = {
    $(selector) { return document.querySelector(selector); },
    el(tag, className, content, parent) {
      const node = document.createElement(tag);
      node.className = className;
      node.textContent = content;
      parent.append(node);
      return node;
    },
    hud() {}, owl() {}, ready() {}, levels() {}, finish() {}, say() {},
    star(n) { this.stars += n; },
    stars:0,
    shuffle(items) { return items; },
    sfx:{no() {},ok() {},tick() {}},
  };
  dom.window.K = K;
  dom.window.eval(fs.readFileSync(path.join(base, id + '.js'), 'utf8'));
  K.onStart();
  return {K, document, close:() => dom.window.close()};
}

test('joining adds the selected whole group once and accepts a replay reset', () => {
  const {K, document, close} = startPage('p02');
  try {
    document.querySelector('[aria-label="8片灯片"]').click();
    assert.equal(document.querySelectorAll('#join-board .lamp').length, 1);
    assert.equal(K.stars, 0);
    document.querySelector('[aria-label="9片灯片"]').click();
    assert.equal(document.querySelectorAll('#join-board .lamp').length, 10);
    assert.equal(K.stars, 1);
    K.onState({demoSwapped:true});
    assert.equal(document.querySelector('#join-equation').textContent, '8 + 2 = 10');
    assert.equal(document.querySelectorAll('#join-board .lamp.blue').length, 2);
    assert.equal(document.querySelectorAll('#join-board .lamp.green').length, 8);
    K.onState({play:true});
    assert.equal(document.querySelectorAll('#join-board .lamp').length, 1);
  } finally { close(); }
});

test('subtraction starts with all ten and preserves the identity of moved and kept groups', () => {
  const {K, document, close} = startPage('p04');
  try {
    document.querySelector('#take-second').click();
    assert.equal(document.querySelectorAll('#whole-box .lamp').length, 10);
    document.querySelector('#take-first').click();
    assert.equal(document.querySelectorAll('#removed-tray .lamp.blue').length, 1);
    assert.equal(document.querySelectorAll('#whole-box .lamp.green').length, 9);
    assert.equal(document.querySelector('#take-equation').textContent, '10 − 1 = 9');
    K.onState({demoSecond:true});
    assert.equal(document.querySelectorAll('#removed-tray .lamp.green').length, 6);
    assert.equal(document.querySelectorAll('#whole-box .lamp.blue').length, 4);
  } finally { close(); }
});

test('a choice of action has an observable effect on the ten grid', () => {
  const {K, document, close} = startPage('p06');
  try {
    document.querySelector('[aria-label="从十片里拿走2片"]').click();
    assert.equal(document.querySelectorAll('#map-board .lamp').length, 0);
    document.querySelector('[aria-label="把2片和8片合起来"]').click();
    assert.equal(document.querySelectorAll('#map-board .lamp').length, 10);
    K.onState({demoOther:true});
    assert.equal(document.querySelector('#map-equation').textContent, '10 − 6 = 4');
    assert.equal(document.querySelectorAll('#map-board .lamp').length, 4);
  } finally { close(); }
});

test('an unknown removal compares the resulting count and can leave zero', () => {
  const {K, document, close} = startPage('p08');
  try {
    document.querySelector('[aria-label="拿走2片"]').click();
    assert.equal(K.stars, 0);
    assert.equal(document.querySelectorAll('#remain-board .lamp').length, 8);
    document.querySelector('[aria-label="拿走3片"]').click();
    assert.equal(document.querySelectorAll('#remain-board .lamp').length, 7);
    assert.equal(document.querySelector('#missing-equation').textContent, '10 − 3 = 7');
    K.onState({demoAll:true});
    assert.equal(document.querySelectorAll('#remain-board .lamp').length, 0);
    assert.equal(document.querySelector('#missing-equation').textContent, '10 − 10 = 0');
    K.onState({play:true});
    assert.equal(document.querySelectorAll('#remain-board .lamp').length, 10);
  } finally { close(); }
});
