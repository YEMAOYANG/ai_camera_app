import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

for (const [page, template] of [
  ['badge-marbles', 'magnetMarbles'],
  ['interview-dispatch', 'listenDelivery'],
]) {
  test(`${page} clears teacher highlights before the shared handoff reset`, () => {
    const events = [];
    const highlights = ['first', 'second'].map(id => ({
      classList: { remove: name => events.push([id, name]) },
    }));
    const resetResult = {};
    const K = {
      ready() {},
      game() {},
      gameTemplates: { [template]: () => ({}) },
      $$(selector) {
        assert.equal(selector, '.teach-hl');
        return highlights;
      },
      onState(state, content) {
        assert.equal(this, K);
        events.push([state, content]);
        return resetResult;
      },
    };
    const source = readFileSync(new URL(`../pages/${page}.js`, import.meta.url), 'utf8');
    runInNewContext(source, { K });

    const demo = { demo: true, level: 1, pause: true };
    const unpause = { pause: false };
    const handoff = { demo: false, level: 1, pause: false };
    const content = { reason: 'teacher handoff' };
    assert.equal(K.onState(demo), resetResult);
    assert.equal(K.onState(unpause), resetResult);
    assert.equal(K.onState(handoff, content), resetResult);
    assert.deepEqual(events, [
      [demo, undefined],
      [unpause, undefined],
      ['first', 'teach-hl'],
      ['second', 'teach-hl'],
      [handoff, content],
    ]);
  });
}
