import http from "node:http";
import { createHash, timingSafeEqual } from "node:crypto";
import { Readable } from "node:stream";
import { URL } from "node:url";

const DEFAULT_MAX_BODY_BYTES = 25 * 1024 * 1024;
const MAX_RUNTIME_AUDIO_BYTES = 16 * 1024 * 1024;
const RUNTIME_COOKIE = "mira_openmaic_runtime";
const SAFE_API_PREFIXES = ["/api/pbl/v2/"];
const SAFE_API_PATHS = new Set([
  "/api/chat",
  "/api/chat/pi",
  "/api/generate/tts",
  "/api/transcription",
  "/api/quiz-grade",
]);
const PUBLIC_ASSET_PREFIXES = [
  "/_next/",
  "/avatars/",
  "/vendor/",
  "/fonts/",
  "/icons/",
  "/logos/",
  "/images/",
];
const BLOCKED_LEGACY_BRAND_ASSET_PATHS = new Set([
  "/logo-horizontal.png",
  "/openmaic-mark.png",
  "/openmaic-favicon.ico",
  "/openmaic-apple-icon.png",
]);
// The student gateway is a production playback boundary. If its upstream is
// accidentally pointed at `next dev`, fail closed before a refresh client or
// hot-update payload can enter an active classroom.
const NEXT_DEVELOPMENT_ASSET_PATTERN = /(?:hmr|hot-update|react(?:_|-)refresh)/i;
const SECRET_KEYS = new Set([
  "apikey",
  "api_key",
  "ttsapikey",
  "websearchapikey",
  "imageapikey",
  "videoapikey",
  "asrapikey",
  "baseurl",
  "ttsbaseurl",
]);

export function createGateway(overrides = {}) {
  const config = gatewayConfig(overrides);
  return http.createServer((request, response) => {
    void handleRequest(request, response, config).catch((error) => {
      if (response.headersSent) {
        response.destroy(error);
        return;
      }
      const status = Number(error?.statusCode || 502);
      json(response, status, {
        ok: false,
        error:
          error?.payload?.error ||
          (status === 401 ? "openmaic_runtime_session_invalid" : "runtime_gateway_failed"),
        message:
          error?.payload?.message ||
          (status === 401 ? "课堂登录已经失效" : "互动课堂暂时不可用，请稍后重试"),
      });
    });
  });
}

async function handleRequest(request, response, config) {
  const url = new URL(request.url || "/", config.publicOrigin);
  if (url.pathname === "/health") {
    if (request.method !== "GET") return methodNotAllowed(response);
    return json(response, 200, {
      ok: true,
      service: "mira-openmaic-runtime-gateway",
      sourceVersion: config.sourceVersion,
    });
  }
  if (url.pathname === "/mira/launch") {
    if (request.method !== "GET") return methodNotAllowed(response);
    return launch(request, response, url, config);
  }
  if (url.pathname === "/mira/probe") {
    if (request.method !== "GET") return methodNotAllowed(response);
    return launchConversationProbe(request, response, url, config);
  }

  const runtimeToken = readCookie(request.headers.cookie, RUNTIME_COOKIE);
  if (!runtimeToken) return unauthorized(response);
  const runtime = await validateRuntime(runtimeToken, config);
  if (url.pathname === "/mira/runtime-events") {
    return recordRuntimeEvent(request, response, runtime, config);
  }
  const decision = authorizeRuntimeRequest(request, url, runtime);
  if (!decision.allowed) {
    return json(response, decision.status || 403, {
      ok: false,
      error: decision.error || "openmaic_route_not_allowed",
      message: "学生课堂不能访问这个功能",
    });
  }
  if (decision.kind === "student-video-export-capability") {
    // The pinned OpenMAIC runtime is also used by trusted content operators,
    // where MP4 rendering may be enabled. Students must never be offered that
    // operator-only control: returning the upstream capability would expose a
    // button whose render job is correctly blocked by this gateway.
    return json(response, 200, { enabled: false });
  }
  if (decision.kind === "runtime-audio") {
    return deliverRuntimeAudio(response, runtime, config, decision.audioId);
  }
  return proxyToUpstream(request, response, url, runtime, config, decision);
}

