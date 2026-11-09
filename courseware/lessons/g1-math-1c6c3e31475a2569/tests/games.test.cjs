const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const source = path.resolve(__dirname, '..');
const {JSDOM} = createRequire(path.resolve(source, '../../../student-web/package.json'))('jsdom');

function page(id) {
  const dom = new JSDOM('<div id="star-n">0</div>' + fs.readFileSync(path.join(source, `pages/${id}.html`), 'utf8'), {runScripts:'outside-only'});
  const w = dom.window, d = w.document, timers = [], messages = [];
  w.setTimeout = fn => {timers.push({fn, active:true}); return timers.length;};
  w.clearTimeout = id => {if(timers[id-1]) timers[id-1].active = false;};
  w.Audio = class {play() {return Promise.resolve();} pause() {}};
  w.K = {
    $: selector => d.querySelector(selector),
    $$: selector => [...d.querySelectorAll(selector)],
    el(tag, cls, html, parent) {const e=d.createElement(tag);e.className=cls;if(html!=null)e.innerHTML=html;if(parent)parent.appendChild(e);return e;},
    hud() {}, owl() {}, ready() {}, levels() {}, highlight() {}, shake() {},
    say(text) {messages.push(text);}, stars:0,
    star(n) {this.stars += n;},
    finish(options) {w.finished=options;},
    shuffle: values => [...values].reverse(),
    drag(el, options) {el.gardenDrag=options;},
    sfx:{no() {}, ok() {}, drop() {}, pick() {}},
  };
  w.eval(fs.readFileSync(path.join(source, `pages/${id}.js`),'utf8'));
  function next() {const item=timers.find(t=>t.active);assert.ok(item,'a progression callback is pending');item.active=false;item.fn();}
  return {w,d,timers,messages,next,close:()=>w.close()};
}

test('quantity cards reject a first mistake without giving the answer, move real objects, complete and reset',()=>{
  const p=page('p02');try {
    p.w.K.onStart();
    p.d.querySelector('[data-count="2"]').click();
    assert.equal(p.w.K.stars,0);
    assert.equal(p.d.querySelectorAll('#garden-board img').length,0);
    assert.doesNotMatch(p.messages.at(-1),/三|3|正确/);
    for(const n of [3,5,4]) {
      p.d.querySelector(`[data-count="${n}"]`).click();
      assert.equal(p.d.querySelectorAll('#garden-board img').length,n);
      p.next();
    }
    assert.ok(p.w.finished);assert.equal(p.w.K.stars,3);
    p.w.finished.again();
    assert.equal(p.w.K.stars,0);assert.equal(p.d.querySelectorAll('#garden-board img').length,0);
    assert.equal(p.d.querySelector('#garden-context').textContent,'名片图卡');
  } finally {p.close();}
});

test('quantity teacher demonstration does not accept student answers or keep demonstration objects in play',()=>{
  const p=page('p02');try {
    p.w.K.onState({demo:true});p.d.querySelector('[data-count="2"]').click();
    assert.equal(p.d.querySelectorAll('#garden-board img').length,0);
    p.w.K.onState({demoPlaced:true});assert.equal(p.d.querySelectorAll('#garden-board img').length,2);
    p.w.K.onState({play:true});assert.equal(p.d.querySelectorAll('#garden-board img').length,0);
    assert.equal(p.w.K.stars,0);
  } finally {p.close();}
});

test('shape game supports wrong/retry, tap-and-place and drag, all levels and replay',()=>{
  const p=page('p06');try {
    p.w.K.onStart();
    p.d.querySelector('[data-item="box"]').click();p.d.querySelector('#garden-match').click();
    assert.equal(p.w.K.stars,0);assert.equal(p.d.querySelectorAll('#garden-match img').length,0);
    assert.doesNotMatch(p.messages.at(-1),/橘子|方盒|正确/);
    p.d.querySelector('[data-item="orange"]').click();p.d.querySelector('#garden-match').click();
    assert.match(p.d.querySelector('#garden-match img').src,/orange/);p.next();
    for(const key of ['box','orange']) {
      const choice=p.d.querySelector(`[data-item="${key}"]`);
      choice.gardenDrag.onDrop(choice,p.d.querySelector('#garden-match'));
      assert.equal(p.d.querySelectorAll('#garden-match img').length,1);p.next();
    }
    assert.equal(p.w.K.stars,3);assert.ok(p.w.finished);
    p.w.finished.again();assert.equal(p.d.querySelectorAll('#garden-match img').length,0);assert.equal(p.w.K.stars,0);
  } finally {p.close();}
});

test('shape demonstration is locked and a fresh play removes its shown match',()=>{
  const p=page('p06');try {
    p.w.K.onState({demo:true});p.d.querySelector('[data-item="orange"]').click();p.d.querySelector('#garden-match').click();
    assert.equal(p.d.querySelectorAll('#garden-match img').length,0);
    p.w.K.onState({demoMatch:true});assert.equal(p.d.querySelectorAll('#garden-match img').length,1);
    p.w.K.onState({play:true});assert.equal(p.d.querySelectorAll('#garden-match img').length,0);assert.equal(p.w.K.stars,0);
  } finally {p.close();}
});

test('turn game blocks extra moves on the friend turn, fills each slot once, finishes and resets',()=>{
  const p=page('p08');try {
    p.w.K.onStart();p.d.querySelector('[data-material="ball"]').click();
    const token=p.d.querySelector('#garden-token');token.click();
    assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,1);
    token.click();p.d.querySelector('[data-slot="1"]').click();
    assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,1,'a child cannot add during the virtual friend turn');
    p.next();assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,2);
    let safety=0;
    while(!p.w.finished&&safety++<35) {
      if(p.d.querySelector('#garden-turn').textContent==='轮到你')token.click();
      else p.next();
      assert.equal(p.d.querySelectorAll('.garden-slot img').length,p.d.querySelectorAll('.garden-slot.filled').length);
    }
    assert.ok(p.w.finished,'all three rounds are reachable');
    p.w.finished.again();assert.equal(p.w.K.stars,0);assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,0);
    assert.equal(p.d.querySelector('#garden-turn').textContent,'先选材料');
  } finally {p.close();}
});

test('reset invalidates pending friend callbacks and teacher operations never award a star',()=>{
  const p=page('p08');try {
    p.w.K.onStart();p.d.querySelector('[data-material="cube"]').click();p.d.querySelector('#garden-token').click();
    const stale=p.timers.find(t=>t.active).fn;
    p.w.K.onStart();stale();
    assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,0);
    assert.equal(p.d.querySelector('#garden-turn').textContent,'先选材料');
    p.w.K.onState({demo:true});p.w.K.onState({demoPlace:true});assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,1);
    assert.equal(p.w.K.stars,0);p.w.K.onState({play:true});assert.equal(p.d.querySelectorAll('.garden-slot.filled').length,0);
  } finally {p.close();}
});
