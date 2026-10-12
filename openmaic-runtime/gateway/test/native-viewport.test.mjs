import assert from 'node:assert/strict';
import { test } from 'node:test';
import { embedTextbookSceneMedia } from '../src/server.mjs';

// This integration check intentionally uses the applied native implementation,
// so a gateway-only byte-restoration test cannot hide a renderer regression.
// Run with Node 24 after the locked native source has been bootstrapped.
const [{ activityViewportMode }, { fitGenUiViewport }] = await Promise.all([
  import('../../.runtime/OpenMAIC/lib/interactive/activity-viewport.ts'),
  import('../../.runtime/OpenMAIC/lib/interactive/logical-viewport.ts'),
]).catch(cause => {
  throw new Error('Native viewport integration requires Node 24 and the locked native source. Run openmaic-runtime/scripts/native-runtime.sh bootstrap first; see openmaic-runtime/README.md.', { cause });
});

test('large classroom media retains native responsive pixels and legacy fixed sizing', () => {
  const path = '/api/classroom-media/tbpub_' + 'a'.repeat(24) + '/media/atlas.png';
  const asset = { path, mimeType: 'image/png', base64: Buffer.alloc(1024 * 1024).toString('base64') };
  const marker = '<meta name="mira-responsive-activity" content="low-reading-v1">';
  for (const head of [marker, '', '<script>const example=' + JSON.stringify(marker) + ';</script>', marker + marker]) {
    const html = '<!doctype html><html><head>' + head + '</head><body>'
      + `<img src="${path}">`.repeat(2) + '</body></html>';
    const bundled = embedTextbookSceneMedia(html, [asset]);
    const expectedMode = activityViewportMode(html);
    assert.equal(activityViewportMode(bundled), expectedMode);
    for (const width of [327, 735, 1247]) {
      const slot = { left: 0, top: 0, width, height: 424 };
      assert.deepEqual(fitGenUiViewport(slot, activityViewportMode(bundled)), fitGenUiViewport(slot, expectedMode));
      if (head === marker) assert.equal(fitGenUiViewport(slot, activityViewportMode(bundled)).scale * 48, 48);
    }
  }
});