async function recordRuntimeEvent(request, response, runtime, config) {
  if (runtime.purpose === "conversation_probe") {
    return json(response, 403, {
      ok: false,
      error: "openmaic_probe_runtime_event_blocked",
      message: "验证课堂不能写入学生学习记录",
    });
  }
  const trustedHeaders = {
    "X-Mira-Runtime-Session": String(runtime.runtimeSessionId),
    "X-Mira-Learning-Session": String(runtime.learningSessionId),
    "X-Mira-Runtime-Classroom-Id": String(runtime.classroomId),
  };
  if (request.method === "GET") {
    const result = await backendJson(
      config,
      "/internal/learning/openmaic/runtime/events",
      undefined,
      trustedHeaders,
      "GET",
    );
    const { internal: _internal, ...publicStatus } = result;
    return json(response, 200, publicStatus);
  }
  if (request.method !== "POST") return methodNotAllowed(response);
  if (!isJsonRequest(request)) {
    return json(response, 415, {
      ok: false,
      error: "runtime_event_json_required",
      message: "课堂事件格式无效",
    });
  }
  const raw = await readBody(request, Math.min(config.maxBodyBytes, 8192));
  const event = prepareRuntimeEvent(raw, runtime);
  const result = await backendJson(
    config,
    "/internal/learning/openmaic/runtime/events",
    event,
    trustedHeaders,
  );
  const { internal: _internal, ...publicReceipt } = result;
  return json(response, 200, publicReceipt);
}

export function prepareRuntimeEvent(raw, runtime) {
  let input;
  try {
    input = JSON.parse(raw.toString("utf8"));
  } catch {
    const error = new Error("invalid runtime event JSON");
    error.statusCode = 400;
    throw error;
  }
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return invalidRuntimeEvent();
  }
  const rootKeys = Object.keys(input).sort();
  if (rootKeys.join(",") !== "payload,schemaVersion,sequence,type") {
    return invalidRuntimeEvent();
  }
  if (input.schemaVersion !== "mira.openmaic.student-runtime-event.v1") {
    return invalidRuntimeEvent();
  }
  if (!Number.isInteger(input.sequence) || input.sequence < 1 || input.sequence > 1_000_000) {
    return invalidRuntimeEvent();
  }
  const fieldsByType = {
    scene_entered: ["sceneId", "sceneIndex"],
    action_completed: ["actionId", "sceneId", "sceneIndex"],
    answer_submitted: ["attemptNumber", "questionId", "response", "sceneId", "sceneIndex"],
    asr_transcribed: ["sceneId", "sceneIndex", "transcript", "turnId"],
    classroom_completed: ["sceneId", "sceneIndex"],
  };
  const expectedFields = fieldsByType[input.type];
  if (
    !expectedFields ||
    !input.payload ||
    typeof input.payload !== "object" ||
    Array.isArray(input.payload) ||
    Object.keys(input.payload).sort().join(",") !== expectedFields.join(",")
  ) {
    return invalidRuntimeEvent();
  }
  const payload = { ...input.payload };
  if (
    !Number.isInteger(payload.sceneIndex) ||
    payload.sceneIndex < 0 ||
    payload.sceneIndex >= 100
  ) {
    return invalidRuntimeEvent();
  }
  for (const key of ["sceneId", "actionId", "questionId", "turnId"]) {
    if (key in payload && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(String(payload[key] || ""))) {
      return invalidRuntimeEvent();
    }
  }
  if (input.type === "answer_submitted") {
    if (payload.attemptNumber !== 1) return invalidRuntimeEvent();
    if (
      payload.response == null ||
      (typeof payload.response === "object" && !Array.isArray(payload.response)) ||
      Buffer.byteLength(canonicalJson(payload.response), "utf8") > 4096
    ) {
      return invalidRuntimeEvent();
    }
  }
  if (
    input.type === "asr_transcribed" &&
    (typeof payload.transcript !== "string" ||
      payload.transcript.length === 0 ||
      payload.transcript.trim() !== payload.transcript ||
      Buffer.byteLength(payload.transcript, "utf8") > 4096)
  ) {
    return invalidRuntimeEvent();
  }
  if (!runtime.runtimeSessionId || !runtime.learningSessionId || !runtime.classroomId) {
    const error = new Error("runtime identity incomplete");
    error.statusCode = 401;
    throw error;
  }
  const material = [
    String(runtime.runtimeSessionId),
    "mira.openmaic.student-runtime-event.v1",
    String(input.sequence),
    String(input.type),
    canonicalJson(payload),
  ].join("\n");
  return {
    schemaVersion: "mira.openmaic.student-runtime-event.v1",
    sequence: input.sequence,
    type: input.type,
    payload,
    idempotencyKey: createHash("sha256").update(material).digest("hex"),
  };
}

function invalidRuntimeEvent() {
  const error = new Error("invalid runtime event");
  error.statusCode = 400;
  throw error;
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  const encoded = JSON.stringify(value);
  if (encoded === undefined || (encoded === "null" && value !== null)) {
    return invalidRuntimeEvent();
  }
  return encoded;
}

