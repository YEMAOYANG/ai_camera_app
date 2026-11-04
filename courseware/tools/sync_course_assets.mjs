#!/usr/bin/env node
/**
 * Upload immutable courseware resources to MinIO, read every object back, and
 * atomically publish the allowlist consumed by the backend.  Local sources are
 * retained as recovery copies. Staged objects can be retired only by exact
 * manifest entries after a complete formal publication archive proves the
 * same bytes are registered; no prefix deletion is supported.
 */
import crypto from "node:crypto";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

import { ROOT, readConfig } from "../../openmaic-runtime/scripts/course-storage.mjs";

const require = createRequire(path.join(ROOT, "openmaic-runtime/.runtime/OpenMAIC/package.json"));
const { S3Client, HeadObjectCommand, PutObjectCommand, GetObjectCommand,
  DeleteObjectCommand } = require("@aws-sdk/client-s3");

export const SCHEMA = "mira.courseware-assets.v1";
export const MAX_ASSET_BYTES = 32 * 1024 * 1024;
const MAX_FILES = 4096;
const MIME = new Map([
  [".aac", "audio/aac"], [".flac", "audio/flac"], [".mp3", "audio/mpeg"],
  [".ogg", "audio/ogg"], [".wav", "audio/wav"], [".webm", "video/webm"],
  [".gif", "image/gif"], [".jpeg", "image/jpeg"], [".jpg", "image/jpeg"],
  [".png", "image/png"], [".webp", "image/webp"], [".mp4", "video/mp4"],
  [".glb", "model/gltf-binary"], [".json", "application/json"],
]);

const sha256 = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
const storageIdentity = config => ({ endpoint: new URL(config.endpoint).origin,
  bucket: config.bucket, region: config.region });

function safeRelative(value) {
  if (typeof value !== "string" || !value || value.includes("\\") || value.includes("\0")
      || path.posix.isAbsolute(value) || value.split("/").some(part => !part || part === "." || part === "..")
      || Buffer.byteLength(value) > 1024) throw Error("Invalid courseware asset path");
  const resolved = path.resolve(ROOT, value);
  if (!resolved.startsWith(ROOT + path.sep)) throw Error("Courseware asset escapes the project");
  return value;
}

function safeKeyPart(value) {
  if (!value || value === "." || value === ".." || Buffer.byteLength(value) > 255
      || /[\\\x00-\x1f\x7f]/.test(value)) throw Error("Invalid courseware object key");
  return value;
}

export function objectKeyFor(sourcePath, checksum) {
  safeRelative(sourcePath);
  if (!/^[a-f0-9]{64}$/.test(checksum)) throw Error("Invalid courseware asset digest");
  const parts = sourcePath.split("/");
  const basename = safeKeyPart(parts.at(-1));
  const immutableName = `${checksum.slice(0, 16)}-${basename}`;
  let keyParts;
  if (sourcePath.startsWith("student-web/public/")) {
    keyParts = ["课件资源", "v1", "学生端", ...parts.slice(2, -1), immutableName];
  } else {
    const match = sourcePath.match(/^output\/courseware-lessons\/([^/]+)\/([^/]+)\/media\/([^/]+)$/);
    if (!match) throw Error("Unsupported courseware asset source");
    keyParts = ["课件资源", "v1", "待上架课件", match[1], match[2], immutableName];
  }
  keyParts.forEach(safeKeyPart);
  const key = keyParts.join("/");
  if (Buffer.byteLength(key) > 1024) throw Error("Courseware object key is too long");
  return key;
}

