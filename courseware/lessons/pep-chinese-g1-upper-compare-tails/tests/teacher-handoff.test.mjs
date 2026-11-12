import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { runInNewContext } from 'node:vm';

for (const [page, template] of [
  ['bubble-dock', 'wordBubbles'],
  ['tail-post', 'listenDelivery'],
]) {
  test(`${page} clears the visual teacher outlines only at child handoff`, () => {
    const removed = [];
    let engineConfig;
    const templateConfig = { reset() {}, update() {}, draw() {} };
    const K = {
      ready() {},
      game(config) {
        engineConfig = config;
        return { follow() {} };
      },
      gameTemplates: { [template]: () => templateConfig },
      $$(selector) {
        assert.equal(selector, '.teach-hl');
        return ['target', 'control'].map(id => ({
          classList: { remove: name => removed.push([id, name]) },
        }));
      },
    };
    const source = readFileSync(new URL(`../pages/${page}.js`, import.meta.url), 'utf8');
    runInNewContext(source, { K });
    assert.equal(engineConfig, templateConfig);
    engineConfig.onState({}, { demo: true, level: 1, pause: true });
    engineConfig.onState({}, { pause: false });
    assert.deepEqual(removed, []);
    engineConfig.onState({}, { demo: false, level: 1, pause: false });
    assert.deepEqual(removed, [['target', 'teach-hl'], ['control', 'teach-hl']]);
  });
}
