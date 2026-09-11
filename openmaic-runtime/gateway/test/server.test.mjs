import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import http from "node:http";
import { afterEach, test } from "node:test";
import { gzipSync } from "node:zlib";

import {
  authorizeRuntimeRequest,
  createGateway,
  injectRuntimeAudioBindings,
  mergeContentSecurityPolicy,
  prepareRuntimeEvent,
  sanitizeRuntimeJson,
} from "../src/server.mjs";

const servers = [];
const legacyBrandAssetPaths = [
  "/logo-horizontal.png",
  "/openmaic-mark.png",
  "/openmaic-favicon.ico",
  "/openmaic-apple-icon.png",
];

test("production gateway rejects insecure public origins", () => {
  const productionConfig = {
    backendUrl: "http://backend:8000",
    upstreamUrl: "http://openmaic:3000",
    publicOrigin: "https://classroom.example.com",
    studentWebOrigin: "https://learn.example.com",
    internalToken: "test-internal-token",
    secureCookie: true,
  };

  assert.throws(
    () =>
      createGateway({
        ...productionConfig,
        publicOrigin: "http://classroom.example.com",
      }),
    /MIRA_RUNTIME_PUBLIC_ORIGIN must use HTTPS in production/,
  );
  assert.throws(
    () =>
      createGateway({
        ...productionConfig,
        studentWebOrigin: "http://learn.example.com",
      }),
    /MIRA_STUDENT_WEB_ORIGIN must use HTTPS in production/,
  );

  const server = createGateway(productionConfig);
  assert.equal(server.listening, false);
});

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map((server) => new Promise((resolve) => server.close(() => resolve()))),
  );
});

test("one-time Mira ticket becomes a private classroom cookie", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      assert.equal(request.headers["x-mira-internal-token"], "test-internal-token");
      if (request.url === "/internal/learning/openmaic/runtime/exchange") {
        assert.equal(body.ticket, "omt_abcdefghijklmnopqrstuvwxyz012345");
        return reply(response, {
          ok: true,
          runtimeToken: "omr_runtime-token-abcdefghijklmnopqrstuvwxyz",
          expiresAt: Date.now() + 60_000,
          classroomId: "classroom-a",
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        assert.equal(body.runtimeToken, "omr_runtime-token-abcdefghijklmnopqrstuvwxyz");
        return reply(response, {
          ok: true,
          runtimeSessionId: "runtime-session-a",
          learningSessionId: "learning-session-a",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(404).end();
    }),
  );
  const upstream = await listen(
    http.createServer((request, response) => {
      if (request.url === "/classroom/classroom-a?mira=1") {
        response.setHeader("content-type", "text/html");
        response.end("<main>full interactive classroom</main>");
        return;
      }
      response.writeHead(404).end();
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const launch = await fetch(`${gateway}/mira/launch?ticket=omt_abcdefghijklmnopqrstuvwxyz012345`, {
    redirect: "manual",
  });
  assert.equal(launch.status, 303);
  assert.equal(launch.headers.get("location"), "/classroom/classroom-a?mira=1");
  const cookie = launch.headers.get("set-cookie");
  assert.match(cookie, /mira_openmaic_runtime=/);
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /SameSite=Lax/);
  assert.doesNotMatch(cookie, /Domain=/);
  assert.doesNotMatch(cookie, /Secure/);

  const classroom = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
    headers: { cookie: cookie.split(";", 1)[0] },
  });
  assert.equal(classroom.status, 200);
  const classroomHtml = await classroom.text();
  assert.match(classroomHtml, /full interactive classroom/);
  assert.doesNotMatch(classroomHtml, /open\s*maic/i);
  assert.match(
    classroom.headers.get("content-security-policy"),
    /frame-ancestors http:\/\/student\.test/,
  );
});

test("runtime events are session-bound by the gateway and never accept client identity or score", async () => {
  let eventCalls = 0;
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "runtime-session-a",
          learningSessionId: "learning-session-a",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/events") {
        if (request.method === "GET") {
          assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
          assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
          assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
          return reply(response, {
            ok: true,
            schemaVersion: "mira.openmaic.student-runtime-event-receipt.v1",
            lastSequence: 1,
            nextSequence: 2,
            completed: false,
            reportId: null,
            internal: { auditId: "must-not-leak" },
          });
        }
        eventCalls += 1;
        assert.equal(request.headers["x-mira-internal-source"], "openmaic-runtime-gateway");
        assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
        assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
        assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
        assert.deepEqual(body, {
          schemaVersion: "mira.openmaic.student-runtime-event.v1",
          sequence: 1,
          type: "scene_entered",
          payload: { sceneIndex: 0, sceneId: "scene-0" },
          idempotencyKey: "e1192a0665ee09e24c776dc68ef8ba2b722d5faab1b8b7411513a512c55595a0",
        });
        return reply(response, {
          ok: true,
          schemaVersion: "mira.openmaic.student-runtime-event-receipt.v1",
          sequence: 1,
          receiptSha256: "a".repeat(64),
          internal: { auditId: "must-not-leak" },
        });
      }
      response.writeHead(404).end();
    }),
  );
  const upstream = await listen(
    http.createServer((_request, response) => {
      response.writeHead(500).end("runtime events must not reach upstream");
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = {
    cookie: "mira_openmaic_runtime=omr_good",
    "content-type": "application/json",
  };

  const accepted = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 1,
      type: "scene_entered",
      payload: { sceneIndex: 0, sceneId: "scene-0" },
    }),
  });
  assert.equal(accepted.status, 200);
  const acceptedBody = await accepted.json();
  assert.equal(acceptedBody.receiptSha256, "a".repeat(64));
  assert.equal(acceptedBody.internal, undefined);

  const resume = await fetch(`${gateway}/mira/runtime-events`, { headers });
  assert.equal(resume.status, 200);
  const resumeBody = await resume.json();
  assert.equal(resumeBody.nextSequence, 2);
  assert.equal(resumeBody.internal, undefined);

  const forgedScore = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 2,
      type: "answer_submitted",
      payload: {
        sceneIndex: 0,
        sceneId: "scene-0",
        questionId: "q1",
        response: "12",
        attemptNumber: 1,
        score: 100,
      },
    }),
  });
  assert.equal(forgedScore.status, 400);

  const forgedRetryAttempt = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 2,
      type: "answer_submitted",
      payload: {
        sceneIndex: 0,
        sceneId: "scene-0",
        questionId: "q1",
        response: "12",
        attemptNumber: 2,
      },
    }),
  });
  assert.equal(forgedRetryAttempt.status, 400);

  const forgedIdentity = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 2,
      type: "scene_entered",
      payload: { sceneIndex: 1, sceneId: "scene-1" },
      childId: "other-child",
    }),
  });
  assert.equal(forgedIdentity.status, 400);
  assert.equal(eventCalls, 1);
});

