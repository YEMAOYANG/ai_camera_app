#!/usr/bin/env node
/** Store and fetch verified course source backups. Never deletes source or cloud data. */
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {ROOT, readConfig, clientFor} from '../../openmaic-runtime/scripts/course-storage.mjs';

const require = createRequire(path.join(ROOT, 'openmaic-runtime/.runtime/OpenMAIC/package.json'));
const {HeadObjectCommand, PutObjectCommand, GetObjectCommand} = require('@aws-sdk/client-s3');
const run = promisify(execFile);
const SCHEMA = 'mira.courseware-backup.remote.v1';
const LIMIT = 5 * 1024 ** 3;
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const identity = c => ({endpoint: new URL(c.endpoint).origin, bucket: c.bucket, region: c.region});
const absent = e => e?.$metadata?.httpStatusCode === 404 || ['NotFound', 'NoSuchKey'].includes(e?.name);
const validHash = x => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
const allowedPath = p => typeof p === 'string' && !/[\\\x00-\x1f\x7f]/.test(p)
  && !path.posix.isAbsolute(p) && p.split('/').every(x => x && x !== '.' && x !== '..')
  && (['courseware-sources.zip', 'backup-receipt.json'].includes(p)
      || /^existing-archives\/output\/course-data-snapshots\/[^/]+\/[^/]+\.tar\.gz$/.test(p));