async function launch(_request, response, url, config) {
  const ticket = String(url.searchParams.get("ticket") || "");
  if (!/^omt_[A-Za-z0-9_-]{20,100}$/.test(ticket)) {
    return json(response, 400, {
      ok: false,
      error: "invalid_openmaic_launch_ticket",
      message: "课堂登录票据无效",
    });
  }
  const result = await backendJson(config, "/internal/learning/openmaic/runtime/exchange", {
    ticket,
  });
  if (!result.ok || !result.runtimeToken || !result.classroomId) {
    return unauthorized(response);
  }
  const maxAge = Math.max(1, Math.floor((Number(result.expiresAt) - Date.now()) / 1000));
  response.statusCode = 303;
  response.setHeader(
    "Set-Cookie",
    serializeCookie(RUNTIME_COOKIE, result.runtimeToken, {
      maxAge,
      secure: config.secureCookie,
    }),
  );
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Location", `/classroom/${encodeURIComponent(result.classroomId)}?mira=1`);
  response.end();
}

async function launchConversationProbe(_request, response, url, config) {
  const ticket = String(url.searchParams.get("ticket") || "");
  if (!/^ompt_[A-Za-z0-9_-]{20,100}$/.test(ticket)) {
    return json(response, 400, {
      ok: false,
      error: "invalid_openmaic_probe_ticket",
      message: "课堂对话验证票据无效",
    });
  }
  const result = await backendJson(config, "/internal/learning/openmaic/runtime/probe/exchange", {
    ticket,
  });
  if (
    !result.ok ||
    result.purpose !== "conversation_probe" ||
    !String(result.runtimeToken || "").startsWith("ompr_") ||
    !result.runtimeSessionId ||
    !result.classroomId ||
    !result.challenge
  ) {
    return unauthorized(response);
  }
  const maxAge = Math.max(1, Math.floor((Number(result.expiresAt) - Date.now()) / 1000));
  response.statusCode = 204;
  response.setHeader(
    "Set-Cookie",
    serializeCookie(RUNTIME_COOKIE, result.runtimeToken, {
      maxAge,
      secure: config.secureCookie,
    }),
  );
  response.setHeader("Cache-Control", "no-store");
  response.end();
}

async function validateRuntime(runtimeToken, config) {
  const isProbe = String(runtimeToken).startsWith("ompr_");
  const result = await backendJson(
    config,
    isProbe
      ? "/internal/learning/openmaic/runtime/probe/validate"
      : "/internal/learning/openmaic/runtime/validate",
    { runtimeToken },
  );
  if (!result.ok || !result.classroomId) {
    const error = new Error("runtime session invalid");
    error.statusCode = 401;
    throw error;
  }
  if (
    isProbe &&
    (result.purpose !== "conversation_probe" || !result.runtimeSessionId || !result.challenge)
  ) {
    const error = new Error("conversation probe session invalid");
    error.statusCode = 401;
    throw error;
  }
  return result;
}

export function authorizeRuntimeRequest(request, url, runtime) {
  const method = String(request.method || "GET").toUpperCase();
  const pathname = url.pathname;
  const classroomId = String(runtime.classroomId || "");

  if (runtime.purpose === "conversation_probe") {
    if (method === "POST" && ["/api/chat", "/api/transcription"].includes(pathname)) {
      return {
        allowed: true,
        kind: "conversation-probe",
        sanitizeJson: pathname === "/api/chat",
      };
    }
    return {
      allowed: false,
      status: 403,
      error: "openmaic_probe_route_not_allowed",
    };
  }

  if (method === "GET" && pathname === `/classroom/${classroomId}`) {
    return { allowed: true, kind: "document" };
  }
  if (method === "GET" && pathname === "/api/classroom") {
    return url.searchParams.get("id") === classroomId
      ? { allowed: true, kind: "json" }
      : { allowed: false, status: 404, error: "classroom_not_found" };
  }
  const runtimeAudioMatch = pathname.match(
    /^\/mira\/runtime-audio\/([A-Za-z0-9][A-Za-z0-9._:-]{0,159})$/,
  );
  if (method === "GET" && runtimeAudioMatch) {
    return {
      allowed: true,
      kind: "runtime-audio",
      audioId: runtimeAudioMatch[1],
    };
  }
  if (method === "GET" && pathname.startsWith(`/api/classroom-media/${classroomId}/`)) {
    return { allowed: true, kind: "media" };
  }
  if (method === "GET" && BLOCKED_LEGACY_BRAND_ASSET_PATHS.has(pathname)) {
    return { allowed: false, status: 404, error: "asset_not_found" };
  }
  if (
    method === "GET" &&
    pathname.startsWith("/_next/") &&
    NEXT_DEVELOPMENT_ASSET_PATTERN.test(pathname)
  ) {
    return { allowed: false, status: 404, error: "asset_not_found" };
  }
  if (
    method === "GET" &&
    (PUBLIC_ASSET_PREFIXES.some((prefix) => pathname.startsWith(prefix)) ||
      /^\/[A-Za-z0-9._-]+\.(?:ico|png|svg|webp|woff2?)$/.test(pathname))
  ) {
    return { allowed: true, kind: "asset" };
  }
  if (method === "GET" && pathname === "/api/export-video/capability") {
    return { allowed: true, kind: "student-video-export-capability" };
  }
  if (method === "GET" && pathname === "/api/server-providers") {
    // OpenMAIC returns provider IDs and reviewed model/voice policy only; its
    // server route never returns credentials or private base URLs. The client
    // needs this metadata to select the same TTS/ASR identity as generation.
    return { allowed: true, kind: "json" };
  }
  if (
    ["GET", "POST", "PUT", "PATCH"].includes(method) &&
    (SAFE_API_PATHS.has(pathname) ||
      SAFE_API_PREFIXES.some((prefix) => pathname.startsWith(prefix)))
  ) {
    return {
      allowed: true,
      kind: "runtime-api",
      sanitizeJson: method !== "GET",
    };
  }

  // Generation, settings, provider configuration, persistence administration,
  // editing, arbitrary media proxying and MP4 render jobs are intentionally not
  // student runtime routes. MP4 export is invoked by Mira's internal content ops.
  return { allowed: false, status: 403, error: "openmaic_route_not_allowed" };
}

