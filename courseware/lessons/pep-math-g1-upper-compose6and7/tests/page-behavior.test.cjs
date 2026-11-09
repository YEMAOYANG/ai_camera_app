const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

// Exercise lesson decisions and transitions without claiming browser or layout acceptance.
function lesson(page) {
  const ids = new Map();
  class Element {
    constructor(tag = 'div') {
      this.tagName = tag.toUpperCase(); this.children = []; this.style = {};
      this.attributes = {}; this.className = ''; this.disabled = false;
      this.classList = {
        add: (name) => { this.className += ' ' + name; },
        contains: (name) => this.className.split(/\s+/).includes(name),
      };
    }
    set id(value) { this._id = value; ids.set(value, this); }
    get id() { return this._id; }
    set innerHTML(value) {
      this.children = []; this.textContent = String(value || '').replace(/<[^>]*>/g, '');
      if (String(value).includes('<img')) this.appendChild(new Element('img'));
    }
    appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    querySelector(selector) { return this.children.find((child) => child.tagName.toLowerCase() === selector); }
  }
  const timers = new Map(); let timerId = 0; const hints = [];
  const K = {
    stars: 0, hud() {}, owl() {}, ready() {}, sfx: new Proxy({}, { get: () => () => {} }),
    $: (selector) => {
      const id = selector.replace(/^#/, '');
      if (!ids.has(id)) { const element = new Element(); element.id = id; }
      return ids.get(id);
    },
    el: (tag, cls, html, parent) => {
      const element = new Element(tag); element.className = cls || ''; element.innerHTML = html;
      if (parent) parent.appendChild(element); return element;
    },
    shuffle: (items) => items.slice(),
    drag: (element, options) => { element.drag = options; },
    levels: (total, done) => { K.progress = { total, done }; },
    say: (text, kind) => { K.lastSay = { text, kind }; },
    highlight: (target) => { hints.push(target); },
    star: (n) => { K.stars += n; },
    finish: (options) => { K.finished = options; },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'pages', page + '.js'), 'utf8'), {
    K, setTimeout: (callback) => { const id = ++timerId; timers.set(id, callback); return id; },
    clearTimeout: (id) => timers.delete(id),
  });
  const get = (id) => K.$('#' + id);
  const click = (id) => { const element = get(id); if (!element.disabled) element.onclick(); };
  const drag = (id, target) => { const element = get(id); if (element.drag.enabled()) element.drag.onDrop(element, get(target)); };
  const tick = () => { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach((callback) => callback()); };
  return { K, get, click, drag, tick, hints };
}

test('free partition rejects incomplete and duplicate groups, finishes three unique splits and resets', () => {
  const w = lesson('p02'); w.K.onStart(); w.click('save-split');
  assert.equal(w.K.stars, 0); assert.equal(w.get('loose-pieces').children.length, 6);
  assert.equal(w.hints.at(-1), '#whole-total');
  function partition(left) {
    for (let i = 1; i <= 6; i += 1) w.drag('piece-' + i, i <= left ? 'tray-left' : 'tray-right');
    w.click('save-split'); w.tick();
  }
  partition(1); partition(1); assert.equal(w.K.stars, 1);
  partition(2); partition(3); assert.ok(w.K.finished); assert.equal(w.K.stars, 3);
  w.K.finished.again(); assert.equal(w.K.stars, 0); assert.equal(w.get('loose-pieces').children.length, 6);
  w.K.onState({ demoLeft: 2 }); w.drag('piece-1', 'tray-right');
  assert.equal(w.get('left-beads').children.length, 2); assert.equal(w.K.stars, 0);
  w.K.onState({ play: true }); assert.equal(w.get('loose-pieces').children.length, 6);
});

test('ordered partition refuses a skipped row and teacher demonstrations never earn progress', () => {
  const w = lesson('p04'); w.K.onStart(); w.click('move-next'); w.click('record-next');
  assert.equal(w.K.progress.done, 0); assert.equal(w.get('ordered-left-count').textContent, 2);
  assert.equal(w.hints.at(-1), '#record-wall');
  w.K.onState({ demoLeft: 2 }); assert.equal(w.get('record-next').disabled, true); assert.equal(w.K.stars, 0);
  assert.notEqual(w.K.lastSay.kind, 'no');
  w.K.onState({ play: true });
  for (let i = 1; i <= 5; i += 1) { w.click('record-next'); if (i < 5) w.click('move-next'); }
  assert.ok(w.K.finished); assert.equal(w.K.progress.done, 5); assert.equal(w.K.stars, 5);
  w.K.finished.again(); assert.equal(w.K.progress.done, 0); assert.equal(w.get('ordered-left-count').textContent, 1);
});