test("gateway accepts bounded ASR transcript events and rejects forged ASR metadata", () => {
  const runtime = {
    runtimeSessionId: "runtime-session-a",
    learningSessionId: "learning-session-a",
    classroomId: "classroom-a",
  };
  const accepted = prepareRuntimeEvent(
    Buffer.from(
      JSON.stringify({
        schemaVersion: "mira.openmaic.student-runtime-event.v1",
        sequence: 7,
        type: "asr_transcribed",
        payload: {
          sceneIndex: 2,
          sceneId: "scene-2",
          turnId: "asr-turn-1",
          transcript: "我觉得答案是十二。",
        },
      }),
    ),
    runtime,
  );
  assert.deepEqual(accepted, {
    schemaVersion: "mira.openmaic.student-runtime-event.v1",
    sequence: 7,
    type: "asr_transcribed",
    payload: {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "我觉得答案是十二。",
    },
    idempotencyKey: "cb401d461231173ecb6fd27b75d5f3d3e7c8a66c2887457af2ca57ded71d9702",
  });

  for (const payload of [
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "",
    },
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "x".repeat(4097),
    },
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "bad turn id",
      transcript: "十二",
    },
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "十二",
      providerId: "browser-forged-provider",
    },
  ]) {
    assert.throws(
      () =>
        prepareRuntimeEvent(
          Buffer.from(
            JSON.stringify({
              schemaVersion: "mira.openmaic.student-runtime-event.v1",
              sequence: 7,
              type: "asr_transcribed",
              payload,
            }),
          ),
          runtime,
        ),
      /invalid runtime event/,
    );
  }
});

test("gateway removes stale compression headers after fetch decodes a classroom document", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const classroomHtml = "<main>decoded full interactive classroom</main>";
  const compressed = gzipSync(classroomHtml);
  const upstream = await listen(
    http.createServer((request, response) => {
      assert.equal(request.url, "/classroom/classroom-a?mira=1");
      assert.match(String(request.headers["accept-encoding"]), /gzip/);
      response.writeHead(200, {
        "content-type": "text/html; charset=utf-8",
        "content-encoding": "gzip",
        "content-length": compressed.byteLength,
      });
      response.end(compressed);
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const classroom = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
    headers: {
      cookie: "mira_openmaic_runtime=omr_good",
      "accept-encoding": "gzip",
    },
  });

  assert.equal(classroom.status, 200);
  assert.equal(classroom.headers.get("content-encoding"), null);
  assert.equal(classroom.headers.get("content-length"), null);
  assert.equal(await classroom.text(), classroomHtml);
});

test("gateway preserves upstream CSP while replacing frame ancestors", () => {
  const csp = mergeContentSecurityPolicy(
    "default-src 'self'; script-src 'self' 'nonce-abc'; frame-ancestors 'none'; object-src 'none'",
    "https://students.mira.example",
  );
  assert.match(csp, /default-src 'self'/);
  assert.match(csp, /script-src 'self' 'nonce-abc'/);
  assert.match(csp, /frame-ancestors https:\/\/students\.mira\.example/);
  assert.equal((csp.match(/frame-ancestors/g) || []).length, 1);
  assert.equal((csp.match(/object-src/g) || []).length, 1);
});