function parseArgs(argv) {
  const result = { command: argv.shift(), include: [], publication: [], concurrency: 8 };
  while (argv.length) {
    const option = argv.shift();
    if (!option?.startsWith("--") || !argv.length) throw Error("Expected named option and value");
    const value = argv.shift();
    if (option === "--include") result.include.push(value);
    else if (option === "--manifest") result.manifest = value;
    else if (option === "--snapshot") result.snapshot = value;
    else if (option === "--next-snapshot") result.nextSnapshot = value;
    else if (option === "--publication") result.publication.push(value);
    else if (option === "--concurrency") result.concurrency = Number(value);
    else throw Error(`Unknown option ${option}`);
  }
  const retirement = ["plan-retire-staged", "retire-staged"].includes(result.command);
  if (!["sync", "verify", "plan-retire-staged", "retire-staged"].includes(result.command) || !result.manifest
      || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(result.snapshot || "")
      || !Number.isInteger(result.concurrency) || result.concurrency < 1 || result.concurrency > 16
      || (result.command === "sync" && !result.include.length)
      || (retirement && (!result.publication.length || result.include.length
          || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(result.nextSnapshot || "")
          || result.nextSnapshot === result.snapshot))
      || (!retirement && (result.publication.length || result.nextSnapshot)))
    throw Error("Invalid courseware sync arguments");
  result.manifest = safeRelative(result.manifest);
  result.include = result.include.map(safeRelative);
  result.publication = result.publication.map(value => {
    const separator = value.indexOf("=");
    const scope = value.slice(0, separator);
    const job = value.slice(separator + 1);
    if (separator < 1 || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}\/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(scope))
      throw Error("Invalid staged publication scope");
    return { scope, job: safeRelative(job) };
  });
  return result;
}

async function stableBytes(relative) {
  const absolute = path.join(ROOT, relative);
  const before = await fsp.lstat(absolute, { bigint: true });
  if (!before.isFile() || before.isSymbolicLink() || before.size <= 0n || before.size > BigInt(MAX_ASSET_BYTES))
    throw Error("Courseware asset must be a bounded regular file");
  const bytes = await fsp.readFile(absolute);
  const after = await fsp.lstat(absolute, { bigint: true });
  for (const field of ["dev", "ino", "size", "mtimeNs", "ctimeNs"])
    if (before[field] !== after[field]) throw Error("Courseware asset changed during inventory");
  return bytes;
}

async function includedFiles(relative) {
  const absolute = path.join(ROOT, relative);
  const stat = await fsp.lstat(absolute);
  if (stat.isSymbolicLink()) throw Error("Courseware asset symlinks are not allowed");
  if (stat.isFile()) return [relative];
  if (!stat.isDirectory()) throw Error("Courseware include is not a file or directory");
  const result = [];
  const visit = async (directory, prefix) => {
    for (const item of await fsp.readdir(directory, { withFileTypes: true })) {
      if (item.isSymbolicLink()) throw Error("Courseware asset symlinks are not allowed");
      const child = path.join(directory, item.name);
      const source = path.posix.join(prefix, item.name);
      if (item.isDirectory()) await visit(child, source);
      else if (item.isFile()) result.push(source);
      else throw Error("Unsupported courseware asset entry");
    }
  };
  await visit(absolute, relative);
  return result;
}

async function inventory(includes) {
  const sources = [...new Set((await Promise.all(includes.map(includedFiles))).flat())].sort();
  if (!sources.length || sources.length > MAX_FILES) throw Error("Courseware asset inventory size is invalid");
  const files = [];
  for (const sourcePath of sources) {
    const mimeType = MIME.get(path.extname(sourcePath).toLowerCase());
    if (!mimeType) throw Error(`Unsupported courseware asset type: ${sourcePath}`);
    const bytes = await stableBytes(sourcePath);
    const checksum = sha256(bytes);
    files.push({ sourcePath, ...(sourcePath.startsWith("student-web/public/")
      ? { publicPath: "/" + sourcePath.slice("student-web/public/".length) } : {}),
      objectKey: objectKeyFor(sourcePath, checksum), sha256: checksum,
      byteSize: bytes.length, mimeType });
  }
  return files;
}

function clientFor(config) {
  return new S3Client({ endpoint: config.endpoint, region: config.region, forcePathStyle: true,
    credentials: { accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey },
    maxAttempts: 3, requestChecksumCalculation: "WHEN_REQUIRED", responseChecksumValidation: "WHEN_REQUIRED" });
}

