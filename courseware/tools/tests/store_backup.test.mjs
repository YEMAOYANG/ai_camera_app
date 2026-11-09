import test from 'node:test';
import assert from 'node:assert/strict';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {uploadBackup, fetchBackup, validateReceipt} from '../store_backup.mjs';

const hash = b => crypto.createHash('sha256').update(b).digest('hex');
const config = {endpoint: 'http://storage.invalid', bucket: 'study', region: 'us-east-1'};
const fixture = async t => {
  assert.ok(process.env.MIRA_TASK_TMPDIR, 'Run through tools/task_tmp.py');
  const root = await fsp.mkdtemp(path.join(await fsp.realpath(process.env.MIRA_TASK_TMPDIR), 'backup-'));
  t.after(() => fsp.rm(root, {recursive: true, force: true}));
  const directory = path.join(root, 'source');
  await fsp.mkdir(directory);
  const files = [];
  for (const [relative, bytes] of [['courseware-sources.zip', Buffer.from('archive fixture')], ['backup-receipt.json', Buffer.from('{"fixture":true}')]]) {
    await fsp.writeFile(path.join(directory, relative), bytes);
    files.push({path: relative, sha256: hash(bytes), byteSize: bytes.length});
  }
  const objects = new Map(), calls = [];
  const client = {async send(command) {
    const type = command.constructor.name, input = command.input;
    calls.push({type, input});
    const object = objects.get(input.Key);
    if (type === 'PutObjectCommand') {
      assert.equal(input.IfNoneMatch, '*');
      assert.equal(object, undefined);
      const parts = []; for await (const part of input.Body) parts.push(Buffer.from(part));
      const bytes = Buffer.concat(parts);
      objects.set(input.Key, {bytes, ETag: '"' + hash(bytes) + '"', VersionId: 'v1'});
      return {};
    }
    if (!object) { const e = Error('missing'); e.name = 'NotFound'; throw e; }
    const metadata = {ContentLength: object.bytes.length, ETag: object.ETag, VersionId: object.VersionId};
    if (type === 'HeadObjectCommand') return metadata;
    assert.equal(type, 'GetObjectCommand');
    assert.equal(input.IfMatch, object.ETag);
    assert.equal(input.VersionId, object.VersionId);
    return {...metadata, Body: Readable.from([object.bytes])};
  }};
  return {root, directory, files, objects, calls, dependencies: {config, client, readBackup: async () => files}};
};

test('uploads once, reads all bytes and resumes without another PUT', async t => {
  const f = await fixture(t);
  const receipt = await uploadBackup(f.directory, f.dependencies);
  assert.equal(receipt.complete, true);
  assert.equal(receipt.localSourcesRetained, true);
  assert.equal(f.calls.filter(x => x.type === 'PutObjectCommand').length, 2);
  assert.equal(f.calls.filter(x => x.type === 'GetObjectCommand').length, 2);
  await uploadBackup(f.directory, f.dependencies);
  assert.equal(f.calls.filter(x => x.type === 'PutObjectCommand').length, 2);
  assert.equal(f.calls.filter(x => x.type === 'GetObjectCommand').length, 4);
  assert.equal(await fsp.readFile(path.join(f.directory, 'courseware-sources.zip'), 'utf8'), 'archive fixture');
});

test('existing corrupt bytes are refused without overwriting or declaring completion', async t => {
  const f = await fixture(t), archive = f.files[0];
  const key = `备份/课件恢复/v1/${archive.sha256}/${archive.path}`;
  f.objects.set(key, {bytes: Buffer.alloc(archive.byteSize, 1), ETag: '"bad"', VersionId: 'v2'});
  await assert.rejects(uploadBackup(f.directory, f.dependencies), /SHA-256 mismatch/);
  assert.equal(f.calls.filter(x => x.type === 'PutObjectCommand').length, 0);
  await assert.rejects(fsp.stat(path.join(f.directory, 'remote-verification.json')), {code: 'ENOENT'});
  await assert.rejects(fsp.stat(path.join(f.directory, '.upload.lock')), {code: 'ENOENT'});
});

test('local verifier failure prevents every network operation', async t => {
  const f = await fixture(t);
  await assert.rejects(uploadBackup(f.directory, {...f.dependencies, readBackup: async (_, options) => {
    assert.equal(options.remoteExport, true);
    throw Error('bad ZIP');
  }}), /bad ZIP/);
  assert.equal(f.calls.length, 0);
});

test('fetch verifies bytes and archive structure and refuses an existing destination', async t => {
  const f = await fixture(t), receipt = await uploadBackup(f.directory, f.dependencies);
  let checked = 0;
  const destination = path.join(f.root, 'restored');
  await fetchBackup(receipt, destination, {...f.dependencies, readBackup: async directory => {
    checked++;
    assert.equal(await fsp.readFile(path.join(directory, 'courseware-sources.zip'), 'utf8'), 'archive fixture');
  }});
  assert.equal(checked, 1);
  await assert.rejects(fetchBackup(receipt, destination, f.dependencies), {code: 'EEXIST'});
});

test('failed archive verification leaves diagnostics but no success receipt', async t => {
  const f = await fixture(t), receipt = await uploadBackup(f.directory, f.dependencies);
  const destination = path.join(f.root, 'failed-restore');
  await assert.rejects(fetchBackup(receipt, destination, {...f.dependencies, readBackup: async () => {throw Error('bad ZIP');}}), /bad ZIP/);
  await assert.rejects(fsp.stat(path.join(destination, 'remote-verification.json')), {code: 'ENOENT'});
  assert.ok((await fsp.stat(path.join(destination, 'courseware-sources.zip'))).isFile());
});

test('receipt rejects traversal, duplicates, foreign keys and missing required files', async t => {
  const f = await fixture(t), receipt = await uploadBackup(f.directory, f.dependencies);
  for (const edit of [
    r => {r.files[0].path = '../escape';},
    r => {r.files.push({...r.files[0]});},
    r => {r.files[0].objectKey = 'another/course.zip';},
    r => {r.files = r.files.slice(0, 1);},
    r => {r.archiveSha256 = '0'.repeat(64);},
  ]) {
    const changed = JSON.parse(JSON.stringify(receipt)); edit(changed);
    assert.throws(() => validateReceipt(changed));
  }
});

test('symlinked local files and a concurrent upload are refused', async t => {
  const f = await fixture(t);
  await fsp.writeFile(path.join(f.directory, '.upload.lock'), 'another writer');
  await assert.rejects(uploadBackup(f.directory, f.dependencies), {code: 'EEXIST'});
  assert.equal(await fsp.readFile(path.join(f.directory, '.upload.lock'), 'utf8'), 'another writer');
  await fsp.unlink(path.join(f.directory, '.upload.lock'));
  await fsp.rename(path.join(f.directory, 'courseware-sources.zip'), path.join(f.root, 'archive.zip'));
  await fsp.symlink(path.join(f.root, 'archive.zip'), path.join(f.directory, 'courseware-sources.zip'));
  await assert.rejects(uploadBackup(f.directory, f.dependencies), /symbolic link/);
  assert.equal(f.calls.length, 0);
});