test("explicit local mode adds only fixed loopback student origins to private HTTP framing", async () => {
  const backend = await listen(http.createServer((_request, response) => {
    reply(response, formalRuntime());
  }));
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, {
      "content-type": "text/html",
      "content-security-policy": "script-src 'self'; frame-ancestors 'none'",
    });
    response.end("<main>classroom</main>");
  }));
  for (const entry of [
    {
      publicOrigin: "http://192.168.228.95:3101",
      studentWebOrigin: "http://192.168.228.95:3000",
      localLanProductionMode: "1",
      expected: "http://192.168.228.95:3000 http://localhost:3000 http://127.0.0.1:3000",
    },
    {
      publicOrigin: "http://192.168.228.95:3101",
      studentWebOrigin: "http://192.168.228.95:3000",
      localLanProductionMode: "0",
      expected: "http://192.168.228.95:3000",
    },
    {
      publicOrigin: "https://classroom.example.com",
      studentWebOrigin: "https://learn.example.com",
      localLanProductionMode: "1",
      expected: "https://learn.example.com",
    },
    {
      publicOrigin: "http://classroom.example.com",
      studentWebOrigin: "http://192.168.228.95:3000",
      localLanProductionMode: "1",
      expected: "http://192.168.228.95:3000",
    },
    {
      publicOrigin: "http://192.168.228.95:3101",
      studentWebOrigin: "http://learn.example.com",
      localLanProductionMode: "1",
      expected: "http://learn.example.com",
    },
  ]) {
    const { expected, ...configuration } = entry;
    const gateway = await listenGateway({ backend, upstream, ...configuration });
    const response = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
      headers: {
        cookie: "mira_openmaic_runtime=omr_good",
        origin: "http://arbitrary.example:3000",
        "x-forwarded-host": "arbitrary.example:3000",
      },
    });
    assert.equal(response.status, 200);
    const csp = response.headers.get("content-security-policy");
    assert.ok(csp.includes(`frame-ancestors ${expected};`));
    assert.match(csp, /script-src 'self'/);
    assert.doesNotMatch(csp, /arbitrary\.example|\*/);
    assert.equal((csp.match(/frame-ancestors/g) || []).length, 1);
  }
});

test("upstream redirects stay on the browser gateway host without trusting request headers", async () => {
  const backend = await listen(http.createServer((_request, response) => {
    reply(response, formalRuntime());
  }));
  let location;
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(307, { location }).end();
  }));
  const gateway = await listenGateway({ backend, upstream });
  for (const [source, expected] of [
    ["/classroom/classroom-a?mira=1#scene-2", "/classroom/classroom-a?mira=1#scene-2"],
    [`${upstream}/classroom/classroom-a?mira=1`, "/classroom/classroom-a?mira=1"],
    ["http://runtime.test/classroom/classroom-a?mira=1", "/classroom/classroom-a?mira=1"],
    [`${upstream}//external.example/path`, "/external.example/path"],
    ["https://unrelated.example/classroom", "https://unrelated.example/classroom"],
  ]) {
    location = source;
    const response = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
      headers: {
        cookie: "mira_openmaic_runtime=omr_good",
        "x-forwarded-host": "untrusted.example",
      },
      redirect: "manual",
    });
    assert.equal(response.status, 307);
    assert.equal(response.headers.get("location"), expected);
    if (source !== "https://unrelated.example/classroom") {
      assert.equal(new URL(expected, gateway).origin, new URL(gateway).origin);
    }
  }
});

test("gateway blocks generation and cross-classroom reads", () => {
  const runtime = { classroomId: "allowed-classroom" };
  assert.equal(
    authorizeRuntimeRequest(
      { method: "POST" },
      new URL("http://runtime.test/api/generate-classroom"),
      runtime,
    ).allowed,
    false,
  );
  const wrong = authorizeRuntimeRequest(
    { method: "GET" },
    new URL("http://runtime.test/api/classroom?id=other-classroom"),
    runtime,
  );
  assert.equal(wrong.allowed, false);
  assert.equal(wrong.status, 404);
  assert.equal(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("http://runtime.test/classroom/allowed-classroom"),
      runtime,
    ).allowed,
    true,
  );
});

test("gateway permits read-only server provider metadata but never provider writes", () => {
  const runtime = { classroomId: "allowed-classroom" };
  assert.deepEqual(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("http://runtime.test/api/server-providers"),
      runtime,
    ),
    { allowed: true, kind: "json" },
  );
  assert.equal(
    authorizeRuntimeRequest(
      { method: "POST" },
      new URL("http://runtime.test/api/server-providers"),
      runtime,
    ).allowed,
    false,
  );
});

test("asset authorization blocks legacy brand files and permits the Mira classroom icon", () => {
  const runtime = { classroomId: "classroom-a" };
  for (const pathname of legacyBrandAssetPaths) {
    assert.deepEqual(
      authorizeRuntimeRequest({ method: "GET" }, new URL(pathname, "http://runtime.test"), runtime),
      {
        allowed: false,
        status: 404,
        error: "asset_not_found",
      },
    );
  }
  assert.deepEqual(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("/mira-classroom-icon.svg", "http://runtime.test"),
      runtime,
    ),
    { allowed: true, kind: "asset" },
  );
});

test("student asset authorization fails closed for Next development HMR resources", () => {
  const runtime = { classroomId: "classroom-a" };
  const developmentOnlyPaths = [
    "/_next/webpack-hmr",
    "/_next/static/webpack/123.hot-update.json",
    "/_next/static/chunks/%5Bturbopack%5D_browser_dev_hmr-client_ts_deadbeef._.js",
    "/_next/static/chunks/node_modules_next_dist_client_dev_noop-turbopack-hmr.js",
    "/_next/static/chunks/react-refresh-runtime.js",
  ];

  for (const pathname of developmentOnlyPaths) {
    assert.deepEqual(
      authorizeRuntimeRequest({ method: "GET" }, new URL(pathname, "http://runtime.test"), runtime),
      {
        allowed: false,
        status: 404,
        error: "asset_not_found",
      },
    );
  }

  assert.deepEqual(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("/_next/static/chunks/app/classroom/runtime.js", "http://runtime.test"),
      runtime,
    ),
    { allowed: true, kind: "asset" },
  );
});