async function readRemote(client, config, entry, expected = undefined) {
  const response = await client.send(new GetObjectCommand({ Bucket: config.bucket, Key: entry.objectKey,
    ...(expected?.etag ? { IfMatch: expected.etag } : {}), ...(expected?.versionId ? { VersionId: expected.versionId } : {}) }));
  let count = 0;
  const hash = crypto.createHash("sha256");
  for await (const part of response.Body) {
    count += part.length;
    if (count > entry.byteSize) throw Error("Remote courseware asset is oversized");
    hash.update(part);
  }
  if (count !== entry.byteSize || hash.digest("hex") !== entry.sha256
      || typeof response.ETag !== "string" || !response.ETag
      || (expected?.etag && response.ETag !== expected.etag)
      || (expected?.versionId && response.VersionId !== expected.versionId))
    throw Error("Remote courseware asset verification failed");
  return { etag: response.ETag, ...(response.VersionId ? { versionId: response.VersionId } : {}) };
}

async function parallel(items, concurrency, operation) {
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(items.length, concurrency) }, async () => {
    for (;;) {
      const index = cursor++;
      if (index >= items.length) return;
      await operation(items[index], index);
    }
  }));
}

async function sync(config, files, concurrency) {
  const client = clientFor(config);
  const verified = new Array(files.length);
  await parallel(files, concurrency, async (entry, index) => {
    let existing;
    try { existing = await client.send(new HeadObjectCommand({ Bucket: config.bucket, Key: entry.objectKey })); }
    catch (error) { if (error?.$metadata?.httpStatusCode !== 404) throw error; }
    let immutable;
    if (existing) {
      if (Number(existing.ContentLength) !== entry.byteSize || existing.Metadata?.sha256 !== entry.sha256)
        throw Error("Existing courseware object differs from the immutable source");
      immutable = { etag: existing.ETag, ...(existing.VersionId ? { versionId: existing.VersionId } : {}) };
    } else {
      const bytes = await stableBytes(entry.sourcePath);
      if (bytes.length !== entry.byteSize || sha256(bytes) !== entry.sha256)
        throw Error("Courseware asset changed after inventory");
      const saved = await client.send(new PutObjectCommand({ Bucket: config.bucket, Key: entry.objectKey,
        Body: bytes, ContentLength: bytes.length, ContentType: entry.mimeType,
        Metadata: { sha256: entry.sha256 }, ChecksumSHA256: Buffer.from(entry.sha256, "hex").toString("base64"),
        IfNoneMatch: "*" }));
      immutable = { etag: saved.ETag, ...(saved.VersionId ? { versionId: saved.VersionId } : {}) };
    }
    if (typeof immutable.etag !== "string" || !immutable.etag) throw Error("Courseware object identity is missing");
    await readRemote(client, config, entry, immutable);
    verified[index] = { ...entry, ...immutable };
  });
  return verified;
}

async function verify(config, manifest, concurrency) {
  const client = clientFor(config);
  await parallel(manifest.files, concurrency, entry => readRemote(client, config, entry, entry));
  return manifest.files;
}

const fileIdentity = entry => `${entry.sha256}:${entry.byteSize}:${entry.mimeType}`;

export function stagedScope(entry) {
  if (!entry || typeof entry.objectKey !== "string") return null;
  const match = entry.objectKey.match(/^课件资源\/v1\/待上架课件\/([^/]+)\/([^/]+)\/[^/]+$/u);
  if (!match) return null;
  safeKeyPart(match[1]);
  safeKeyPart(match[2]);
  return `${match[1]}/${match[2]}`;
}

function projectFile(value, requiredPrefix) {
  if (typeof value !== "string" || !path.isAbsolute(value))
    throw Error("Publication proof path is invalid");
  const absolute = path.resolve(value);
  const prefix = path.join(ROOT, requiredPrefix) + path.sep;
  if (!absolute.startsWith(prefix)) throw Error("Publication proof escapes its managed directory");
  return absolute;
}

async function regularJson(absolute) {
  const stat = await fsp.lstat(absolute);
  if (!stat.isFile() || stat.isSymbolicLink()) throw Error("Publication proof must be a regular file");
  return JSON.parse(await fsp.readFile(absolute, "utf8"));
}