test('block cuts keep their seam inside the opened gap, demonstrate rejoining and reset fully', () => {
  const w = lesson('p07'); w.K.onStart();
  for (let cut = 1; cut <= 6; cut += 1) {
    w.K.onState({ demoCut: cut });
    const blocks = w.get('block-strip').children.filter((child) => child.className === 'unit-block');
    const centre = Number.parseFloat(w.get('seam-' + cut).style.left) + 24;
    assert.ok(centre > Number.parseFloat(blocks[cut - 1].style.left) + 102);
    assert.ok(centre < Number.parseFloat(blocks[cut].style.left));
    assert.equal(w.get('part-left').textContent + w.get('part-right').textContent, 7);
  }
  assert.equal(w.K.stars, 0);
  w.K.onState({ demoCut: 0 }); assert.equal(w.get('part-left').textContent, '');
  assert.equal(w.get('block-strip').children[3].style.left, '324px');
  w.K.onState({ play: true }); w.click('save-cut'); assert.equal(w.K.stars, 0);
  w.K.onState({ demoCut: 3 }); assert.notEqual(w.K.lastSay.kind, 'no');
  w.K.onState({ play: true });
  for (let cut = 1; cut <= 3; cut += 1) { w.click('seam-' + cut); w.click('save-cut'); }
  w.tick(); assert.ok(w.K.finished); assert.equal(w.K.stars, 3);
  w.K.finished.again(); assert.equal(w.K.stars, 0); assert.equal(w.get('part-left').textContent, '');
});

test('missing-part first error leaves the box closed, later hint is recoverable and all four tasks finish', () => {
  const w = lesson('p09'); w.K.onStart();
  const choice = (n) => w.get('missing-choices').children.find((element) => element.attributes['aria-label'] === '选' + n + '颗');
  choice(4).onclick(); assert.equal(w.K.stars, 0);
  assert.equal(w.get('hidden-box').children[0].tagName, 'IMG'); assert.equal(w.hints.at(-1), '#whole-total');
  w.K.onState({ demo: true }); assert.notEqual(w.K.lastSay.kind, 'no');
  w.K.onState({ play: true }); choice(4).onclick();
  choice(4).onclick(); choice(4).onclick(); assert.equal(w.get('hidden-box').children.length, 5);
  for (const n of [5, 3, 4, 4]) { choice(n).onclick(); w.tick(); }
  assert.ok(w.K.finished); assert.equal(w.K.stars, 4);
  w.K.finished.again(); assert.equal(w.K.stars, 0); assert.equal(w.get('shown-beads').children.length, 1);
  w.K.onState({ demo: true }); assert.equal(w.get('hidden-box').children.length, 2);
  assert.ok(w.get('missing-choices').children.every((element) => element.disabled));
  w.K.onState({ play: true }); assert.equal(w.get('hidden-box').children[0].tagName, 'IMG');
});

test('whole-group merge permits withdrawal, refuses an incomplete group and finishes after replay', () => {
  const w = lesson('p11'); w.K.onStart(); w.click('check-merge');
  assert.equal(w.K.stars, 0); assert.equal(w.get('merge-target').children.length, 0);
  assert.equal(w.hints.at(-1), '#merge-target');
  w.K.onState({ demo: true }); assert.notEqual(w.K.lastSay.kind, 'no');
  w.K.onState({ play: true });
  const select = (n) => {
    const group = w.get('group-pool').children.find((element) => element.attributes['aria-label'] === '装着' + n + '颗的圆片盘');
    group.drag.onTap();
  };
  select(1); select(1); assert.equal(w.get('merge-target').children.length, 0);
  function complete() {
    for (const pair of [[1, 5], [3, 4], [2, 4]]) { pair.forEach(select); w.click('check-merge'); w.tick(); }
    assert.ok(w.K.finished); assert.equal(w.K.stars, 3);
  }
  complete(); w.K.finished.again(); assert.equal(w.K.stars, 0); assert.equal(w.K.progress.done, 0); complete();
  w.K.onState({ demo: true }); assert.equal(w.get('merge-target').children.length, 3);
  w.K.onState({ play: true }); assert.equal(w.get('merge-target').children.length, 0); assert.equal(w.K.stars, 0);
});

test('third partition hint always demonstrates a split that is still missing, without awarding it', () => {
  const w = lesson('p02'); w.K.onStart(); assert.equal(w.get('reset-split').disabled, true);
  for (let i = 1; i <= 6; i += 1) w.drag('piece-' + i, i <= 2 ? 'tray-left' : 'tray-right');
  w.click('save-split'); w.tick(); assert.equal(w.K.stars, 1);
  w.click('save-split'); assert.equal(w.get('loose-pieces').children.length, 6);
  w.click('save-split'); w.click('save-split');
  assert.equal(w.get('left-beads').children.length, 1); assert.equal(w.get('right-beads').children.length, 5);
  assert.equal(w.K.stars, 1); w.click('save-split'); assert.equal(w.K.stars, 2);
});

test('third merge hint replaces an impossible retained part with a feasible two-group demonstration', () => {
  const w = lesson('p11'); w.K.onStart(); assert.equal(w.get('reset-merge').disabled, true);
  const three = w.get('group-pool').children.find((element) => element.attributes['aria-label'] === '装着3颗的圆片盘');
  three.drag.onTap(); w.click('check-merge');
  assert.equal(w.get('merge-target').children.length, 1); assert.equal(w.K.stars, 0);
  w.click('check-merge'); w.click('check-merge');
  const parts = w.get('merge-target').children.filter((element) => element.className === 'merged-part');
  assert.equal(parts.length, 2); assert.equal(parts.reduce((sum, part) => sum + part.children.length, 0), 6);
  assert.equal(w.K.stars, 0); w.click('check-merge'); assert.equal(w.K.stars, 1);
});
