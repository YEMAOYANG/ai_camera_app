import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { RESPONSIVE_FRAME_LAYOUT_SHIM } = require('../.runtime/OpenMAIC/lib/interactive/responsive-frame-layout.ts');

function frame(initial = [0, 0], loading = false) {
  const listeners = new Map(), callbacks = [], root = { clientWidth: initial[0], clientHeight: initial[1] };
  let observer, resizes = 0;
  const parent = {};
  const window = { parent,
    addEventListener(type, fn) { const list = listeners.get(type) ?? []; list.push(fn); listeners.set(type, list); },
    dispatchEvent(event) { if (event.type === 'resize') resizes++; for (const fn of listeners.get(event.type) ?? []) fn(event); },
  };
  const document = { documentElement: root, readyState: loading ? 'loading' : 'complete',
    addEventListener: window.addEventListener };
  vm.runInNewContext(RESPONSIVE_FRAME_LAYOUT_SHIM.replace(/^<script[^>]*>|<\/script>$/g, ''), {
    window, document, Event: class { constructor(type) { this.type = type; } },
    requestAnimationFrame: fn => callbacks.push(fn),
    ResizeObserver: class { constructor(fn) { observer = fn; } observe(element) { assert.equal(element, root); } },
  });
  return { root,
    get resizes() { return resizes; },
    flush() { for (let i = 0; callbacks.length && i < 10; i++) callbacks.shift()(); assert.equal(callbacks.length, 0, 'resize dispatch must settle'); },
    observe() { observer(); },
    ready() { window.dispatchEvent({ type: 'DOMContentLoaded' }); },
    visible(value, source = parent) { window.dispatchEvent({ type: 'message', source, data: { type: 'mira:checkpoint-visibility', active: value } }); },
  };
}

test('a zero-size initial frame waits and then repairs the authored layout at its real size', () => {
  const f = frame(); f.flush(); assert.equal(f.resizes, 0);
  f.root.clientWidth = 1000; f.root.clientHeight = 563; f.observe(); f.flush();
  assert.equal(f.resizes, 1);
});
test('positive initial layout is measured after authored DOMContentLoaded handlers', () => {
  const f = frame([393, 740], true); f.flush(); assert.equal(f.resizes, 0);
  f.ready(); f.flush(); assert.equal(f.resizes, 1);
});
test('unchanged resize observations and the synthetic resize do not form a loop', () => {
  const f = frame([1000, 563]); f.flush();
  for (let i = 0; i < 8; i++) f.observe(); f.flush(); assert.equal(f.resizes, 1);
  f.root.clientWidth = 393; f.observe(); f.flush(); assert.equal(f.resizes, 2);
});
test('hidden then visible at the same size remeasures without reloading the activity', () => {
  const f = frame([1000, 563]); f.flush(); f.visible(false); f.flush();
  assert.equal(f.resizes, 1); f.visible(true); f.flush(); assert.equal(f.resizes, 2);
});
test('zero height is not a layout and its restoration is measured even at the old size', () => {
  const f = frame([1000, 563]); f.flush();
  f.root.clientHeight = 0; f.observe(); f.flush(); assert.equal(f.resizes, 1);
  f.root.clientHeight = 563; f.observe(); f.flush(); assert.equal(f.resizes, 2);
});
test('unrelated windows cannot force layout and malformed visibility does not reset it', () => {
  const f = frame([1000, 563]); f.flush();
  f.visible(true, {}); f.visible('yes'); f.flush(); assert.equal(f.resizes, 1);
});