async function proxyToUpstream(request, response, url, runtime, config, decision) {
  const upstreamUrl = new URL(url.pathname + url.search, `${config.upstreamUrl}/`);
  let body;
  const method = String(request.method || "GET").toUpperCase();
  if (!["GET", "HEAD"].includes(method)) {
    body = await readBody(request, config.maxBodyBytes);
    if (decision.sanitizeJson && isJsonRequest(request)) {
      body = sanitizeRuntimeJson(body, runtime.classroomId, {
        requireRootStageId: decision.kind === "conversation-probe" && url.pathname === "/api/chat",
      });
    }
  }
  const headers = filteredRequestHeaders(request.headers);
  headers.set("x-mira-runtime-session", String(runtime.runtimeSessionId));
  headers.set("x-mira-learning-session", String(runtime.learningSessionId));
  headers.set("x-mira-runtime-classroom-id", String(runtime.classroomId));
  if (runtime.purpose === "conversation_probe") {
    headers.set("x-mira-runtime-purpose", "conversation_probe");
    headers.set("x-mira-verification-challenge", String(runtime.challenge));
  }
  headers.set("x-forwarded-host", new URL(config.publicOrigin).host);
  headers.set("x-forwarded-proto", new URL(config.publicOrigin).protocol.replace(":", ""));
  const upstream = await fetch(upstreamUrl, {
    method,
    headers,
    body,
    redirect: "manual",
    signal: AbortSignal.timeout(config.upstreamTimeoutMs),
  });

  if (
    decision.kind === "json" &&
    method === "GET" &&
    url.pathname === "/api/classroom" &&
    upstream.ok
  ) {
    const contentType = String(upstream.headers.get("content-type") || "")
      .split(";", 1)[0]
      .trim()
      .toLowerCase();
    if (contentType !== "application/json") {
      return runtimeAudioBindingError();
    }
    const rawClassroom = await readFetchBody(
      upstream.body,
      config.maxBodyBytes,
      runtimeAudioBindingError,
    );
    const manifest = await backendJson(
      config,
      "/internal/learning/openmaic/runtime/audio-manifest",
      undefined,
      trustedRuntimeHeaders(runtime),
      "GET",
    );
    const assembled = injectRuntimeAudioBindings(rawClassroom, runtime, manifest);
    response.statusCode = upstream.status;
    copyResponseHeaders(upstream.headers, response, config, decision, url.pathname);
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.setHeader("Content-Length", String(assembled.length));
    response.end(assembled);
    return;
  }

  response.statusCode = upstream.status;
  copyResponseHeaders(upstream.headers, response, config, decision, url.pathname);
  if (!upstream.body) return response.end();
  Readable.fromWeb(upstream.body).pipe(response);
}

