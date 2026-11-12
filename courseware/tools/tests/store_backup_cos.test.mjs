import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import {Readable} from 'node:stream';
import test from 'node:test';
import {mirrorBackup} from '../store_backup.mjs';

const sourceConfig = {endpoint: 'http://primary.invalid', bucket: 'study', region: 'local'};
const config = {endpoint: 'https://secondary.invalid', bucket: 'study-123', region: 'example',
  provider: 'tencent-cos'};

async function fixture(t, {encryption = 'AES256', changedVersion = false} = {}) {
  const root = await fs.mkdtemp(path.join(await fs.realpath(process.env.MIRA_TASK_TMPDIR), 'cos-backup-'));
  t.after(() => fs.rm(root, {recursive: true}));
  const directory = path.join(root, 'primary'), workspace = path.join(root, 'workspace');
  await fs.mkdir(directory);
  await fs.mkdir(workspace);
  const files = [], bytesByName = new Map();
  for (const name of ['courseware-sources.zip', 'backup-receipt.json']) {
    const bytes = Buffer.from(name);
    await fs.writeFile(path.join(directory, name), bytes);
    bytesByName.set(name, bytes);
    files.push({path: name, sha256: crypto.createHash('sha256').update(bytes).digest('hex'), byteSize: bytes.length});
  }
  const archiveSha256 = files[0].sha256;
  const primary = {schemaVersion: 'mira.courseware-backup.remote.v1', complete: true,
    storage: sourceConfig, archiveSha256, files: files.map(file => ({...file,
      objectKey: `备份/课件恢复/v1/${archiveSha256}/${file.path}`}))};
  const primaryPath = path.join(directory, 'remote-verification.json');
  await fs.writeFile(primaryPath, JSON.stringify(primary));
  const objects = new Map(), operations = [];
  const client = {async send({constructor: {name}, input}) {
    operations.push(name);
    if (name === 'PutObjectCommand') {
      assert.equal(input.IfNoneMatch, '*');
      assert.equal(input.ServerSideEncryption, 'AES256');
      const parts = [];
      for await (const part of input.Body) parts.push(part);
      objects.set(input.Key, {bytes: Buffer.concat(parts), reads: 0});
      return {};
    }
    const object = objects.get(input.Key);
    if (!object) throw Object.assign(Error('missing'), {name: 'NotFound'});
    const VersionId = changedVersion && object.reads > 0 ? 'v2' : 'v1';
    const metadata = {ContentLength: object.bytes.length, ETag: '"etag"', VersionId,
      ServerSideEncryption: encryption};
    if (name === 'HeadObjectCommand') return metadata;
    assert.equal(input.VersionId, VersionId);
    object.reads++;
    return {...metadata, Body: Readable.from([object.bytes])};
  }};
  return {directory, workspace, files, bytesByName, primaryPath, primary, operations,
    options: {sourceConfig, config, client, readBackup: async () => files}};
}

test('independently downloads versioned COS objects without changing primary evidence', async t => {
  const f = await fixture(t);
  const result = await mirrorBackup(f.directory, f.workspace, f.options);
  assert.deepEqual(result.uploaded.files, result.downloaded.files);
  assert.equal(result.downloaded.archiveSha256, f.primary.archiveSha256);
  assert.equal(f.operations.filter(name => name === 'GetObjectCommand').length, 4);
  assert.equal(await fs.readFile(f.primaryPath, 'utf8'), JSON.stringify(f.primary));
  for (const [name, bytes] of f.bytesByName) {
    assert.deepEqual(await fs.readFile(path.join(f.workspace, 'download', name)), bytes);
  }
});

test('refuses the primary endpoint and changed local backup before network operations', async t => {
  const f = await fixture(t);
  await assert.rejects(mirrorBackup(f.directory, f.workspace,
    {...f.options, config: {...config, endpoint: sourceConfig.endpoint}}), /Independent COS target/);
  f.primary.files[1].sha256 = '0'.repeat(64);
  await fs.writeFile(f.primaryPath, JSON.stringify(f.primary));
  await assert.rejects(mirrorBackup(f.directory, f.workspace, f.options), /differs from the primary/);
  assert.equal(f.operations.length, 0);
});

test('refuses unencrypted COS objects and changes between upload and download', async t => {
  // An existing COS object can be versioned while lacking the configured encryption.
  const broken = await fixture(t, {encryption: null});
  await assert.rejects(mirrorBackup(broken.directory, broken.workspace, broken.options), /lacks versioning or AES256/);
  const changed = await fixture(t, {changedVersion: true});
  await assert.rejects(mirrorBackup(changed.directory, changed.workspace, changed.options), /object version changed/);
});
