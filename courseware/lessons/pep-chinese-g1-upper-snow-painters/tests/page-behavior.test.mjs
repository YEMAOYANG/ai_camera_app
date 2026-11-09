import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import vm from 'node:vm';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..');
const {JSDOM} = createRequire(path.join(project, 'student-web/package.json'))('jsdom');
const pages = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../pages');

// These are page-state regressions, not layout, real canvas or G6 acceptance.
function classroom(name) {
  const dom = new JSDOM('<style>' + fs.readFileSync(path.join(pages, name + '.css'), 'utf8') + '</style><main id="play">' + fs.readFileSync(path.join(pages, name + '.html'), 'utf8')
    + '</main><b id="star-n">0</b>', {runScripts: 'outside-only'});
  const w = dom.window, d = w.document, timers = new Map();
  let serial = 0;
  w.setTimeout = fn => {timers.set(++serial, fn); return serial;};
  w.clearTimeout = id => timers.delete(id);
  const K = w.K = {
    $: selector => d.querySelector(selector), $$: selector => [...d.querySelectorAll(selector)],
    started: true, scale: 1, stars: 0, shuffle: a => a.slice().reverse(),
    hud() {}, owl() {}, ready() {}, say() {}, shake() {}, drag() {},
    levels: (total, done) => {K.level = [total, done];},
    star: count => {K.stars += count; d.querySelector('#star-n').textContent = String(K.stars);},
    finish: options => {K.finished = options;},
    el: (tag, cls, html, parent) => {
      const e = d.createElement(tag); e.className = cls || '';
      if (html) e.innerHTML = html;
      if (parent) parent.append(e);
      return e;
    },
    sfx: {pick() {}, no() {}, ok() {}, tick() {}},
  };
  if (name === 'trace') {
    // A synthetic mask isolates coverage/reset state. Real font/canvas remains a browser gate.
    w.HTMLCanvasElement.prototype.getContext = () => ({
      clearRect() {}, setLineDash() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fillText() {},
      getImageData() {
        const data = new Uint8ClampedArray(440 * 440 * 4);
        for (let i = 3; i < data.length; i += 4) data[i] = 255;
        return {data};
      },
    });
    d.querySelector('#trace-ink').getBoundingClientRect = () => ({left: 0, top: 0, width: 440, height: 440});
  }
  vm.runInContext(fs.readFileSync(path.join(pages, name + '.js'), 'utf8'), dom.getInternalVMContext());
  K.onStart();
  return {
    w, d, K,
    click: e => e.dispatchEvent(new w.MouseEvent('click', {bubbles: true})),
    flush() {while (timers.size) {const [id, fn] = timers.entries().next().value; timers.delete(id); fn();}},
  };
}

const examples = {
  roof: {demo: 'roof', count: 2}, characters: {demo: 'home', count: 11}, tracks: {demo: 'chick', count: 4},
  analogy: {demo: 'bamboo', count: 4}, stamps: {demo: 'steps', count: 4},
  'stroke-match': {demo: 'vertical', count: 3}, trace: {demo: 'trace', count: 5},
};