export function injectRuntimeAudioBindings(raw, runtime, manifest) {
  let payload;
  try {
    payload = JSON.parse(raw.toString("utf8"));
  } catch {
    return runtimeAudioBindingError();
  }
  const classroomId = String(runtime.classroomId || "");
  const classroom = payload?.classroom;
  const idPattern = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;
  const hashPattern = /^[0-9a-f]{64}$/;
  const expectedClassroomHash = String(manifest?.classroomContentSha256 || "");
  const sceneCount = Array.isArray(classroom?.scenes) ? classroom.scenes.length : 0;
  if (
    payload?.success !== true ||
    !classroom ||
    typeof classroom !== "object" ||
    Array.isArray(classroom) ||
    String(classroom.id || "") !== classroomId ||
    !classroom.stage ||
    typeof classroom.stage !== "object" ||
    Array.isArray(classroom.stage) ||
    !Array.isArray(classroom.scenes) ||
    manifest?.ok !== true ||
    manifest?.schemaVersion !== "mira.openmaic.runtime-audio-manifest.v1" ||
    String(manifest.classroomId || "") !== classroomId ||
    !hashPattern.test(expectedClassroomHash) ||
    sceneCount < 1 ||
    sceneCount > 60 ||
    !Number.isInteger(manifest.speechActionCount) ||
    manifest.speechActionCount < 1 ||
    manifest.speechActionCount > 240 ||
    !Array.isArray(manifest.assets) ||
    manifest.assets.length !== manifest.speechActionCount
  ) {
    return runtimeAudioBindingError();
  }

  // The formal audio sidecar was generated from this exact immutable classroom
  // authority using Python json.dumps(..., sort_keys=True, separators=(",",
  // ":"), ensure_ascii=False). canonicalJson applies the same recursive key
  // ordering and compact UTF-8 representation, so unchanged key insertion
  // order cannot affect the digest.
  const actualClassroomHash = createHash("sha256")
    .update(canonicalJson({ stage: classroom.stage, scenes: classroom.scenes }), "utf8")
    .digest();
  if (!timingSafeEqual(actualClassroomHash, Buffer.from(expectedClassroomHash, "hex"))) {
    return runtimeAudioBindingError();
  }

  const bindings = new Map();
  for (const item of manifest.assets) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return runtimeAudioBindingError();
    }
    const sceneId = String(item.sceneId || "");
    const actionId = String(item.actionId || "");
    const audioId = String(item.audioId || "");
    const deliveryPath = String(item.deliveryPath || "");
    const metadata = item.audioMetadata;
    const key = `${sceneId}\n${actionId}`;
    if (
      !idPattern.test(sceneId) ||
      !idPattern.test(actionId) ||
      !idPattern.test(audioId) ||
      deliveryPath !== `/mira/runtime-audio/${audioId}` ||
      !hashPattern.test(String(item.contentHash || "")) ||
      item.mimeType !== "audio/wav" ||
      !Number.isInteger(item.byteSize) ||
      item.byteSize <= 44 ||
      item.byteSize > MAX_RUNTIME_AUDIO_BYTES ||
      !Number.isInteger(item.durationMs) ||
      item.durationMs < 300 ||
      item.durationMs > 120_000 ||
      !metadata ||
      typeof metadata !== "object" ||
      Array.isArray(metadata) ||
      metadata.schemaVersion !== "mira.openmaic.speech-audio.v1" ||
      metadata.providerId !== "qwen-tts" ||
      metadata.modelId !== "qwen3-tts-flash" ||
      !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/.test(String(metadata.voiceId || "")) ||
      metadata.fallbackUsed !== false ||
      bindings.has(key)
    ) {
      return runtimeAudioBindingError();
    }
    bindings.set(key, {
      audioId,
      audioUrl: deliveryPath,
      audioMetadata: {
        schemaVersion: "mira.openmaic.speech-audio.v1",
        providerId: "qwen-tts",
        modelId: "qwen3-tts-flash",
        voiceId: String(metadata.voiceId),
        fallbackUsed: false,
      },
    });
  }

  let speechCount = 0;
  const seenActionIds = new Set();
  for (const scene of classroom.scenes) {
    if (
      !scene ||
      typeof scene !== "object" ||
      Array.isArray(scene) ||
      !idPattern.test(String(scene.id || "")) ||
      !Array.isArray(scene.actions)
    ) {
      return runtimeAudioBindingError();
    }
    let sceneSpeechCount = 0;
    for (const action of scene.actions) {
      if (action?.type !== "speech") continue;
      sceneSpeechCount += 1;
      speechCount += 1;
      if (
        !action ||
        typeof action !== "object" ||
        Array.isArray(action) ||
        !idPattern.test(String(action.id || "")) ||
        seenActionIds.has(String(action.id)) ||
        typeof action.text !== "string" ||
        !action.text.trim()
      ) {
        return runtimeAudioBindingError();
      }
      seenActionIds.add(String(action.id));
      const key = `${scene.id}\n${action.id}`;
      const binding = bindings.get(key);
      if (!binding) return runtimeAudioBindingError();
      if (
        (action.audioId != null && String(action.audioId) !== binding.audioId) ||
        (action.audioUrl != null && String(action.audioUrl) !== binding.audioUrl)
      ) {
        return runtimeAudioBindingError();
      }
      action.audioId = binding.audioId;
      action.audioUrl = binding.audioUrl;
      action.audioMetadata = binding.audioMetadata;
      bindings.delete(key);
    }
    if (sceneSpeechCount < 1 || sceneSpeechCount > 20) {
      return runtimeAudioBindingError();
    }
  }
  if (manifest.speechActionCount !== speechCount || bindings.size !== 0) {
    return runtimeAudioBindingError();
  }
  return Buffer.from(JSON.stringify(payload));
}

