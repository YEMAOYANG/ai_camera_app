// Run through `node --input-type=module` on stdin from the native source cwd.
// This resolves the same bare package export as Next's external server package.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, realpathSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

globalThis.fetch = () => { throw new Error('Generation profile probe forbids network access'); };
const { generateSceneContent, generateWidgetContent, buildPrompt } = await import('@openmaic/generation');
const entry = import.meta.resolve('@openmaic/generation');
assert.match(entry, /\/dist\/index\.js$/, 'Production package must resolve its compiled dist export');
assert.equal(realpathSync(fileURLToPath(entry)), realpathSync(resolve('packages/@openmaic/generation/dist/index.js')),
  'Production export resolved outside the selected native workspace package');
const title = 'Local provider-free profile probe';
const description = 'Frozen observation only';
const keyPoints = ['Frozen local concept'];
const languageDirective = 'Local registered teacher';
const evidence = [];
const digest = (text) => createHash('sha256').update(text).digest('hex');
for (const widgetType of ['game', 'visualization3d']) {
  const outline = {
    id: 'local-production-profile-probe', type: 'interactive', widgetType,
    title, description, keyPoints, order: 1,
    widgetOutline: { gameType: 'quiz', visualizationType: 'geometry', objects: [], interactions: [] },
  };
  const ordinaryVariables = widgetType === 'game'
    ? { title, description, keyPoints: keyPoints.join('\n'), languageDirective,
        gameType: 'quiz', scoring: { correctPoints: 10, speedBonus: 5 } }
    : { title, description, keyPoints: keyPoints.join('\n'), languageDirective,
        visualizationType: 'geometry', objects: [], interactions: [] };
  for (const route of ['scene', 'widget']) {
    for (const textbook of [false, true]) {
      let captured = null;
      let calls = 0;
      const mockAI = async (system, user) => {
        calls += 1;
        captured = { system, user };
        return '<html><head></head><body></body></html>';
      };
      const profile = textbook ? { textbookPromptProfile: 'textbook-v1' } : {};
      if (route === 'scene') {
        await generateSceneContent(outline, mockAI, { languageDirective, interactiveIncludeKatex: false, ...profile });
      } else {
        await generateWidgetContent(outline, mockAI, languageDirective, { includeKatex: false, ...profile });
      }
      assert.equal(calls, 1, `${route}/${widgetType}: expected one local mock call`);
      assert.ok(captured && typeof captured.system === 'string' && typeof captured.user === 'string');
      if (textbook) {
        const heading = widgetType === 'game'
          ? '# Textbook Picture Game Authoring v1'
          : '# Textbook Manipulable Geometry Authoring v1';
        assert.ok(captured.system.includes(heading), `${route}/${widgetType}: stale or incorrect textbook package export`);
        assert.ok(captured.system.includes('Authoritative textbook activity contract'));
        for (const command of ['SET_WIDGET_STATE', 'HIGHLIGHT_ELEMENT', 'ANNOTATE_ELEMENT', 'REVEAL_ELEMENT']) {
          assert.ok(captured.system.includes(`case '${command}'`), `${route}/${widgetType}: missing native command`);
        }
        assert.ok(captured.system.includes("window.miraNarrate('observe')"));
        assert.ok(captured.system.includes('min-width:48px; min-height:48px; flex-shrink:0'));
        const full = captured.system + captured.user;
        assert.doesNotMatch(full, /[\p{Extended_Pictographic}\u{1f1e6}-\u{1f1ff}\u20e3]/u);
        assert.doesNotMatch(full, /\{\{|Scoring Configuration/);
        for (const value of [title, description, keyPoints[0], languageDirective]) assert.ok(captured.user.includes(value));
      } else {
        assert.deepEqual(captured, buildPrompt(widgetType === 'game' ? 'game-content' : 'visualization3d-content', ordinaryVariables),
          `${route}/${widgetType}: ordinary prompts changed`);
      }
      evidence.push({ route, widgetType, profile: textbook ? 'textbook-v1' : 'ordinary',
        systemSha256: digest(captured.system), userSha256: digest(captured.user) });
    }
  }
}
console.log(JSON.stringify({ schemaVersion: 'mira.generation-package-profile-probe.v1', status: 'passed',
  providerCalls: 0, mockCalls: evidence.length, entry, entrySha256: digest(readFileSync(fileURLToPath(entry))), evidence }));