async function publicationProof(specification) {
  const jobPath = path.join(ROOT, specification.job);
  const job = await regularJson(jobPath);
  if (job.status !== "complete" || job.lastError != null
      || job.identity?.sourceKind !== "textbook_release"
      || typeof job.identity?.courseId !== "string"
      || typeof job.identity?.sourceDigest !== "string")
    throw Error("Formal publication archive is not complete");
  const receiptPath = projectFile(job.receiptPath, "backend/data/course-storage/archive-transfers");
  const retainedPath = projectFile(job.retainedManifestPath, "backend/data/course-storage/archives");
  const receiptBytes = await fsp.readFile(receiptPath);
  if (!/^[a-f0-9]{64}$/.test(job.receiptSha256 || "") || sha256(receiptBytes) !== job.receiptSha256)
    throw Error("Formal publication receipt digest differs");
  const formal = await regularJson(retainedPath);
  if (formal.schemaVersion !== "mira.course-archive.export.v1" || formal.complete !== true
      || formal.missing != null || !Array.isArray(formal.files) || !formal.files.length
      || !/^tbpub_[a-f0-9]{24}$/.test(formal.identity?.classroomId || "")
      || !/^[a-f0-9]{64}$/.test(formal.identity?.contentKey || "")
      || formal.identity?.courseId !== job.identity.courseId
      || formal.identity?.releaseSha256 !== job.identity.sourceDigest)
    throw Error("Formal publication manifest is not registered and complete");
  const media = new Set(formal.files.filter(file => typeof file.archivePath === "string"
    && file.archivePath.startsWith("媒体/") && file.sourceKind === "referenced_media").map(fileIdentity));
  if (!media.size) throw Error("Formal publication archive has no referenced media");
  return { scope: specification.scope, classroomId: formal.identity.classroomId,
    contentKey: formal.identity.contentKey, media };
}

export function retirementPlan(manifest, publications) {
  if (!manifest || !Array.isArray(manifest.files) || !Array.isArray(publications)
      || !publications.length) throw Error("Courseware retirement inputs are invalid");
  const byScope = new Map();
  for (const publication of publications) {
    if (!publication || typeof publication.scope !== "string" || !(publication.media instanceof Set)
        || byScope.has(publication.scope)) throw Error("Publication scopes must be unique");
    byScope.set(publication.scope, publication);
  }
  const retiring = [];
  const retained = [];
  for (const entry of manifest.files) {
    const scope = stagedScope(entry);
    if (!scope || !byScope.has(scope)) {
      retained.push(entry);
      continue;
    }
    if (entry.versionId) throw Error("Versioned staged objects need a separate retirement workflow");
    if (!byScope.get(scope).media.has(fileIdentity(entry)))
      throw Error(`Staged object is absent from its formal publication archive: ${entry.objectKey}`);
    retiring.push(entry);
  }
  for (const scope of byScope.keys()) {
    if (!retiring.some(entry => stagedScope(entry) === scope))
      throw Error(`No staged objects match publication scope ${scope}`);
  }
  return { retiring, retained, scopes: [...byScope.keys()].sort(),
    classrooms: publications.map(value => value.classroomId).sort() };
}

const missingRemote = error => error?.$metadata?.httpStatusCode === 404
  || error?.name === "NoSuchKey" || error?.name === "NotFound";

async function remoteState(client, config, entry) {
  try {
    await readRemote(client, config, entry, entry);
    return "present";
  } catch (error) {
    if (missingRemote(error)) return "missing";
    throw error;
  }
}

async function planRetirement(config, plan, concurrency, allowMissing) {
  const client = clientFor(config);
  let missing = 0;
  await parallel(plan.retiring, concurrency, async entry => {
    const state = await remoteState(client, config, entry);
    if (state === "missing") {
      missing += 1;
      if (!allowMissing) throw Error(`Staged object is already missing: ${entry.objectKey}`);
    }
  });
  return { client, missing };
}