async function deliverRuntimeAudio(response, runtime, config, audioId) {
  const upstream = await fetch(
    new URL(
      `/internal/learning/openmaic/runtime/audio/${encodeURIComponent(audioId)}`,
      `${config.backendUrl}/`,
    ),
    {
      method: "GET",
      headers: {
        Accept: "audio/wav",
        ...trustedRuntimeHeaders(runtime),
        "X-Mira-Internal-Token": config.internalToken,
        "X-Mira-Internal-Source": "openmaic-runtime-gateway",
      },
      redirect: "error",
      signal: AbortSignal.timeout(config.backendTimeoutMs),
    },
  );
  if (!upstream.ok) {
    const error = new Error("backend rejected runtime audio");
    error.statusCode = upstream.status === 404 ? 404 : 502;
    error.payload = {
      error:
        upstream.status === 404
          ? "openmaic_runtime_audio_not_found"
          : "openmaic_runtime_audio_unavailable",
      message: upstream.status === 404 ? "课堂音频不存在" : "课堂音频暂时不可用",
    };
    throw error;
  }
  const mimeType = String(upstream.headers.get("content-type") || "")
    .split(";", 1)[0]
    .trim()
    .toLowerCase();
  const expectedHash = String(upstream.headers.get("x-mira-audio-sha256") || "");
  const expectedSize = Number(upstream.headers.get("content-length"));
  if (
    mimeType !== "audio/wav" ||
    !/^[0-9a-f]{64}$/.test(expectedHash) ||
    !Number.isInteger(expectedSize) ||
    expectedSize <= 44 ||
    expectedSize > MAX_RUNTIME_AUDIO_BYTES
  ) {
    return runtimeAudioDeliveryError();
  }
  const bytes = await readFetchBody(upstream.body, MAX_RUNTIME_AUDIO_BYTES);
  if (
    bytes.length !== expectedSize ||
    bytes.subarray(0, 4).toString("ascii") !== "RIFF" ||
    bytes.subarray(8, 12).toString("ascii") !== "WAVE" ||
    createHash("sha256").update(bytes).digest("hex") !== expectedHash
  ) {
    return runtimeAudioDeliveryError();
  }
  response.statusCode = 200;
  response.setHeader("Content-Type", "audio/wav");
  response.setHeader("Content-Length", String(bytes.length));
  response.setHeader("Cache-Control", "private, no-store");
  response.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader("Content-Security-Policy", "default-src 'none';");
  response.end(bytes);
}

function trustedRuntimeHeaders(runtime) {
  return {
    "X-Mira-Runtime-Session": String(runtime.runtimeSessionId),
    "X-Mira-Learning-Session": String(runtime.learningSessionId),
    "X-Mira-Runtime-Classroom-Id": String(runtime.classroomId),
  };
}

function runtimeAudioBindingError() {
  const error = new Error("runtime audio binding invalid");
  error.statusCode = 502;
  error.payload = {
    error: "openmaic_runtime_audio_binding_invalid",
    message: "正式课堂音频装配失败",
  };
  throw error;
}

function runtimeAudioDeliveryError() {
  const error = new Error("runtime audio delivery invalid");
  error.statusCode = 502;
  error.payload = {
    error: "openmaic_runtime_audio_integrity_failed",
    message: "课堂音频完整性校验失败",
  };
  throw error;
}

export function sanitizeRuntimeJson(raw, classroomId, { requireRootStageId = false } = {}) {
  if (!raw?.length) return raw;
  let payload;
  try {
    payload = JSON.parse(raw.toString("utf8"));
  } catch {
    const error = new Error("invalid JSON body");
    error.statusCode = 400;
    throw error;
  }
  if (
    requireRootStageId &&
    (!payload ||
      typeof payload !== "object" ||
      Array.isArray(payload) ||
      String(payload.stageId || "") !== classroomId)
  ) {
    const error = new Error("conversation probe stageId mismatch");
    error.statusCode = 403;
    throw error;
  }
  const clean = scrub(payload, classroomId, new WeakSet());
  return Buffer.from(JSON.stringify(clean));
}

function scrub(value, classroomId, seen) {
  if (Array.isArray(value)) return value.map((item) => scrub(item, classroomId, seen));
  if (!value || typeof value !== "object") return value;
  if (seen.has(value)) throw new Error("cyclic JSON is not allowed");
  seen.add(value);
  const output = {};
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.replace(/[-_]/g, "").toLowerCase();
    if (SECRET_KEYS.has(normalized)) continue;
    if (["classroomid", "stageid"].includes(normalized)) {
      const supplied = String(item || "");
      if (supplied && supplied !== classroomId) {
        const error = new Error("cross-classroom request blocked");
        error.statusCode = 403;
        throw error;
      }
    }
    output[key] = scrub(item, classroomId, seen);
  }
  seen.delete(value);
  return output;
}

