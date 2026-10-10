import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const scripts = dirname(fileURLToPath(import.meta.url));
const probe = readFileSync(join(scripts, 'probe-generation-package.mjs'), 'utf8');
const runtime = join(scripts, 'native-runtime.sh');

// Tiny fake exports model a built package, not a TypeScript/vitest src alias.
// Also used by the existing native-runtime environment boundary harness.
export function writeFixture(root, mutation = '') {
  const packageDir = join(root, 'packages/@openmaic/generation');
  mkdirSync(join(packageDir, 'dist'), { recursive: true });
  mkdirSync(join(root, 'node_modules/@openmaic'), { recursive: true });
  mkdirSync(join(root, 'node_modules/typescript/bin'), { recursive: true });
  symlinkSync(packageDir, join(root, 'node_modules/@openmaic/generation'));
  writeFileSync(join(packageDir, 'package.json'), JSON.stringify({ name: '@openmaic/generation', type: 'module', exports: { '.': { import: './dist/index.js' } } }));
  writeFileSync(join(packageDir, 'tsconfig.json'), '{}');
  writeFileSync(join(root, 'node_modules/typescript/bin/tsc'), `
const fs = require('node:fs');
if(process.env.APP_AI_API_KEY || process.env.DEEPSEEK_API_KEY || process.env.MIRA_INTERNAL_API_TOKEN || process.env.NEXT_PUBLIC_UNRELATED) throw new Error('dirty compiler environment');
if(JSON.stringify(process.argv.slice(2)) !== JSON.stringify(['-p','tsconfig.json','--incremental','false'])) throw new Error('compiler arguments');
fs.writeFileSync('compiled.test-only', 'compiled');
`);
  writeFileSync(join(packageDir, 'dist/index.js'), `
import { existsSync } from 'node:fs';
const mutation = ${JSON.stringify(mutation)};
function prompts(type, textbook) {
  if (!textbook || mutation === 'stale') return {system:'ordinary '+type,user:'ordinary variables'};
  let system = (type === 'game' ? '# Textbook Picture Game Authoring v1' : '# Textbook Manipulable Geometry Authoring v1')
    + ' Authoritative textbook activity contract '
    + "case 'SET_WIDGET_STATE' case 'HIGHLIGHT_ELEMENT' case 'ANNOTATE_ELEMENT' case 'REVEAL_ELEMENT' "
    + "window.miraNarrate('observe') min-width:48px; min-height:48px; flex-shrink:0";
  if(mutation === 'emoji') system += String.fromCodePoint(0x1f408);
  if(mutation === 'missing_command') system = system.replace("case 'REVEAL_ELEMENT'",'');
  return {system,user:'Local provider-free profile probe Frozen observation only Frozen local concept Local registered teacher'};
}
export function buildPrompt(id) { return prompts(id === 'game-content' ? 'game' : 'visualization3d',false); }
async function generate(outline,call,options={}) {
  if(mutation === 'network') await fetch('https://example.invalid/forbidden');
  const p = prompts(outline.widgetType,options.textbookPromptProfile === 'textbook-v1');
  if(mutation === 'ordinary_changed' && !options.textbookPromptProfile) p.user += ' changed';
  await call(p.system,p.user); return {type:'interactive',html:'<html></html>'};
}
export const generateSceneContent=generate;
export function generateWidgetContent(outline,call,language,options) {return generate(outline,call,options);}
`);
}