test("student HTTP gateway never proxies legacy brand files but serves the Mira icon", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const upstreamPaths = [];
  const upstream = await listen(
    http.createServer((request, response) => {
      upstreamPaths.push(request.url);
      response.writeHead(200, { "content-type": "image/svg+xml" });
      response.end('<svg aria-label="Mira classroom" />');
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };

  for (const pathname of legacyBrandAssetPaths) {
    const blocked = await fetch(`${gateway}${pathname}`, { headers });
    assert.equal(blocked.status, 404);
    const body = await blocked.json();
    assert.equal(body.error, "asset_not_found");
    assert.equal(body.message, "学生课堂不能访问这个功能");
    assert.doesNotMatch(body.message, /open\s*maic/i);
  }
  assert.deepEqual(upstreamPaths, []);

  const icon = await fetch(`${gateway}/mira-classroom-icon.svg`, { headers });
  assert.equal(icon.status, 200);
  assert.equal(icon.headers.get("content-type"), "image/svg+xml");
  assert.match(await icon.text(), /Mira classroom/);
  assert.deepEqual(upstreamPaths, ["/mira-classroom-icon.svg"]);
});

test("student HTTP gateway proxies only classroom avatar assets", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const avatarPng = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+9cQJkwAAAABJRU5ErkJggg==",
    "base64",
  );
  const upstreamPaths = [];
  const upstream = await listen(
    http.createServer((request, response) => {
      upstreamPaths.push(request.url);
      assert.equal(request.url, "/avatars/teacher-2.png");
      response.writeHead(200, { "content-type": "image/png" });
      response.end(avatarPng);
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };

  const avatar = await fetch(`${gateway}/avatars/teacher-2.png`, { headers });
  assert.equal(avatar.status, 200);
  assert.equal(avatar.headers.get("content-type"), "image/png");
  assert.deepEqual(Buffer.from(await avatar.arrayBuffer()), avatarPng);

  const unknown = await fetch(`${gateway}/private/teacher-2.png`, { headers });
  assert.equal(unknown.status, 403);
  const legacy = await fetch(`${gateway}/logo-horizontal.png`, { headers });
  assert.equal(legacy.status, 404);
  assert.deepEqual(upstreamPaths, ["/avatars/teacher-2.png"]);
});

test("student HTTP gateway never caches Next runtime chunks but may cache immutable assets", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const upstream = await listen(
    http.createServer((request, response) => {
      response.writeHead(200, {
        "content-type": request.url.startsWith("/_next/") ? "application/javascript" : "image/png",
        "cache-control": "public, max-age=31536000, immutable",
      });
      response.end("asset");
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };

  const runtimeChunk = await fetch(`${gateway}/_next/static/chunks/app/classroom/runtime.js`, {
    headers,
  });
  assert.equal(runtimeChunk.status, 200);
  assert.equal(runtimeChunk.headers.get("cache-control"), "no-store");

  const avatar = await fetch(`${gateway}/avatars/teacher-2.png`, { headers });
  assert.equal(avatar.status, 200);
  assert.equal(avatar.headers.get("cache-control"), "private, max-age=3600");
});

test("student runtime hides operator-only MP4 export without calling upstream", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  let upstreamCalls = 0;
  const upstream = await listen(
    http.createServer((_request, response) => {
      upstreamCalls += 1;
      reply(response, { enabled: true });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const capability = await fetch(`${gateway}/api/export-video/capability`, {
    headers: { cookie: "mira_openmaic_runtime=omr_good" },
  });
  assert.equal(capability.status, 200);
  assert.deepEqual(await capability.json(), { enabled: false });
  assert.equal(upstreamCalls, 0);

  assert.equal(
    authorizeRuntimeRequest(
      { method: "POST" },
      new URL("http://runtime.test/api/export-video/render"),
      {
        classroomId: "classroom-a",
      },
    ).allowed,
    false,
  );

  const blocked = await fetch(`${gateway}/api/export-video/render`, {
    method: "POST",
    headers: {
      cookie: "mira_openmaic_runtime=omr_good",
      "content-type": "application/json",
    },
    body: "{}",
  });
  assert.equal(blocked.status, 403);
  const blockedBody = await blocked.json();
  assert.equal(blockedBody.error, "openmaic_route_not_allowed");
  assert.equal(blockedBody.message, "学生课堂不能访问这个功能");
  assert.doesNotMatch(blockedBody.message, /open\s*maic/i);
  assert.equal(upstreamCalls, 0);
});

test("runtime JSON removes client credentials and rejects another stage", () => {
  const cleaned = JSON.parse(
    sanitizeRuntimeJson(
      Buffer.from(
        JSON.stringify({
          stageId: "classroom-a",
          apiKey: "must-not-leave-browser",
          config: {
            baseUrl: "https://attacker.invalid",
            agentIds: ["teacher"],
          },
        }),
      ),
      "classroom-a",
    ).toString("utf8"),
  );
  assert.deepEqual(cleaned, {
    stageId: "classroom-a",
    config: { agentIds: ["teacher"] },
  });
  assert.throws(
    () =>
      sanitizeRuntimeJson(Buffer.from(JSON.stringify({ stageId: "classroom-b" })), "classroom-a"),
    /cross-classroom/,
  );
});

test("authorized chat SSE is streamed through the gateway", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const upstream = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      assert.equal(request.url, "/api/chat");
      assert.equal(body.stageId, "classroom-a");
      assert.equal(body.apiKey, undefined);
      assert.equal(request.headers["x-mira-runtime-session"], "rs1");
      assert.equal(request.headers["x-mira-learning-session"], "ls1");
      assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
      assert.equal(request.headers["x-mira-runtime-purpose"], undefined);
      assert.equal(request.headers["x-mira-verification-challenge"], undefined);
      response.writeHead(200, { "content-type": "text/event-stream" });
      response.write('data: {"type":"text_delta","data":"你好"}\n\n');
      response.end();
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const result = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: {
      cookie: "mira_openmaic_runtime=omr_good",
      "content-type": "application/json",
      "x-mira-runtime-session": "attacker-session",
      "x-mira-learning-session": "attacker-learning-session",
      "x-mira-runtime-classroom-id": "attacker-classroom",
      "x-mira-runtime-purpose": "conversation_probe",
      "x-mira-verification-challenge": "attacker-challenge",
    },
    body: JSON.stringify({ stageId: "classroom-a", apiKey: "secret" }),
  });
  assert.equal(result.status, 200);
  assert.match(await result.text(), /text_delta/);
});

test("conversation probe is cookie-authenticated, scope-bound, and streams chat plus multipart ASR", async () => {
  const challenge = "ompc_abcdefghijklmnopqrstuvwxyz012345";
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/probe/exchange") {
        assert.equal(body.ticket, "ompt_abcdefghijklmnopqrstuvwxyz012345");
        return reply(response, {
          ok: true,
          purpose: "conversation_probe",
          runtimeToken: "ompr_runtime-token-abcdefghijklmnopqrstuvwxyz",
          runtimeSessionId: "probe-session-a",
          classroomId: "classroom-a",
          challenge,
          expiresAt: Date.now() + 60_000,
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/probe/validate") {
        assert.equal(body.runtimeToken, "ompr_runtime-token-abcdefghijklmnopqrstuvwxyz");
        return reply(response, {
          ok: true,
          purpose: "conversation_probe",
          runtimeSessionId: "probe-session-a",
          learningSessionId: "probe-learning-session-a",
          classroomId: "classroom-a",
          challenge,
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(404).end();
    }),
  );
  const seen = [];
  const upstream = await listen(
    http.createServer(async (request, response) => {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      seen.push({
        url: request.url,
        headers: request.headers,
        body: Buffer.concat(chunks),
      });
      if (request.url === "/api/chat") {
        response.writeHead(200, { "content-type": "text/event-stream" });
        response.end(
          `event: mira-verification\ndata: ${JSON.stringify({ challenge, route: "text-chat" })}\n\n`,
        );
        return;
      }
      reply(response, {
        success: true,
        proof: { challenge, route: "transcription" },
      });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const unauthenticated = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ stageId: "classroom-a" }),
  });
  assert.equal(unauthenticated.status, 401);

  const exchange = await fetch(
    `${gateway}/mira/probe?ticket=ompt_abcdefghijklmnopqrstuvwxyz012345`,
    {
      redirect: "manual",
    },
  );
  assert.equal(exchange.status, 204);
  const cookie = exchange.headers.get("set-cookie").split(";", 1)[0];
  assert.match(exchange.headers.get("set-cookie"), /HttpOnly/);

  const crossClassroom = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify({ stageId: "classroom-b" }),
  });
  assert.equal(crossClassroom.status, 403);
  assert.equal(seen.length, 0);

  const missingStage = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify({ message: "probe" }),
  });
  assert.equal(missingStage.status, 403);
  assert.equal(seen.length, 0);

  const chat = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: {
      cookie,
      "content-type": "application/json",
      "x-mira-runtime-purpose": "attacker-purpose",
      "x-mira-verification-challenge": "attacker-challenge",
      "x-mira-runtime-classroom-id": "attacker-classroom",
    },
    body: JSON.stringify({
      stageId: "classroom-a",
      apiKey: "must-be-scrubbed",
    }),
  });
  assert.equal(chat.status, 200);
  assert.match(await chat.text(), /mira-verification/);

  const form = new FormData();
  form.set("audio", new File(["silent-audio"], "probe.webm", { type: "audio/webm" }));
  form.set("language", "zh");
  const transcription = await fetch(`${gateway}/api/transcription`, {
    method: "POST",
    headers: { cookie },
    body: form,
  });
  assert.equal(transcription.status, 200);
  assert.equal((await transcription.json()).proof.route, "transcription");

  const blockedDocument = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
    headers: { cookie },
  });
  assert.equal(blockedDocument.status, 403);

  assert.equal(seen.length, 2);
  for (const request of seen) {
    assert.equal(request.headers["x-mira-runtime-session"], "probe-session-a");
    assert.equal(request.headers["x-mira-runtime-purpose"], "conversation_probe");
    assert.equal(request.headers["x-mira-verification-challenge"], challenge);
    assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
  }
  assert.doesNotMatch(seen[0].body.toString("utf8"), /must-be-scrubbed/);
  assert.match(seen[1].headers["content-type"], /multipart\/form-data; boundary=/);
  assert.match(seen[1].body.toString("utf8"), /silent-audio/);
});