async function backendJson(config, path, body, trustedHeaders = {}, method = "POST") {
  const requestOptions = {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...trustedHeaders,
      "X-Mira-Internal-Token": config.internalToken,
      "X-Mira-Internal-Source": "openmaic-runtime-gateway",
    },
    signal: AbortSignal.timeout(config.backendTimeoutMs),
  };
  if (method !== "GET") requestOptions.body = JSON.stringify(body);
  const response = await fetch(new URL(path, `${config.backendUrl}/`), requestOptions);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error("backend rejected runtime request");
    error.statusCode = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function filteredRequestHeaders(source) {
  const headers = new Headers();
  for (const [key, value] of Object.entries(source)) {
    const normalized = key.toLowerCase();
    if (
      value == null ||
      normalized.startsWith("x-mira-") ||
      ["host", "cookie", "authorization", "content-length", "connection"].includes(normalized)
    )
      continue;
    headers.set(key, Array.isArray(value) ? value.join(", ") : String(value));
  }
  return headers;
}

function copyResponseHeaders(source, response, config, decision, pathname) {
  const upstreamCsp = source.get("content-security-policy");
  for (const [key, value] of source.entries()) {
    const normalized = key.toLowerCase();
    if (
      [
        "set-cookie",
        "content-security-policy",
        // Node fetch transparently decodes compressed upstream bodies. Do not
        // tell the browser that the already-decoded stream is still encoded.
        "content-encoding",
        "content-length",
        "x-frame-options",
        "connection",
        "transfer-encoding",
      ].includes(normalized)
    )
      continue;
    if (normalized === "location") {
      const rewritten = rewriteLocation(value, config);
      response.setHeader(key, rewritten);
    } else {
      response.setHeader(key, value);
    }
  }
  response.setHeader(
    "Cache-Control",
    decision.kind === "asset" && !pathname.startsWith("/_next/")
      ? "private, max-age=3600"
      : "no-store",
  );
  response.setHeader("Cross-Origin-Resource-Policy", "same-origin");
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Referrer-Policy", "no-referrer");
  response.setHeader(
    "Permissions-Policy",
    "camera=(), geolocation=(), payment=(), usb=(), microphone=(self)",
  );
  response.setHeader(
    "Content-Security-Policy",
    mergeContentSecurityPolicy(upstreamCsp, studentFrameAncestors(config)),
  );
}

function studentFrameAncestors(config) {
  const origins = new Set([config.studentWebOrigin]);
  if (
    config.localLanProductionMode &&
    isPrivateHttpOrigin(config.publicOrigin) &&
    isPrivateHttpOrigin(config.studentWebOrigin)
  ) {
    // A local student tab must embed the gateway on the same host so its Lax
    // session cookie survives iframe navigation. Only these fixed loopback
    // aliases are added; request Host/Origin headers cannot expand this list.
    for (const hostname of ["localhost", "127.0.0.1"]) {
      const origin = new URL(config.studentWebOrigin);
      origin.hostname = hostname;
      origins.add(origin.origin);
    }
  }
  return [...origins].join(" ");
}

function isPrivateHttpOrigin(value) {
  const url = new URL(value);
  if (url.protocol !== "http:" || url.username || url.password) return false;
  const hostname = url.hostname.toLowerCase();
  if (hostname === "localhost" || hostname === "[::1]") return true;
  if (hostname.startsWith("[fc") || hostname.startsWith("[fd")) return true;
  const octets = hostname.split(".").map(Number);
  if (
    octets.length !== 4 ||
    octets.some((value) => !Number.isInteger(value) || value < 0 || value > 255)
  ) return false;
  return octets[0] === 10 || octets[0] === 127 ||
    (octets[0] === 172 && octets[1] >= 16 && octets[1] <= 31) ||
    (octets[0] === 192 && octets[1] === 168);
}

export function mergeContentSecurityPolicy(source, studentWebOrigin) {
  const directives = String(source || "")
    .split(";")
    .map((value) => value.trim())
    .filter(Boolean)
    .filter((value) => !value.toLowerCase().startsWith("frame-ancestors "));
  const names = new Set(directives.map((value) => value.split(/\s+/, 1)[0].toLowerCase()));
  directives.push(`frame-ancestors ${studentWebOrigin}`);
  if (!names.has("object-src")) directives.push("object-src 'none'");
  if (!names.has("base-uri")) directives.push("base-uri 'self'");
  return `${directives.join("; ")};`;
}