async function retire(config, plan, concurrency) {
  const { client, missing } = await planRetirement(config, plan, concurrency, true);
  let deleted = 0;
  await parallel(plan.retiring, concurrency, async entry => {
    let head;
    try { head = await client.send(new HeadObjectCommand({ Bucket: config.bucket, Key: entry.objectKey })); }
    catch (error) { if (!missingRemote(error)) throw error; }
    if (head) {
      if (Number(head.ContentLength) !== entry.byteSize || head.Metadata?.sha256 !== entry.sha256
          || (entry.etag && head.ETag !== entry.etag))
        throw Error("Staged object changed before retirement");
      await client.send(new DeleteObjectCommand({ Bucket: config.bucket, Key: entry.objectKey }));
      deleted += 1;
    }
    try {
      await client.send(new HeadObjectCommand({ Bucket: config.bucket, Key: entry.objectKey }));
      throw Error("Staged object still exists after retirement");
    } catch (error) {
      if (!missingRemote(error)) throw error;
    }
  });
  return { deleted, alreadyMissing: missing };
}

async function atomicJson(relative, value) {
  const target = path.join(ROOT, relative);
  await fsp.mkdir(path.dirname(target), { recursive: true });
  const temporary = `${target}.new-${process.pid}`;
  const handle = await fsp.open(temporary, "wx", 0o600);
  try { await handle.writeFile(JSON.stringify(value, null, 2) + "\n"); await handle.sync(); }
  finally { await handle.close(); }
  await fsp.rename(temporary, target);
}

export async function run(options) {
  const config = readConfig();
  const storage = storageIdentity(config);
  if (options.command === "verify") {
    const manifest = JSON.parse(await fsp.readFile(path.join(ROOT, options.manifest), "utf8"));
    if (manifest.schemaVersion !== SCHEMA || JSON.stringify(manifest.storage) !== JSON.stringify(storage)
        || !Array.isArray(manifest.files) || !manifest.files.length || manifest.snapshotId !== options.snapshot)
      throw Error("Courseware manifest does not match the requested storage and snapshot");
    await verify(config, manifest, options.concurrency);
    return { verified: true, files: manifest.files.length,
      bytes: manifest.files.reduce((sum, file) => sum + file.byteSize, 0) };
  }
  if (["plan-retire-staged", "retire-staged"].includes(options.command)) {
    const manifest = JSON.parse(await fsp.readFile(path.join(ROOT, options.manifest), "utf8"));
    if (manifest.schemaVersion !== SCHEMA || JSON.stringify(manifest.storage) !== JSON.stringify(storage)
        || !Array.isArray(manifest.files) || !manifest.files.length || manifest.snapshotId !== options.snapshot)
      throw Error("Courseware manifest does not match the requested storage and snapshot");
    const publications = await Promise.all(options.publication.map(publicationProof));
    const plan = retirementPlan(manifest, publications);
    const bytes = plan.retiring.reduce((sum, file) => sum + file.byteSize, 0);
    if (options.command === "plan-retire-staged") {
      await planRetirement(config, plan, options.concurrency, false);
      return { planned: true, files: plan.retiring.length, bytes, scopes: plan.scopes,
        classrooms: plan.classrooms, retainedFiles: plan.retained.length };
    }
    const result = await retire(config, plan, options.concurrency);
    await atomicJson(options.manifest, { ...manifest, snapshotId: options.nextSnapshot,
      createdAt: new Date().toISOString(), files: plan.retained });
    return { retired: true, files: plan.retiring.length, bytes, scopes: plan.scopes,
      classrooms: plan.classrooms, retainedFiles: plan.retained.length, ...result };
  }
  const files = await inventory(options.include);
  const uploaded = await sync(config, files, options.concurrency);
  const manifest = { schemaVersion: SCHEMA, snapshotId: options.snapshot,
    createdAt: new Date().toISOString(), storage, files: uploaded };
  await atomicJson(options.manifest, manifest);
  return { synced: true, files: uploaded.length,
    publicFiles: uploaded.filter(file => file.publicPath).length,
    bytes: uploaded.reduce((sum, file) => sum + file.byteSize, 0) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  Promise.resolve().then(() => run(parseArgs(process.argv.slice(2))))
    .then(result => process.stdout.write(JSON.stringify(result) + "\n"))
    .catch(error => { process.stderr.write(JSON.stringify({ error: String(error?.message || error) }) + "\n"); process.exitCode = 1; });
}