test("formal classroom JSON is assembled with session-bound audio and same-origin WAV delivery", async () => {
  const wav = Buffer.alloc(64);
  wav.write("RIFF", 0, "ascii");
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVE", 8, "ascii");
  const digest = createHash("sha256").update(wav).digest("hex");
  const manifest = formalAudioManifest(digest, wav.length);
  let manifestCalls = 0;
  let audioCalls = 0;
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        if (body.runtimeToken !== "omr_good") {
          response.writeHead(401, { "content-type": "application/json" });
          response.end(JSON.stringify({ ok: false, error: "invalid" }));
          return;
        }
        return reply(response, formalRuntime());
      }
      assert.equal(request.headers["x-mira-internal-token"], "test-internal-token");
      assert.equal(request.headers["x-mira-internal-source"], "openmaic-runtime-gateway");
      assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
      assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
      assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
      assert.equal(request.headers.cookie, undefined);
      assert.equal(request.headers.authorization, undefined);
      if (request.url === "/internal/learning/openmaic/runtime/audio-manifest") {
        manifestCalls += 1;
        return reply(response, {
          ...manifest,
          internal: { mustNotLeak: true },
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/audio/formal-audio-0") {
        audioCalls += 1;
        response.writeHead(200, {
          "content-type": "audio/wav",
          "content-length": wav.length,
          "x-mira-audio-sha256": digest,
        });
        response.end(wav);
        return;
      }
      response.writeHead(404, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "not_found" }));
    }),
  );
  const upstream = await listen(
    http.createServer((request, response) => {
      assert.equal(request.url, "/api/classroom?id=classroom-a");
      assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
      assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
      assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
      assert.notEqual(request.headers["x-mira-runtime-session"], "forged-session");
      reply(response, { success: true, classroom: formalClassroom() });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const cookie = "mira_openmaic_runtime=omr_good";

  const classroomResponse = await fetch(`${gateway}/api/classroom?id=classroom-a`, {
    headers: { cookie, "x-mira-runtime-session": "forged-session" },
  });
  assert.equal(classroomResponse.status, 200);
  const classroomPayload = await classroomResponse.json();
  assert.equal(classroomPayload.internal, undefined);
  const speech = classroomPayload.classroom.scenes[0].actions[0];
  assert.deepEqual(speech.audioMetadata, {
    schemaVersion: "mira.openmaic.speech-audio.v1",
    providerId: "qwen-tts",
    modelId: "qwen3-tts-flash",
    voiceId: "Ethan",
    fallbackUsed: false,
  });
  assert.equal(speech.audioId, "formal-audio-0");
  assert.equal(speech.audioUrl, "/mira/runtime-audio/formal-audio-0");
  assert.equal(manifestCalls, 1);

  const audioResponse = await fetch(`${gateway}${speech.audioUrl}`, {
    headers: { cookie, "x-mira-runtime-session": "forged-session" },
  });
  assert.equal(audioResponse.status, 200);
  assert.equal(audioResponse.headers.get("content-type"), "audio/wav");
  assert.equal(audioResponse.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(Buffer.from(await audioResponse.arrayBuffer()), wav);
  assert.equal(audioCalls, 1);

  assert.equal((await fetch(`${gateway}${speech.audioUrl}`)).status, 401);
  assert.equal(
    (
      await fetch(`${gateway}/mira/runtime-audio/not-this-classroom`, {
        headers: { cookie },
      })
    ).status,
    404,
  );
  assert.equal(
    (
      await fetch(`${gateway}/mira/runtime-audio/%2e%2e%2fsecret.wav`, {
        headers: { cookie },
      })
    ).status,
    403,
  );
  assert.equal(
    (
      await fetch(`${gateway}/api/classroom?id=classroom-b`, {
        headers: { cookie },
      })
    ).status,
    404,
  );
  assert.equal(
    (
      await fetch(`${gateway}${speech.audioUrl}`, {
        headers: { cookie: "mira_openmaic_runtime=omr_wrong" },
      })
    ).status,
    401,
  );
});

test("formal audio assembly fails closed for partial, duplicate, or conflicting bindings", () => {
  const hash = "a".repeat(64);
  const runtime = formalRuntime();
  const classroom = { success: true, classroom: formalClassroom() };
  const manifest = formalAudioManifest(hash, 64);
  // Python json.dumps(..., sort_keys=True, separators=(",", ":"),
  // ensure_ascii=False) over the same {stage, scenes} authority.
  assert.equal(
    manifest.classroomContentSha256,
    "17ae050d637aa618cd525b2fe254af07c00e1c0b19165a31d247afba6e0461f3",
  );
  const assembled = injectRuntimeAudioBindings(
    Buffer.from(JSON.stringify(classroom)),
    runtime,
    manifest,
  );
  assert.equal(JSON.parse(assembled).classroom.scenes[9].actions[0].audioId, "formal-audio-9");

  for (const invalid of [
    { ...manifest, speechActionCount: 9, assets: manifest.assets.slice(0, 9) },
    {
      ...manifest,
      assets: [...manifest.assets.slice(0, 9), manifest.assets[0]],
    },
  ]) {
    assert.throws(
      () => injectRuntimeAudioBindings(Buffer.from(JSON.stringify(classroom)), runtime, invalid),
      (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
    );
  }
  const conflicting = formalClassroom();
  conflicting.scenes[0].actions[0].audioId = "other-audio";
  const conflictingManifest = formalAudioManifest(hash, 64, conflicting);
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: conflicting })),
        runtime,
        conflictingManifest,
      ),
    (error) =>
      error?.statusCode === 502 &&
      error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );
});