async function noLinks(filename) {
  const absolute = path.resolve(filename);
  let current = path.parse(absolute).root;
  for (const part of absolute.slice(current.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    const stat = await fsp.lstat(current);
    if (stat.isSymbolicLink()) throw Error('Backup path contains a symbolic link');
  }
  return absolute;
}

async function fileHash(filename) {
  await noLinks(filename);
  const before = await fsp.lstat(filename, {bigint: true});
  if (!before.isFile() || before.size > BigInt(LIMIT)) throw Error('Backup file is invalid or exceeds 5 GiB');
  const checksum = crypto.createHash('sha256');
  for await (const chunk of fs.createReadStream(filename, {flags: fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW})) checksum.update(chunk);
  const after = await fsp.lstat(filename, {bigint: true});
  if (['ino', 'dev', 'size', 'mtimeNs', 'ctimeNs'].some(k => before[k] !== after[k])) throw Error('Backup file changed');
  return {sha256: checksum.digest('hex'), byteSize: Number(before.size)};
}

async function readBackup(directory, {remoteExport = false} = {}) {
  await noLinks(directory);
  // Use the existing, tested stdlib verifier; do not execute code from the ZIP.
  const script = 'import json,sys;sys.path.insert(0,sys.argv[1]);import courseware_backup as b;'
    + 'from pathlib import Path;p=Path(sys.argv[2]);i=b.verify_backup(p/b.ARCHIVE_NAME,remote_export=sys.argv[3]=="1");'
    + 'print(json.dumps({"paths":[b.ARCHIVE_NAME,"backup-receipt.json"]+[x["backupPath"] for x in i["sidecars"]]}))';
  const {stdout} = await run('python3', ['-B', '-c', script, path.join(ROOT, 'tools'), directory, remoteExport ? '1' : '0'], {maxBuffer: 4 * 1024 ** 2});
  const files = [];
  for (const relative of JSON.parse(stdout).paths) {
    if (!allowedPath(relative)) throw Error('Unexpected backup member');
    files.push({path: relative, ...await fileHash(path.join(directory, relative))});
  }
  return files;
}

export function validateReceipt(receipt) {
  if (receipt?.schemaVersion !== SCHEMA || !validHash(receipt.archiveSha256)
      || !Array.isArray(receipt.files) || receipt.files.length < 2 || receipt.files.length > 1000) throw Error('Invalid backup receipt');
  const paths = new Set();
  const prefix = `备份/课件恢复/v1/${receipt.archiveSha256}/`;
  for (const f of receipt.files) {
    if (!allowedPath(f.path) || paths.has(f.path) || f.objectKey !== prefix + f.path
        || !validHash(f.sha256) || !Number.isSafeInteger(f.byteSize) || f.byteSize < 1 || f.byteSize > LIMIT) throw Error('Invalid backup file identity');
    paths.add(f.path);
  }
  if (!paths.has('courseware-sources.zip') || !paths.has('backup-receipt.json')
      || receipt.files.find(f => f.path === 'courseware-sources.zip').sha256 !== receipt.archiveSha256) throw Error('Incomplete backup receipt');
  return receipt;
}

async function head(client, config, key) {
  try { return await client.send(new HeadObjectCommand({Bucket: config.bucket, Key: key})); }
  catch (e) { if (absent(e)) return null; throw e; }
}

export async function verifyObject(client, config, file, remote, output) {
  if (!remote?.ETag || remote.ContentLength !== file.byteSize) throw Error('Remote backup identity mismatch');
  const result = await client.send(new GetObjectCommand({Bucket: config.bucket, Key: file.objectKey,
    IfMatch: remote.ETag, ...(remote.VersionId ? {VersionId: remote.VersionId} : {})}));
  let size = 0;
  const checksum = crypto.createHash('sha256');
  try {
    if (result.ETag !== remote.ETag || result.ContentLength !== file.byteSize
        || (remote.VersionId && result.VersionId !== remote.VersionId)) throw Error('Remote backup changed');
    for await (const chunk of result.Body) {
      size += chunk.length;
      if (size > file.byteSize) throw Error('Remote backup exceeds expected size');
      checksum.update(chunk);
      if (output) await output(chunk);
    }
    if (size !== file.byteSize || checksum.digest('hex') !== file.sha256) throw Error('Remote backup SHA-256 mismatch');
  } finally { result.Body?.destroy?.(); }
  return {...file, etag: remote.ETag, ...(remote.VersionId ? {versionId: remote.VersionId} : {})};
}

async function writeReceipt(directory, receipt) {
  const temp = path.join(directory, `.remote-verification-${crypto.randomUUID()}.tmp`);
  await fsp.writeFile(temp, JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  await fsp.rename(temp, path.join(directory, 'remote-verification.json'));
}

export async function uploadBackup(directory, dependencies = {}) {
  directory = await noLinks(directory);
  const lock = await fsp.open(path.join(directory, '.upload.lock'), 'wx', 0o600);
  try {
    const files = await (dependencies.readBackup || readBackup)(directory, {remoteExport: true});
    const archive = files.find(f => f.path === 'courseware-sources.zip');
    const prefix = `备份/课件恢复/v1/${archive?.sha256}/`;
    const receipt = validateReceipt({schemaVersion: SCHEMA, archiveSha256: archive?.sha256,
      files: files.map(f => ({...f, objectKey: prefix + f.path}))});
    const config = dependencies.config || readConfig();
    const client = dependencies.client || clientFor(config, {maxAttempts: 1});
    const verified = [];
    for (const file of receipt.files) {
      const filename = path.join(directory, file.path);
      const local = await fileHash(filename);
      if (local.sha256 !== file.sha256 || local.byteSize !== file.byteSize) throw Error('Backup source changed');
      let remote = await head(client, config, file.objectKey);
      if (!remote) {
        const body = fs.createReadStream(filename, {flags: fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW});
        try {
          await client.send(new PutObjectCommand({Bucket: config.bucket, Key: file.objectKey, Body: body,
            ContentLength: file.byteSize, IfNoneMatch: '*', Metadata: {sha256: file.sha256},
            ContentType: file.path.endsWith('.json') ? 'application/json' : file.path.endsWith('.gz') ? 'application/gzip' : 'application/zip',
            ...(config.provider === 'tencent-cos' ? {ServerSideEncryption: 'AES256'} : {})}));
        } finally { body.destroy(); }
        remote = await head(client, config, file.objectKey);
      }
      verified.push(await verifyObject(client, config, file, remote));
    }
    const result = {...receipt, files: verified, storage: identity(config), verifiedAt: new Date().toISOString(),
      complete: true, localSourcesRetained: true};
    await writeReceipt(directory, result);
    return result;
  } finally { await lock.close(); await fsp.unlink(path.join(directory, '.upload.lock')); }
}

export async function fetchBackup(receipt, destination, dependencies = {}) {
  validateReceipt(receipt);
  destination = path.resolve(destination);
  await noLinks(path.dirname(destination));
  // Exclusive creation prevents an existing recovery tree from being overwritten.
  await fsp.mkdir(destination, {mode: 0o700});
  const config = dependencies.config || readConfig();
  const client = dependencies.client || clientFor(config, {maxAttempts: 1});
  const files = [];
  for (const file of receipt.files) {
    const remote = await head(client, config, file.objectKey);
    const filename = path.join(destination, file.path);
    await fsp.mkdir(path.dirname(filename), {recursive: true, mode: 0o700});
    await noLinks(path.dirname(filename));
    const handle = await fsp.open(filename, 'wx', 0o600);
    try {
      files.push(await verifyObject(client, config, file, remote, async chunk => {
        let offset = 0;
        while (offset < chunk.length) offset += (await handle.write(chunk, offset, chunk.length - offset)).bytesWritten;
      }));
      await handle.sync();
    } finally { await handle.close(); }
  }
  await (dependencies.readBackup || readBackup)(destination);
  const result = {...receipt, files, storage: identity(config), verifiedAt: new Date().toISOString(), complete: true};
  await writeReceipt(destination, result);
  return result;
}

async function main(argv) {
  const command = argv.shift(), options = {};
  while (argv.length) {
    const name = argv.shift(), value = argv.shift();
    if (!['--backup', '--receipt', '--destination'].includes(name) || !value || options[name]) throw Error('Invalid backup options');
    options[name] = value;
  }
  const config = readConfig();
  let result;
  if (command === 'upload' && Object.keys(options).join() === '--backup') result = await uploadBackup(options['--backup'], {config});
  else if (command === 'fetch' && Object.keys(options).length === 2 && options['--receipt'] && options['--destination']) {
    await noLinks(options['--receipt']);
    result = await fetchBackup(JSON.parse(await fsp.readFile(options['--receipt'], 'utf8')), options['--destination'], {config});
  } else throw Error('Use upload --backup DIR or fetch --receipt FILE --destination NEW_DIR');
  console.log(JSON.stringify({complete: result.complete, storage: result.storage, files: result.files.length,
    bytes: result.files.reduce((n, f) => n + f.byteSize, 0), archiveSha256: result.archiveSha256}));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch(e => { console.error(JSON.stringify({error: 'course_backup_failed', reason: e.name})); process.exitCode = 1; });
}
