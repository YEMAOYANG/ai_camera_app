import assert from "node:assert/strict";
import test from "node:test";

import { objectKeyFor } from "./sync_course_assets.mjs";

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