for (const [name, spec] of Object.entries(examples)) {
  test(name + ': first-error hints, completion, teacher replay and child reset', t => {
    const c = classroom(name), {d, K, click, flush, w} = c;
    t.after(() => w.close());
    const wrongThenRight = (wrong, right) => {
      click(wrong); assert.equal(d.querySelectorAll('.hint').length, 0, 'first error must not reveal the answer');
      click(right);
    };
    for (let i = 0; i < spec.count; i++) {
      if (name === 'roof') wrongThenRight(d.querySelector('[data-radical="water"]'), d.querySelector('#roof-card'));
      if (name === 'characters') {
        const target = d.querySelector('#character-target').textContent, cards = [...d.querySelectorAll('.letter-card')];
        wrongThenRight(cards.find(e => e.dataset.char !== target), cards.find(e => e.dataset.char === target));
      }
      if (name === 'tracks') {
        const kind = ['chick', 'dog', 'duck', 'horse'][i];
        click(d.querySelector('#animal-' + kind));
        const wrong = [...d.querySelectorAll('.footprint')].find(e => e.dataset.kind !== kind && !e.classList.contains('paired'));
        if (wrong) {click(wrong); assert.equal(d.querySelectorAll('.hint').length, 0);}
        click(d.querySelector('#track-' + kind));
        const animal = d.querySelector('#animal-' + kind), footprint = d.querySelector('#track-' + kind);
        assert.ok(parseFloat(animal.style.left) - parseFloat(footprint.style.left) + parseFloat(animal.style.width)
          < parseFloat(w.getComputedStyle(footprint.querySelector('img')).left),
        'paired animal must leave its entire footprint image visible');
      }
      if (name === 'analogy') {
        const kind = ['chick', 'dog', 'duck', 'horse'][i], targets = [...d.querySelectorAll('.likeness')];
        wrongThenRight(targets.find(e => e.dataset.kind !== kind), targets.find(e => e.dataset.kind === kind));
      }
      if (name === 'stamps') {
        const kind = ['chick', 'dog', 'duck', 'horse'][i], animals = [...d.querySelectorAll('.stamp-animal')];
        wrongThenRight(animals.find(e => e.dataset.kind !== kind), animals.find(e => e.dataset.kind === kind));
        for (let step = 0; step < 3; step++) {
          click(d.querySelector('#step-' + (step + 1)));
          const marks = d.querySelectorAll('.stamp-mark');
          assert.equal(marks.length, step + 1);
          const animal = d.querySelector('.stamp-animal[data-kind="' + kind + '"]');
          assert.ok(parseFloat(marks[step].style.left) + 120 <= parseFloat(animal.style.left) + 15,
            'new footprint must be visible behind the animal');
        }
      }
      if (name === 'stroke-match') {
        const kind = ['vertical', 'double', 'hook'][i], targets = [...d.querySelectorAll('.stroke-choice')];
        wrongThenRight(targets.find(e => e.dataset.kind !== kind), targets.find(e => e.dataset.kind === kind));
      }
      if (name === 'trace') {
        const ink = d.querySelector('#trace-ink'), next = d.querySelector('#trace-next');
        assert.equal(next.disabled, true);
        const pointer = (type, x, y) => ink.dispatchEvent(new w.MouseEvent(type, {bubbles: true, clientX: x, clientY: y}));
        for (let y = 14; y < 200; y += 16) {
          pointer('pointerdown', 14, y); pointer('pointermove', 426, y); pointer('pointerup', 426, y);
        }
        assert.equal(next.disabled, false); click(next);
      }
      flush();
    }
    assert.ok(K.finished, 'all child levels must reach the finish state');
    if (name === 'trace') assert.deepEqual(K.level, [5, 5]);
    K.onState({demo: spec.demo});
    assert.deepEqual(K.level, [spec.count, 0], 'teacher replay must not inherit the last child level');
    assert.equal(K.stars, 0);
    if (name === 'stamps') assert.equal(d.querySelector('#stamp-target').getAttribute('src'), '__IMG:bamboo-leaf__');
    if (name === 'analogy') assert.equal(d.querySelector('#analogy-picture').getAttribute('src'), '__IMG:track-chick__');
    K.onState({phase: 'play'});
    assert.equal(K.stars, 0); assert.equal(d.querySelectorAll('.hint').length, 0);
    if (name === 'roof') assert.equal(d.querySelectorAll('#roof-slot .radical-card').length, 0);
    if (name === 'characters') assert.equal(d.querySelectorAll('#character-bank .letter-card').length, 3);
    if (name === 'tracks') assert.equal(d.querySelectorAll('.paired').length, 0);
    if (name === 'stamps') assert.equal(d.querySelectorAll('.stamp-mark').length, 0);
    if (name === 'trace') {
      assert.equal(d.querySelector('#trace-word').textContent, '用');
      assert.equal(d.querySelector('#trace-next').disabled, true);
    }
    K.finished.again(); assert.equal(K.stars, 0);
  });
}
