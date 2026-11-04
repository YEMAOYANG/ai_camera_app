import assert from "node:assert/strict";
import test from "node:test";

import { objectKeyFor, retirementPlan, stagedScope } from "./sync_course_assets.mjs";

const digest = "a".repeat(64);

test("student courseware resources receive immutable readable MinIO keys", () => {
  assert.equal(
    objectKeyFor("student-web/public/textbooks/navigation-v1/subjects.png", digest),
    `课件资源/v1/学生端/textbooks/navigation-v1/${digest.slice(0, 16)}-subjects.png`,
  );
});

test("generated lesson media stay grouped by lesson and build", () => {
  assert.equal(
    objectKeyFor("output/courseware-lessons/math-six/build3/media/pic-a.png", digest),
    `课件资源/v1/待上架课件/math-six/build3/${digest.slice(0, 16)}-pic-a.png`,
  );
});

test("unrelated frontend files and traversal are rejected", () => {
  assert.throws(() => objectKeyFor("student-web/public/images/logo.png", "bad"));
  assert.throws(() => objectKeyFor("../secret.png", digest));
  assert.throws(() => objectKeyFor("backend/private/site.png", digest));
});

test("only exact lesson and build staging keys have a retirement scope", () => {
  assert.equal(stagedScope({ objectKey: "课件资源/v1/待上架课件/math-six/build3/file.png" }),
    "math-six/build3");
  assert.equal(stagedScope({ objectKey: "课件资源/v1/学生端/textbooks/file.png" }), null);
  assert.equal(stagedScope({ objectKey: "课件资源/v1/待上架课件/math-six/file.png" }), null);
});

test("retirement needs formal byte proof and retains student assets", () => {
  const staged = { objectKey: "课件资源/v1/待上架课件/math-six/build3/file.png",
    sha256: digest, byteSize: 12, mimeType: "image/png" };
  const student = { objectKey: "课件资源/v1/学生端/textbooks/file.png",
    sha256: "b".repeat(64), byteSize: 20, mimeType: "image/png" };
  const publication = { scope: "math-six/build3", classroomId: "tbpub_" + "c".repeat(24),
    media: new Set([`${digest}:12:image/png`]) };
  const plan = retirementPlan({ files: [staged, student] }, [publication]);
  assert.deepEqual(plan.retiring, [staged]);
  assert.deepEqual(plan.retained, [student]);
  assert.throws(() => retirementPlan({ files: [staged, student] }, [
    { ...publication, media: new Set([`${digest}:13:image/png`]) },
  ]), /absent from its formal publication archive/);
});

test("retirement rejects broad or unmatched publication scopes", () => {
  const staged = { objectKey: "课件资源/v1/待上架课件/math-six/build3/file.png",
    sha256: digest, byteSize: 12, mimeType: "image/png" };
  assert.throws(() => retirementPlan({ files: [staged] }, [
    { scope: "other/build3", classroomId: "tbpub_" + "c".repeat(24), media: new Set() },
  ]), /No staged objects match/);
});