if (process.argv[2] === '--write-fixture') {
  writeFixture(process.argv[3]);
} else {
  function withFixture(mutation, run) {
    const root = mkdtempSync(join(tmpdir(), 'mira-generation-probe-'));
    try { writeFixture(root, mutation); return run(root); } finally { rmSync(root, { recursive: true, force: true }); }
  }
  function runProbe(root) {
    return spawnSync(process.execPath, ['--input-type=module'], { cwd: root, input: probe, encoding: 'utf8', timeout: 15000 });
  }
  test('real bare export probe covers both routes and ordinary templates without Provider calls', () => {
    withFixture('', root => {
      const result = runProbe(root);
      assert.equal(result.status, 0, result.stderr);
      const report = JSON.parse(result.stdout);
      assert.equal(report.providerCalls, 0);
      assert.equal(report.mockCalls, 8);
      assert.equal(report.evidence.length, 8);
      assert.match(report.entry, /\/packages\/@openmaic\/generation\/dist\/index\.js$/);
    });
  });
  for (const mutation of ['stale', 'emoji', 'missing_command', 'ordinary_changed', 'network']) {
    test(`production export probe rejects ${mutation} package`, () => {
      withFixture(mutation, root => {
        const result = runProbe(root);
        assert.notEqual(result.status, 0);
        assert.ok(result.stderr.length);
      });
    });
  }
  test('package build uses local tsc in a clean environment, then runs the export probe', () => {
    withFixture('', root => {
      const result = spawnSync('bash', ['-c', 'source "$1"; SOURCE_DIR="$2"; OPENMAIC_PID_FILE="$2/missing.pid"; build_generation_package', '_', runtime, root], {
        encoding: 'utf8', timeout: 15000,
        env: { ...process.env, APP_AI_API_KEY: 'test-no-log', DEEPSEEK_API_KEY: 'test-no-log', MIRA_INTERNAL_API_TOKEN: 'test-no-log', NEXT_PUBLIC_UNRELATED: 'test-no-log' },
      });
      assert.equal(result.status, 0, result.stderr);
      assert.equal(readFileSync(join(root, 'packages/@openmaic/generation/compiled.test-only'), 'utf8'), 'compiled');
      assert.equal(JSON.parse(result.stdout).status, 'passed');
      assert.ok(!result.stdout.includes('test-no-log'));
    });
  });
  test('failed probe blocks both production start paths before credentials or launch', () => {
    withFixture('stale', root => {
      for (const entry of ['start_openmaic', 'run_openmaic_production_foreground']) {
        const script = `source "$1"; SOURCE_DIR="$2"; require_openmaic_dependencies(){ :; }; reject_openmaic_build_dotenv_files(){ :; }; require_openmaic_production_build(){ :; }; load_openmaic_provider_env(){ echo UNEXPECTED_PROVIDER_LOAD; }; ${entry}`;
        const result = spawnSync('bash', ['-c', script, '_', runtime, root], { encoding: 'utf8', timeout: 15000 });
        assert.notEqual(result.status, 0, entry);
        assert.ok(!result.stdout.includes('UNEXPECTED_PROVIDER_LOAD'), entry);
        assert.match(result.stderr, /provider-free production export probe/);
      }
    });
  });
  test('generation build refuses a live managed source process without touching dist', () => {
    withFixture('', root => {
      writeFileSync(join(root, 'live.pid'), '123');
      const script = 'source "$1"; SOURCE_DIR="$2"; OPENMAIC_PID_FILE="$2/live.pid"; process_is_alive(){ return 0; }; process_cwd(){ printf "%s" "$SOURCE_DIR"; }; build_generation_package';
      const result = spawnSync('bash', ['-c', script, '_', runtime, root], { encoding: 'utf8', timeout: 15000 });
      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /caches imported modules/);
      assert.throws(() => readFileSync(join(root, 'packages/@openmaic/generation/compiled.test-only')));
    });
  });
  test('Next production build stops before Next if the generation package fails its probe', () => {
    withFixture('stale', root => {
      const script = 'source "$1"; SOURCE_DIR="$2"; OPENMAIC_PID_FILE="$2/missing.pid"; bootstrap_openmaic_source(){ :; }; require_openmaic_dependencies(){ :; }; load_runtime_origin_env(){ echo UNEXPECTED_NEXT_PREPARATION; }; build_openmaic_production';
      const result = spawnSync('bash', ['-c', script, '_', runtime, root], { encoding: 'utf8', timeout: 15000 });
      assert.notEqual(result.status, 0);
      assert.ok(!result.stdout.includes('UNEXPECTED_NEXT_PREPARATION'));
    });
  });
}
