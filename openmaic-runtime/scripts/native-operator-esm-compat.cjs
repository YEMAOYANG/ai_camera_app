'use strict';

// Local tsx/CJS operators import Native packages whose exports only declare
// "import". Preserve normal resolution (especially pg/pg-pool); retry only the
// known Native package families after an actual missing-export rejection.
// This hook loads modules only. It does not start workers or run recovery.
const { registerHooks, createRequire } = require('node:module');
const fs = require('node:fs');
const path = require('node:path');

registerHooks({
  resolve(specifier, context, nextResolve) {
    try {
      return nextResolve(specifier, context);
    } catch (error) {
      if (
        error.code !== 'ERR_PACKAGE_PATH_NOT_EXPORTED' ||
        !(
          specifier.startsWith('@openmaic/') ||
          specifier.startsWith('@earendil-works/')
        )
      ) {
        throw error;
      }
      return nextResolve(specifier, {
        ...context,
        conditions: [...new Set([...context.conditions, 'import'])],
      });
    }
  },
});

// Playwright serializes probe functions into a separate browser context. tsx's
// keepNames helper is scoped to the Node module and cannot travel with them.
// Transpile only these existing probes without that cosmetic name helper; their
// assertions, inputs, return values and source files stay unchanged.
const nativeRoot = path.resolve(__dirname, '../.runtime/OpenMAIC');
const nativeRequire = createRequire(path.join(nativeRoot, 'package.json'));
const esbuild = createRequire(nativeRequire.resolve('tsx/package.json'))('esbuild');
const nativeProbeFiles = new Set([
  'mira-formal-scene-dom.ts',
  'mira-formal-scene-inspector.ts',
  'mira-formal-exploration.ts',
].map((name) => path.join(nativeRoot, 'lib/server', name)));
const loadTypeScript = require.extensions['.ts'];
if (!loadTypeScript) throw new Error('NATIVE_OPERATOR_REQUIRES_TSX_CJS_FIRST');
require.extensions['.ts'] = function loadNativeProbe(module, filename) {
  const probe = nativeProbeFiles.has(filename);
  const localModule = filename.startsWith(path.join(nativeRoot, 'lib') + path.sep)
    || filename.startsWith(path.join(nativeRoot, 'scripts') + path.sep);
  if (!probe && !localModule) return loadTypeScript(module, filename);
  const source = fs.readFileSync(filename, 'utf8');
  if (!probe && !/\bimport\s*\(/.test(source)) return loadTypeScript(module, filename);
  // This operator runs as CJS. Node's ESM view of a tsx-transformed local
  // module can expose only `default`, breaking an internal named import.
  // Preserve the asynchronous boundary but resolve local dynamic imports
  // through this same CJS loader. Production and dependency files are untouched.
  const result = esbuild.transformSync(source, {
    loader: 'ts',
    format: 'cjs',
    target: 'es2022',
    supported: { 'dynamic-import': false },
    keepNames: !probe,
    sourcefile: filename,
  });
  module._compile(result.code, filename);
};