test("formal audio assembly binds every speech in scene/action order for an adaptive classroom", () => {
  const runtime = formalRuntime();
  const classroom = formalClassroom(7);
  classroom.scenes[0].actions.push({
    id: "speech-extra",
    type: "speech",
    text: "extra focused explanation",
  });
  const manifest = formalAudioManifest("a".repeat(64), 64, classroom);
  const assembled = injectRuntimeAudioBindings(
    Buffer.from(JSON.stringify({ success: true, classroom })),
    runtime,
    manifest,
  );
  const parsed = JSON.parse(assembled);
  assert.equal(parsed.classroom.scenes.length, 7);
  assert.equal(manifest.speechActionCount, 8);
  assert.equal(parsed.classroom.scenes[0].actions[0].audioId, "formal-audio-0");
  assert.equal(parsed.classroom.scenes[0].actions[1].audioId, "formal-audio-1");
  assert.equal(parsed.classroom.scenes[6].actions[0].audioId, "formal-audio-7");

  const missingSpeech = formalClassroom(7);
  missingSpeech.scenes[1].actions = [];
  const missingSpeechManifest = formalAudioManifest("a".repeat(64), 64, missingSpeech);
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: missingSpeech })),
        runtime,
        missingSpeechManifest,
      ),
    (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );

  const overfullScene = formalClassroom(1);
  overfullScene.scenes[0].actions = Array.from({ length: 21 }, (_, index) => ({
    id: `speech-overfull-${index}`,
    type: "speech",
    text: `explanation ${index}`,
  }));
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: overfullScene })),
        runtime,
        formalAudioManifest("a".repeat(64), 64, overfullScene),
      ),
    (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );

  const tooManyOverall = formalClassroom(13);
  for (const [sceneIndex, scene] of tooManyOverall.scenes.entries()) {
    scene.actions = Array.from({ length: 20 }, (_, actionIndex) => ({
      id: `speech-total-${sceneIndex}-${actionIndex}`,
      type: "speech",
      text: `explanation ${sceneIndex}-${actionIndex}`,
    }));
  }
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: tooManyOverall })),
        runtime,
        formalAudioManifest("a".repeat(64), 64, tooManyOverall),
      ),
    (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );
});