function rewriteLocation(location, config) {
  try {
    const resolved = new URL(location, `${config.upstreamUrl}/`);
    if (
      resolved.origin === new URL(config.upstreamUrl).origin ||
      resolved.origin === new URL(config.publicOrigin).origin
    ) {
      // Preserve the browser's gateway host (including a local loopback alias).
      // A path beginning with // must not become a protocol-relative redirect.
      const pathname = resolved.pathname.replace(/^\/+/, "/");
      return `${pathname}${resolved.search}${resolved.hash}`;
    }
  } catch {}
  return location;
}

async function readBody(request, maxBytes) {
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > maxBytes) {
      const error = new Error("request body too large");
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function readFetchBody(body, maxBytes, fail = runtimeAudioDeliveryError) {
  if (!body) return fail();
  const chunks = [];
  let length = 0;
  for await (const chunk of Readable.fromWeb(body)) {
    length += chunk.length;
    if (length > maxBytes) return fail();
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

function isJsonRequest(request) {
  return String(request.headers["content-type"] || "")
    .toLowerCase()
    .includes("application/json");
}

function readCookie(header, name) {
  for (const part of String(header || "").split(";")) {
    const [rawName, ...rest] = part.trim().split("=");
    if (rawName === name) return decodeURIComponent(rest.join("="));
  }
  return "";
}

function serializeCookie(name, value, { maxAge, secure }) {
  return [
    `${name}=${encodeURIComponent(value)}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    secure ? "Secure" : "",
    `Max-Age=${maxAge}`,
  ]
    .filter(Boolean)
    .join("; ");
}

function unauthorized(response) {
  return json(response, 401, {
    ok: false,
    error: "openmaic_runtime_session_required",
    message: "请从 Mira 学生学习空间进入课堂",
  });
}

function methodNotAllowed(response) {
  return json(response, 405, {
    ok: false,
    error: "method_not_allowed",
    message: "请求方式不受支持",
  });
}

function json(response, status, payload) {
  response.statusCode = status;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(JSON.stringify(payload));
}

function gatewayConfig(overrides) {
  const config = {
    port: Number(overrides.port ?? process.env.PORT ?? 3101),
    upstreamUrl: String(
      overrides.upstreamUrl ?? process.env.OPENMAIC_UPSTREAM_URL ?? "http://127.0.0.1:3100",
    ).replace(/\/$/, ""),
    backendUrl: String(
      overrides.backendUrl ?? process.env.MIRA_BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000",
    ).replace(/\/$/, ""),
    publicOrigin: String(
      overrides.publicOrigin ?? process.env.MIRA_RUNTIME_PUBLIC_ORIGIN ?? "http://127.0.0.1:3101",
    ).replace(/\/$/, ""),
    studentWebOrigin: String(
      overrides.studentWebOrigin ?? process.env.MIRA_STUDENT_WEB_ORIGIN ?? "http://127.0.0.1:3000",
    ).replace(/\/$/, ""),
    internalToken: String(overrides.internalToken ?? process.env.MIRA_INTERNAL_API_TOKEN ?? ""),
    secureCookie: Boolean(overrides.secureCookie ?? process.env.NODE_ENV === "production"),
    localLanProductionMode:
      String(overrides.localLanProductionMode ?? process.env.MIRA_LOCAL_LAN_PRODUCTION_MODE) === "1",
    maxBodyBytes: Number(
      overrides.maxBodyBytes ?? process.env.MIRA_RUNTIME_MAX_BODY_BYTES ?? DEFAULT_MAX_BODY_BYTES,
    ),
    backendTimeoutMs: Number(overrides.backendTimeoutMs ?? 10_000),
    upstreamTimeoutMs: Number(overrides.upstreamTimeoutMs ?? 300_000),
    sourceVersion: "openmaic@1.0.0",
  };
  for (const [label, value] of [
    ["OPENMAIC_UPSTREAM_URL", config.upstreamUrl],
    ["MIRA_BACKEND_INTERNAL_URL", config.backendUrl],
    ["MIRA_RUNTIME_PUBLIC_ORIGIN", config.publicOrigin],
    ["MIRA_STUDENT_WEB_ORIGIN", config.studentWebOrigin],
  ]) {
    const parsed = new URL(value);
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
      throw new Error(`${label} must be a credential-free HTTP(S) URL`);
    }
  }
  if (config.secureCookie) {
    for (const [label, value] of [
      ["MIRA_RUNTIME_PUBLIC_ORIGIN", config.publicOrigin],
      ["MIRA_STUDENT_WEB_ORIGIN", config.studentWebOrigin],
    ]) {
      if (new URL(value).protocol !== "https:") {
        throw new Error(`${label} must use HTTPS in production`);
      }
    }
  }
  if (!config.internalToken) throw new Error("MIRA_INTERNAL_API_TOKEN is required");
  return config;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const server = createGateway();
  const port = Number(process.env.PORT || 3101);
  server.listen(port, "0.0.0.0", () => {
    process.stdout.write(`Mira OpenMAIC runtime gateway listening on ${port}\n`);
  });
}