test("formal audio assembly rejects same-ID classroom content tampering", () => {
  const authoritative = formalClassroom();
  const manifest = formalAudioManifest("a".repeat(64), 64, authoritative);
  const cases = [
    [
      "stage",
      (classroom) => {
        classroom.stage.title = "tampered stage";
      },
    ],
    [
      "speech text",
      (classroom) => {
        classroom.scenes[0].actions[0].text = "tampered lesson";
      },
    ],
    [
      "quiz",
      (classroom) => {
        classroom.scenes[1].content.quiz.prompt = "tampered quiz";
      },
    ],
  ];
  for (const [label, mutate] of cases) {
    const classroom = structuredClone(authoritative);
    mutate(classroom);
    assert.throws(
      () =>
        injectRuntimeAudioBindings(
          Buffer.from(JSON.stringify({ success: true, classroom })),
          formalRuntime(),
          manifest,
        ),
      (error) =>
        error?.statusCode === 502 &&
        error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
      label,
    );
  }
});

test("classroom assembly fails closed on non-JSON upstream and manifest backend failure", async () => {
  let mode = "non-json";
  const backend = await listen(
    http.createServer(async (request, response) => {
      await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        return reply(response, formalRuntime());
      }
      if (request.url === "/internal/learning/openmaic/runtime/audio-manifest") {
        response.writeHead(503, { "content-type": "application/json" });
        response.end(JSON.stringify({ ok: false, error: "audio_not_ready" }));
        return;
      }
      response.writeHead(404).end();
    }),
  );
  const upstream = await listen(
    http.createServer((_request, response) => {
      if (mode === "non-json") {
        response.writeHead(200, { "content-type": "text/html" });
        response.end("not classroom JSON");
        return;
      }
      reply(response, { success: true, classroom: formalClassroom() });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const options = { headers: { cookie: "mira_openmaic_runtime=omr_good" } };
  const nonJson = await fetch(`${gateway}/api/classroom?id=classroom-a`, options);
  assert.equal(nonJson.status, 502);
  assert.equal((await nonJson.json()).error, "openmaic_runtime_audio_binding_invalid");

  mode = "backend-failure";
  const backendFailure = await fetch(`${gateway}/api/classroom?id=classroom-a`, options);
  assert.equal(backendFailure.status, 503);
  assert.equal((await backendFailure.json()).error, "audio_not_ready");
});

function formalRuntime() {
  return {
    ok: true,
    runtimeSessionId: "runtime-session-a",
    learningSessionId: "learning-session-a",
    classroomId: "classroom-a",
    expiresAt: Date.now() + 60_000,
  };
}

function formalClassroom(sceneCount = 10) {
  return {
    id: "classroom-a",
    stage: { id: "stage-a", title: "authoritative stage" },
    scenes: Array.from({ length: sceneCount }, (_, index) => ({
      id: `scene-${index}`,
      actions: [{ id: `speech-${index}`, type: "speech", text: `lesson ${index}` }],
      content: {
        quiz: { id: `quiz-${index}`, prompt: `question ${index}` },
      },
    })),
  };
}

function formalAudioManifest(contentHash, byteSize, classroom = formalClassroom()) {
  const speechActions = classroom.scenes.flatMap((scene) =>
    scene.actions.filter((action) => action.type === "speech").map((action) => ({ scene, action })),
  );
  return {
    ok: true,
    schemaVersion: "mira.openmaic.runtime-audio-manifest.v1",
    classroomId: "classroom-a",
    classroomContentSha256: formalClassroomContentSha256(classroom),
    speechActionCount: speechActions.length,
    assets: speechActions.map(({ scene, action }, index) => ({
      sceneId: scene.id,
      actionId: action.id,
      audioId: `formal-audio-${index}`,
      deliveryPath: `/mira/runtime-audio/formal-audio-${index}`,
      contentHash,
      mimeType: "audio/wav",
      byteSize,
      durationMs: 1_000,
      audioMetadata: {
        schemaVersion: "mira.openmaic.speech-audio.v1",
        providerId: "qwen-tts",
        modelId: "qwen3-tts-flash",
        voiceId: "Ethan",
        fallbackUsed: false,
      },
    })),
  };
}

function formalClassroomContentSha256(classroom) {
  const canonical = canonicalJsonForHash({
    stage: classroom.stage,
    scenes: classroom.scenes,
  });
  return createHash("sha256").update(canonical, "utf8").digest("hex");
}

function canonicalJsonForHash(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJsonForHash).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJsonForHash(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function listenGateway({ backend, upstream, ...overrides }) {
  const server = createGateway({
    backendUrl: backend,
    upstreamUrl: upstream,
    publicOrigin: "http://runtime.test",
    studentWebOrigin: "http://student.test",
    internalToken: "test-internal-token",
    secureCookie: false,
    ...overrides,
  });
  servers.push(server);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

async function listen(server) {
  servers.push(server);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

function reply(response, payload) {
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

async function jsonBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}


test("student interaction events bind exact fields and cannot claim grades or arbitrary operations", () => {
  const runtime = { runtimeSessionId: "runtime-1", learningSessionId: "learning-1", classroomId: "classroom-1" };
  const payload = { sceneIndex: 1, sceneId: "scene-1", objectiveIndex: 0, controlSelector: "#quantity",
    action: "range", value: "12", feedbackText: "一个十两个一，因为十个一是一个十" };
  const encode = value => Buffer.from(JSON.stringify({ schemaVersion: "mira.openmaic.student-runtime-event.v1",
    sequence: 1, type: "interaction_completed", payload: value }));
  assert.deepEqual(prepareRuntimeEvent(encode(payload), runtime).payload, payload);
  for (const change of [{objectiveIndex:true}, {objectiveIndex:30}, {action:"evaluate"},
    {controlSelector:"body *"}, {value:"x".repeat(501)}, {feedbackText:""}, {passed:true},
    {action:"click", value:"12"}]) assert.throws(() => prepareRuntimeEvent(encode({...payload,...change}), runtime));
  assert.equal(prepareRuntimeEvent(encode({...payload, objectiveIndex:29}), runtime).payload.objectiveIndex, 29);
});

test("new paid classrooms receive only backend-authorized budget headers and canonical teaching requests", async () => {
  let admission, nativeRequest;
  const binding = {schemaVersion:"mira.learning.paid-budget-binding.v1",authorizationId:"a".repeat(64),required:true};
  const backend = await listen(http.createServer(async (request,response) => {
    if (request.url.endsWith('/paid-call')) {
      admission = { body: await jsonBody(request), headers: request.headers };
      return reply(response,{ok:true,paidBudget:binding,request:{messages:[],canonical:true}});
    }
    reply(response,{...formalRuntime(),paidBudgets:{required_teaching:binding,optional_interaction:null}});
  }));
  const upstream = await listen(http.createServer(async (request,response) => {
    nativeRequest = {body:await jsonBody(request),headers:request.headers};reply(response,{ok:true});
  }));
  const gateway = await listenGateway({backend,upstream});
  const result = await fetch(`${gateway}/api/chat`, {method:'POST',headers:{
    cookie:'mira_openmaic_runtime=omr_good','content-type':'application/json',
    'x-mira-paid-budget-authorization':'forged','x-mira-internal-token':'forged',
  },body:JSON.stringify({paidBudget:binding,authorizationId:'forged',messages:[],miraScriptedAction:{sceneId:'scene-a',actionId:'discussion-a'}})});
  assert.equal(result.status,200);
  assert.equal(admission.body.path,'/api/chat');
  assert.equal(admission.body.request.paidBudget,undefined);
  assert.equal(admission.body.request.authorizationId,undefined);
  assert.equal(admission.headers['x-mira-internal-token'],'test-internal-token');
  assert.equal(nativeRequest.headers['x-mira-paid-budget-authorization'],binding.authorizationId);
  assert.equal(nativeRequest.headers['x-mira-paid-budget-required'],'1');
  assert.equal(nativeRequest.headers['x-mira-internal-token'],'test-internal-token');
  assert.deepEqual(nativeRequest.body,{messages:[],canonical:true});
});

test("new classroom unpaid interaction fails before any native request while old playback remains readable", async () => {
  let nativeCalls=0;
  const backend = await listen(http.createServer((request,response) => {
    if(request.url.endsWith('/paid-call'))return reply(response,{ok:true,paidBudget:null});
    reply(response,{...formalRuntime(),paidBudgets:{required_teaching:null,optional_interaction:null}});
  }));
  const upstream = await listen(http.createServer((_request,response) => {nativeCalls++;reply(response,{ok:true});}));
  const gateway = await listenGateway({backend,upstream});
  const response = await fetch(`${gateway}/api/chat`,{method:'POST',headers:{cookie:'mira_openmaic_runtime=omr_good','content-type':'application/json'},body:'{}'});
  assert.equal(response.status,503);assert.equal(nativeCalls,0);
  const asset=await fetch(`${gateway}/_next/static/chunk.js`,{headers:{cookie:'mira_openmaic_runtime=omr_good'}});
  assert.equal(asset.status,200);assert.equal(nativeCalls,1);
});
