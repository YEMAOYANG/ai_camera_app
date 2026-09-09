# Mira full OpenMAIC classroom runtime

This directory integrates the complete self-hosted OpenMAIC classroom with Mira. It is intentionally separate from `backend/openmaic-sidecar`, which remains a narrow generation contract. The full runtime supplies slides, interactive HTML simulations and games, PBL, multi-agent discussion, whiteboard actions, teacher playback actions, media and optional MP4 export.

## Ownership boundary

```text
Mira
  student identity / parent authorization
  catalog release and child visibility
  deterministic answers, reports and mastery
  teacher preference and reviewed narration assets
  one-time classroom launch tickets

OpenMAIC full runtime
  Stage / Scene / Action playback
  slides and 3D or HTML interactive scenes
  PBL and multi-agent classroom dialogue
  real-time whiteboard and teacher actions
  optional Chromium + FFmpeg MP4 rendering
```

Students never receive the OpenMAIC editor, provider settings, API keys or an unrestricted classroom URL. They enter through the gateway with a 60-second, single-use Mira ticket. The gateway binds its HttpOnly runtime cookie to one student, one Mira learning session and one released classroom.

OpenMAIC-generated quiz feedback is formative. Mira's backend remains the authority for final assessment and mastery.

## Pinned upstream

`upstream.lock.json` pins OpenMAIC `1.0.0` at commit `aa2bfb3c1d406c47100c6744d90e788abdf1f6d5` under the MIT license. The bootstrap script verifies the commit, license, patch count, latest patch name, and latest patch SHA-256 before replaying the ordered patch chain in `patches/`. The chain covers the headless VoxCPM compatibility layer, deterministic Qwen TTS/ASR identities, sample recovery attestations, the isolated Mira student-classroom chrome, request-id-idempotent formal candidate generation, private formal audio and Runtime event boundaries, production Node/Edge/client boundaries, bounded Provider timeouts, the low-disk local Runtime cache policy, session-authoritative student audio refresh, OpenMAIC-owned formal audio lifecycle receipts, student-safe audible output, stable session-local playback state, refresh-safe classroom resume, resumable completion evidence, the OpenMAIC-owned adaptive professional courseware authority, bounded rate-limit handling for mandatory web research, and the DeepSeek professional creator/verifier split.

The local test runtime uses Next.js Webpack development mode. This keeps the
rebuild cache bounded on low-disk developer Macs while preserving the same
reviewed OpenMAIC source and Runtime gateway contract.

Patch `0022` pins Kimi inside OpenMAIC for courseware phases and compiles the locked teaching brief into the final 5/2/3 classroom deterministically, so the backend never performs a second model generation. Patch `0023` upgrades only allowlisted DashScope OSS audio URLs from HTTP to HTTPS before the private formal-audio download. Patch `0024` keeps English as the subject language while requiring Chinese instruction speech and Chinese ASR for mixed Chinese-English lessons. Patch `0025` accepts the leading hyphen or underscore emitted by OpenMAIC nanoid classroom identities without weakening the bounded identifier grammar. Patch `0026` keeps Docker standalone builds intact while native `next start` builds omit the unused standalone copy, preventing runtime audio from being duplicated into a multi-gigabyte local artifact. Patch `0027` applies the same allowlisted HTTPS upgrade to release-readiness TTS receipts and provides a one-shot audited continuation from call 3, preserving successful Kimi and ASR receipts instead of paying for them again. Patch `0028` keeps already-generated narration playback and volume controls independent of Provider TTS settings, prevents formal audio failures from falling through to browser TTS, and reports a controlled text-continuation fallback to the classroom UI. Patch `0029` completes the truncated Provider-readiness source and test endings from `0027`, so a clean bootstrap preserves the full reviewed health assertion and valid TypeScript syntax. Patch `0030` reuses one locally derived Provider proof for both the completed receipt and recovery audit, and replaces the test's CommonJS crypto lookup with a static Node import; it changes neither Provider calls nor business state. None of these patches enables voice cloning or adds credentials.

Patch `0033` makes OpenMAIC own the complete formal classroom audio lifecycle: ten deterministic Qwen TTS assets and ten Qwen ASR checks must succeed before the generation job returns its `formalAudio` receipt. It also adds an explicit student “开始上课” audio gesture and same-sentence retry so Chromium cannot silently skip narration. Existing published audio remains compatible and no target fingerprint changes.

Patch `0034` gives the student classroom session-local 100% audio defaults, unlocks a dedicated browser audio graph from the “开始上课” gesture, and applies a bounded +6 dB gain with a limiter only to private formal-runtime narration. If Web Audio is unavailable or blocked, native HTML audio remains the fallback. Mute, volume, discussion speech, and resume-failure recovery share the same student controls; no Provider call, database contract, or course fingerprint changes.

Patch `0035` keeps the one-time “开始上课” acceptance above playback-chrome remounts, turns an individual audio failure into a local pause-and-retry instead of reopening the gate, blocks editor generation/media recovery in student routes, and makes student classroom/editor state memory-only. Student progress remains authoritative through Runtime events; expired gateway audio URLs and editor Web Locks are no longer involved in LAN playback. The patch changes no Provider call, generated classroom bytes, database contract, or course fingerprint.

Patch `0036` remembers the accepted audio gate per classroom in the current tab session and recognizes an existing saved playback position, so refreshing or reopening a started classroom restores its cursor without presenting the lesson as new. Playback remains paused after refresh because browsers may revoke autoplay privilege; the normal play control re-unlocks the audio graph and a non-blocking notice explains how to continue. A genuinely new classroom still uses the one-time full-screen gesture, while a restored classroom asks for any renewed browser gesture only through the normal play control. The patch changes no Provider call, generated classroom bytes, database contract, or course fingerprint.

Patch `0037` arms student narration when an already-started lesson moves to a manually selected quiz or interactive scene while auto-play remains enabled. This ensures every reviewed scene can emit its locked completion action instead of leaving the backend at the intentional 95% safety cap. The backend separately aggregates only identity-matched scene/action evidence and authoritative answers across legitimate re-entry to the same learning session; all 10 scenes, all 10 locked completion actions, and all required answers remain mandatory.

Patch `0038` replaces the formal fixed-template compiler with an isolated OpenMAIC Pro Agent job. A parent grade selection still reserves course preparation asynchronously; the backend supplies the complete answer-blind brief, so the Agent never asks for user input. The job loads the Mira, K12 planning, and deep-interactive Skills, requires one to four server-managed web searches plus a same-session source fetch, records citation evidence, and promotes the PostgreSQL Stage into the student classroom store only after the exact 10-scene, roster, assessment, interaction, research, and audio gates pass.

Patch `0039` supersedes the fixed page-count and fixed 5/2/3 layout in `0038`. The OpenMAIC Pro Agent now plans an adaptive deck from the settled teaching brief, grade, bounded skill and requested or inferred duration, without asking a parent or learner for another prompt. The formal gate accepts one through sixty scenes, requires slide, quiz and interactive coverage, permits PBL when appropriate, distributes the four locked questions across one to four quiz pages in order, and lets each interaction choose its content-appropriate widget. Research, citations, the one-teacher/four-peer roster, one through twenty speech actions per scene (up to 240 per classroom), slide focus/explanation sequences, widget evidence and fail-closed quality rules remain mandatory. A slide must contain at least one renderable spotlight target and at least one sequence of one or more spotlights immediately followed by an explanation; opening, transition and closing speech may remain unfocused, matching official OpenMAIC classroom behavior. Formal Qwen audio and ASR receipts flatten the actual speech actions in scene/action order and use the existing `sceneOrder` field as the global speech-segment ordinal.

Patch `0040` retries one explicit Kimi courseware HTTP 429 within the same bounded request timeout. Patch `0041` serializes the keyless Brave HTML search fallback, spaces request starts by at least one second, and retries one HTTP 429 using a bounded `Retry-After`. API-key search behavior and the fail-closed research requirement are unchanged.

Patch `0042` replaces the courseware-only Kimi binding with a fail-closed DeepSeek policy. DeepSeek V4 Pro owns the professional Agent, research-query rewrite, courseware creation, and structured scenes; DeepSeek V4 Flash is isolated to independent verification and verification after repair. JSON-producing calls disable thinking, Agent reasoning remains enabled, and formal health publishes the exact creator/verifier policy without exposing credentials.

The current `deepseek-v4-pro-flash-v1` policy supersedes the historical Kimi
courseware bindings above. DeepSeek V4 Pro owns the professional Agent and all
courseware creation; DeepSeek V4 Flash performs independent verification and
verification after repair. Search-query rewriting stays on Pro with thinking
disabled. Strict JSON creation and verification calls disable thinking, while
the Pro Agent retains its professional reasoning policy. No
`KIMI_*` value is injected into the courseware process. The existing default-on
Brave research, source fetch, and citation gates are unchanged.

## OpenMAIC v1 professional workbench and Skills

The pinned v1 source keeps OpenMAIC's professional workbench, editable Stage/Scene
workflow, built-in Skills, and operator-facing generation UI. Mira adds the
`mira-primary-courseware` Skill for deliberate operator course creation. It sets
the early-primary quality bar: one teaching move per page, a concrete visual
scaffold, meaningful learner action, progressive spotlight targets, reviewed
narration, and a completion gate that rejects missing audio or fake interaction.

This professional surface is not the student classroom. Students still receive
only the released playback runtime through the gateway and can never open Pro
editing, Skill management, provider settings, or unrestricted generation.

Web search remains split by trust boundary. It is mandatory by default for the
server-authored formal catalog workflow and unavailable in student playback.
The Mira Skill limits a course to one through four precise searches, requires at
least one result to be fetched into the same durable Agent session, prefers
primary educational sources, and requires a visible source title or domain in
the pages that use researched facts. Missing search, fetch, or citation evidence
fails the job closed instead of publishing an offline or invented result.

```bash
cd openmaic-runtime
./scripts/bootstrap-upstream.sh
cp .env.example .env
```

Fill the server-owned model/provider configuration in `.env`. Keep
`MIRA_OPENMAIC_MODEL_PROVIDER=deepseek`, the Pro creator model, the Flash
verifier model, and both entries in `DEEPSEEK_MODELS`; add only the private
DeepSeek key. Do not copy browser keys or student tokens into this file.

## Start locally

Patch `0058` adds an explicit local recovery path for an existing terminal
professional Stage. It preserves the original failed job, exact source hashes,
locked questions, review-attempt ledger and Provider dispatch records. It does
not create another Agent. The saved course must still pass research, Skills,
independent teaching review, both browser sizes, media and every TTS/ASR gate.
The reviewer selects source evidence IDs; the server derives the summary from
all seven dimension decisions. Invalid older reviews remain rejected.

`operator/run-saved-stage.sh prepare|inspect|complete <manifest.json>` runs the
saved-stage operator with the same private configuration as the managed stack.
Only a browser rejection with no Provider dispatch can complete its existing
review slot. `repair-audio` permits one recorded `.repair1` child dispatch for a
proven bad or ambiguous narration, retaining original records in a promotion
journal. `complete-audio-tail` requires that repair and a cached passed teaching
review; its Provider hook forbids another teaching-review call. These are
explicit operator commands, never student polling or automatic retries.

The professional Agent driver now reserves each model turn durably before
dispatch: at most 48 turns per session, 8,000,000 cumulative serialized input
characters for newly tracked turns and 16,384 output tokens per turn, with SDK
retries disabled. Old recorded turns consume the turn allowance. This is an
Agent-driver allowance, not a currency limit; separate content, verification,
media and publication budgets still apply.

After recovery, `backend/scripts/resume_saved_formal_course.py` reconciles only
the same upstream request and drains the existing publication gates. It cannot
start content or another classroom. A successful recovery is an audited repair
of previously generated courseware, not evidence of a fresh automatic run.

Patch `0045` reconnects a running formal classroom job to its original durable
professional Agent after a runtime restart. A PostgreSQL owner lock excludes
concurrent completion, and the original request hash and dispatch marker remain
mandatory. Existing TTS/ASR receipts are reused by the audio lifecycle. Polling
never creates a replacement Agent or job; the backend only reopens a transport
quarantine when that same upstream job has an authoritative completed result.

1. Apply backend migrations through `071_learning_deepseek_courseware_policy.sql`.
2. Set the same private `INTERNAL_API_TOKEN` in the backend and `MIRA_INTERNAL_API_TOKEN` in `openmaic-runtime/.env`.
3. Start the Mira backend on port 8000.
4. Start OpenMAIC and its gateway:

```bash
cd openmaic-runtime
docker compose up --build openmaic gateway
```

To add server-side MP4 export:

```bash
docker compose --profile video-export up --build openmaic gateway render-service
```

The upstream admin port is bound only to `127.0.0.1:3100`. Students use the gateway on `:3101`. In production, put the gateway behind HTTPS on a same-site classroom subdomain and keep the upstream port private.

### Native development start without Docker

Docker is not required for local UI and playback development. The pinned
upstream targets Node 22; Node 25 also works when its experimental server-side
Web Storage is disabled so it cannot be mistaken for browser `localStorage`.

The repeatable local command starts both processes with courseware model
credentials read only from `openmaic-runtime/.env`, stores PID files and logs
under `/tmp/mira-openmaic-runtime`, and reads the backend-owned gateway token,
Agent database, search, and audio settings separately from `backend/.env`:

```bash
cd openmaic-runtime
./scripts/native-runtime.sh start
./scripts/native-runtime.sh status
./scripts/healthcheck.sh
# ./scripts/native-runtime.sh stop
```

```bash
cd openmaic-runtime
./scripts/bootstrap-upstream.sh

cd .runtime/OpenMAIC
NPM_CONFIG_MANAGE_PACKAGE_MANAGER_VERSIONS=false pnpm install --frozen-lockfile

NODE_OPTIONS=--no-experimental-webstorage \
NEXT_PUBLIC_MAIC_EDITOR_ENABLED=false \
NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=false \
NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
NEXT_PUBLIC_PI_CHAT_ENABLED=true \
NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=false \
NEXT_PUBLIC_ENABLE_PPTX_IMPORT=false \
ALLOWED_FRAME_ANCESTORS=http://127.0.0.1:3000 \
NPM_CONFIG_MANAGE_PACKAGE_MANAGER_VERSIONS=false \
pnpm dev --hostname 127.0.0.1 --port 3100
```

This command intentionally starts with no model provider. It is sufficient to
load the upstream UI and play an already persisted classroom, but the strict
Mira health preflight rejects it and it cannot generate a new classroom.
Approved Mira generation is fixed to
DeepSeek V4 Pro for professional creation and DeepSeek V4 Flash for independent
verification. The server-owned `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and
`DEEPSEEK_MODELS` values live only in `openmaic-runtime/.env`; the native helper
rejects other model IDs and never places provider configuration in the backend,
Parent App, or Student Web.

The native runtime also supports `DEEPSEEK_SERVICE=bailian` while retaining the
official credential unchanged. The private `BAILIAN_DEEPSEEK_API_KEY` and
`BAILIAN_DEEPSEEK_BASE_URL` select the Beijing service; the HTTP adapter maps
Pro/Flash to `deepseek-v4-pro-0813` / `deepseek-v4-flash-0731` and converts the
thinking parameter. Enable free-quota-only for both dated models in the cloud
console before setting `BAILIAN_DEEPSEEK_FREE_TIER_ONLY_CONFIRMED=1`. There is
no automatic paid fallback. See [switching runbook](../docs/runbooks/deepseek-bailian-switch.md)
for the manual official rollback and the native-only scope of this selector.

### Native production build and foreground start

The formal runtime must use a prebuilt Next.js artifact rather than `next dev`
or HMR. Build it once, then let the process supervisor own the production
foreground command:

```bash
cd openmaic-runtime
./scripts/native-runtime.sh build-openmaic-production

MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 \
MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 \
MIRA_OPENMAIC_ENABLE_QWEN_ASR=1 \
./scripts/native-runtime.sh foreground-openmaic-production
```

`build-openmaic-production` replays the pinned patch chain and requires the
installed dependencies, then runs the upstream vendor assertion and `next
build` with `NODE_ENV=production`. Its child environment is empty except for
basic process settings, the validated credential-free Student Web origin, and
the six script-owned `NEXT_PUBLIC_*` feature flags. It neither loads nor
forwards model, TTS, ASR, recovery, internal-token, persistence-token, or other
caller-provided `NEXT_PUBLIC_*` values, so Provider credentials cannot be
written into `.next` or emitted by the build. Because Next.js automatically
loads project dotenv files, the command also fails closed if `.env`,
`.env.local`, `.env.production`, or `.env.production.local` exists inside the
pinned OpenMAIC source tree; server credentials stay in the separate
`openmaic-runtime/.env` read only by the production start command.

`foreground-openmaic-production` fails closed unless `.next/BUILD_ID` is
present and non-empty. It executes `next start` with `NODE_ENV=production` and
reuses the same strict DeepSeek V4 Pro/V4 Flash model policy, Qwen TTS, Qwen
ASR, deterministic recovery, internal-token, origin, and clean
child-environment loaders as the reviewed development foreground path.
Readiness remains authoritative only after the existing root, formal-audio,
and formal-provider-readiness health contracts pass. The native `start` and
`restart` commands also require and serve the reviewed production artifact.
`foreground-openmaic` remains the explicit direct-upstream development entry
point for source work; it must not be placed behind the student gateway because
its HMR client is intentionally blocked there.

### Durable local classroom stack

The child-facing stack also serves Student Web from a production artifact. The
launcher rebuilds it only when the recorded source/config/dotenv fingerprint,
installed Next.js version, or `.next/BUILD_ID` changes, then runs Next.js 16.3
with `next start`. This keeps the outer `:3000` page free of Fast Refresh/HMR
during long classroom sessions.

```bash
cd openmaic-runtime
./scripts/local-test-stack.sh build-student-web-production
./scripts/local-test-stack.sh start
./scripts/local-test-stack.sh status
# ./scripts/local-test-stack.sh stop
```

`start` performs the same stale-build check, so it does not rebuild on every
launch. On the first upgraded run it accepts only the strict v1
PID/start-time/cwd/root-command/listener identity previously written by this
script for `next dev`, stops that exact process, builds with port 3000 empty,
and publishes a v2 pending-to-production identity. Unknown listeners are never
adopted or killed. Current health additionally binds the exact Next version,
BUILD_ID hash, every port-3000 listener, and HTTP readiness. BUILD_ID/source
drift makes status fail but does not prevent safely stopping the recorded
instance.

The local build/start environment sets `MIRA_LOCAL_LAN_PRODUCTION_MODE=1`. The
flag is intentionally scoped to this LAN launcher so private/loopback HTTP PIN
cookies and the OpenMAIC microphone origin work during local hardware testing;
public production deployments retain the normal HTTPS-only policy.

The same flag reaches the gateway. With private HTTP student/runtime origins,
the student launch response and exact frame/microphone allowlists support
`localhost` and `127.0.0.1` alongside the configured LAN address. Gateway
redirects retain the browser's host, so the host-only `HttpOnly; SameSite=Lax`
runtime cookie remains usable inside the classroom iframe. Request headers
cannot add arbitrary origins to these allowlists.

For Mira's native helper, each server provider is an explicit per-start opt-in.
It reads only allowlisted model Provider values from the OpenMAIC-owned
`openmaic-runtime/.env`, maps them into the private OpenMAIC process, and never
sources or prints the dotenv file. `MIRA_OPENMAIC_PROVIDER_ENV_FILE` applies
only to non-model capabilities and cannot redirect DeepSeek credential loading.
The backend remains the business-orchestration owner but never stores the
DeepSeek key or model routing:

```bash
# Report only provider/model/voice availability; no secret values are printed.
MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 ./scripts/native-runtime.sh provider-status

# Strict generation readiness. The OpenMAIC dotenv must provide the reviewed
# DeepSeek V4 Pro/V4 Flash identities; speech still requires reviewed Qwen identities.
MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 \
MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 \
MIRA_OPENMAIC_ENABLE_QWEN_ASR=1 \
./scripts/native-runtime.sh restart
```

The Qwen key can be supplied as a capability-specific `TTS_QWEN_API_KEY` or
`ASR_QWEN_API_KEY`, or as a shared `DASHSCOPE_API_KEY`/`QWEN_API_KEY`. Use the
direct upstream development command above for credential-free playback. The
native helper's `start`/`status` contract is generation-ready and therefore
requires the exact Qwen TTS and Qwen ASR policies. A flag must be exactly `0`
or `1`; a missing credential or an unreviewed model/voice fails before either
service is reported healthy.

The native helper and Docker Compose inject the fixed policy
`deepseek-v4-pro-flash-v1`. The `maic-agent-driver` uses DeepSeek V4 Pro with
the professional reasoning policy. `generate-classroom` and all structured
`scene-content` stages use V4 Pro with
`thinking={mode:"disabled",enabled:false}` so strict JSON stays deterministic.
The matching formal contract is
`mira.openmaic.formal-runtime.v4-deepseek-professional`.
Only `independent_verification` and `verification_after_repair` use V4 Flash.
The bounded search-query rewrite stays on V4 Pro with thinking disabled. Arbitrary caller
`MODEL_ROUTES` values are not forwarded by either Mira launcher; the launchers
construct only this reviewed route set.

`GET /api/health` is also the credential-free preflight for these policies. It
resolves and validates every protected stage through `getStageRoute`; a missing
or unsupported policy ID, or any route/model/thinking mismatch, returns HTTP
503. A healthy response exposes this exact contract and never includes provider
keys or base URLs. The formal candidate scope additionally requires the
configured DeepSeek V4 Pro creator and V4 Flash verifier, exposes the adaptive
one-through-sixty-scene professional contract, and reports
`speechAudioGenerated=true`. Default-on server-managed web search still
requires authoritative sources, a same-session fetch, and citations. The same
scoped payload attests
`studentRuntimeEvents.schemaVersion=mira.openmaic.student-runtime-events.v1`,
`studentRuntimeEvents.classroomAuthoritySchema=mira.openmaic.runtime-event-authority.v1`,
the `/mira/runtime-events` gateway endpoint, backend-only authority, and explicit
rejection of client identity and score fields. Formal generation accepts `runtimeRequestId`,
persists the canonical input digest, supports query/replay by that key, and
rejects `enableTTS=true`; speech audio is deliberately deferred to the
backend's later voice stage.

The same root health payload attests the persistence instrumentation boundary:
`runtimePolicy.instrumentationBoundary.nodeRuntimeOnly=true`,
`edgeBundle="excluded"`, `collector="asset-collector-schedule"`, and
`serverExternalPackages=["@openmaic/storage","pg"]`. The Edge/general
instrumentation entry does not import the Node-only collector graph; Node
instrumentation retains the collector startup path.

Formal production narration is a separate private sidecar contract and does
not change the Task-13 classroom bytes or set `enableTTS=true`. The scoped
preflight is `GET /api/health?scope=formal-audio`; the TTS and ASR job routes
are `POST/GET /api/mira/formal-audio/tts` and
`POST/GET /api/mira/formal-audio/asr`. They accept only a direct loopback
request on port `3100` with the server-owned internal token. A backend client
must send this exact header topology:

```http
Host: 127.0.0.1:3100
X-Forwarded-Host: 127.0.0.1:3100
X-Forwarded-For: 127.0.0.1
X-Forwarded-Proto: http
X-Forwarded-Port: 3100
X-Mira-Internal-Token: ...
```

The TTS POST body contains the request, classroom-content hash, subject,
teacher-profile id/version/hash/gender, scene/action/segment identity, text and
text hash. Runtime derives the Provider, model, voice, language and fallback
policy: Chinese uses Serena, the male math teacher uses Ethan, and English uses
Jennifer. `GET /tts?requestId=...&download=1` returns only the locally stored
`audio/wav`. The ASR POST body binds to the same identities plus the successful
TTS request and audio hash; it cannot provide an audio URL or base64 payload. A
successful ASR response uses `state=succeeded` and `transcriptSha256`; only the
first POST response carries the ephemeral raw `transcript`. Runtime never
persists that transcript or a Provider response.

Formal publication uses a second private proof boundary after audio validation:
`POST/GET /api/mira/formal-provider-readiness` and
`GET /api/health?scope=formal-provider-readiness`. They use the same exact
loopback/internal-token topology as formal audio. The request binds one build
item and Runtime classroom to an auto-validated Task-14 audio-job receipt, one
auto-validated local validation WAV receipt, and the legacy route/session proof.
The route/session proof remains explicitly `providerCall=false` and cannot be
used as the Provider receipt.

Runtime writes the readiness job before dispatch and writes each attempted call
before its fetch. It then makes exactly five fixed, server-owned calls: one
authenticated DeepSeek V4 Pro text turn, one Qwen `qwen3-asr-flash` turn over
the bound local WAV, and Qwen `qwen3-tts-flash` turns for Serena (Chinese),
Ethan (Math), and Jennifer (English). Caller Provider/model/voice/key/base-URL,
fallback, audio-URL, base64, and Provider-proof fields are rejected. A changed
idempotent body conflicts; a timeout, lost response, or stale running job is
`ambiguous` and never automatically retried. Only hashes, fixed identities,
counts, timestamps, safe state, and contract versions persist—never keys, raw
Provider bodies, chat output, transcripts, audio, media URLs, or base64.

Each formal-audio job writes its Provider attempt with an exclusive local record before the
single Provider fetch. A replay with the same canonical body returns the same
receipt, a changed body conflicts, and a timeout, lost response or stale
running job becomes `ambiguous` without retry. Provider synthesis, media
download and ASR each have one 120-second ceiling. Media downloads require an
HTTPS credential-free allowlisted Aliyun host, public DNS addresses, bounded
redirects, exact `audio/wav`, and at most 16 MiB before atomic local write and
readback.

```json
{
  "capabilities": { "tts": true, "asr": true },
  "runtimePolicy": {
    "tts": {
      "enforced": true,
      "providerId": "qwen-tts",
      "modelId": "qwen3-tts-flash",
      "voiceId": "Serena"
    },
    "asr": {
      "enforced": true,
      "providerId": "qwen-asr",
      "modelId": "qwen3-asr-flash",
      "fallbackAllowed": false
    },
    "structuredScene": {
      "enforced": true,
      "policyId": "deepseek-v4-pro-flash-v1",
      "providerId": "deepseek",
      "modelId": "deepseek-v4-pro",
      "stages": [
        "scene-content",
        "scene-content:slide",
        "scene-content:quiz",
        "scene-content:interactive",
        "scene-content:pbl"
      ],
      "thinking": { "mode": "disabled", "enabled": false }
    },
    "modelPolicy": {
      "schemaVersion": "mira.openmaic.professional-model-policy.v1",
      "policyId": "deepseek-v4-pro-flash-v1",
      "agentDriver": {
        "providerId": "deepseek",
        "modelId": "deepseek-v4-pro",
        "thinking": { "mode": "enabled", "enabled": true, "effort": "high" }
      },
      "coursewareCreator": {
        "providerId": "deepseek",
        "modelId": "deepseek-v4-pro",
        "thinking": { "mode": "disabled", "enabled": false }
      },
      "coursewareVerifier": {
        "providerId": "deepseek",
        "modelId": "deepseek-v4-flash",
        "thinking": { "mode": "disabled", "enabled": false }
      },
      "structuredScene": {
        "policyId": "deepseek-v4-pro-flash-v1",
        "providerId": "deepseek",
        "modelId": "deepseek-v4-pro",
        "thinking": { "mode": "disabled", "enabled": false }
      },
      "fallbackAllowed": false
    },
    "studentChrome": {
      "enforced": true,
      "policyVersion": "mira-student-chrome.v6",
      "marker": "mira=1",
      "locale": "zh-CN",
      "theme": "light",
      "autoPlayDefault": true,
      "autoPlayPersistence": "student-session",
      "audioStartPersistence": "classroom-tab-session",
      "manualAutoPlayToggleEnabled": true,
      "asrEnabled": true,
      "asrPersistence": "student-session",
      "manualAsrToggleEnabled": false,
      "operatorAsrPreferencePreserved": true,
      "operatorChromePreserved": true,
      "headerControlsHidden": true,
      "exportsHidden": true,
      "teacherIdentity": {
        "agentId": "mira-sample-teacher",
        "avatar": "/avatars/teacher-2.png"
      }
    },
    "instrumentationBoundary": {
      "nodeRuntimeOnly": true,
      "edgeBundle": "excluded",
      "collector": "asset-collector-schedule",
      "serverExternalPackages": ["@openmaic/storage", "pg"]
    }
  }
}
```

The native `start` and `status` probes accept OpenMAIC as generation-ready only
when the exact TTS identity, ASR identity, creator/verifier model policy,
structured-scene contract, and student-chrome attestation above are present.
Playback-only deployments can still query the upstream endpoint, but they are
not reported as ready for Mira's paid generation path.

### Stable macOS development stack

For a long generation run, do not rely on a terminal-owned `nohup` process.
The managed helper installs three user LaunchAgents so macOS launchd directly
owns the backend (`:8000`), private production OpenMAIC (`:3100`), and student
gateway (`:3101`). They remain alive after the invoking shell or Codex turn
exits and are restarted by launchd if a service crashes.

```bash
cd openmaic-runtime
./scripts/managed-dev-stack.sh install  # writes plists only; starts nothing
./scripts/managed-dev-stack.sh start
./scripts/managed-dev-stack.sh status
./scripts/managed-dev-stack.sh stop
# ./scripts/managed-dev-stack.sh uninstall
```

`start`, `status`, and `stop` are idempotent. The generated plists contain only
fixed paths, service labels, a tool path, and log paths. Provider credentials
and the internal gateway token are never copied into a plist or command line:
the foreground service entry points read the existing OpenMAIC-owned
`openmaic-runtime/.env` at process start and inject only allowlisted values into
the private process environment. Logs are stored under
`/tmp/mira-managed-dev-stack` and status output never dumps an environment.

The helper starts the prebuilt OpenMAIC production runtime in the reviewed
DeepSeek V4 Pro/V4 Flash + Qwen3-TTS + Qwen3-ASR mode,
but it does not change the backend generation flag, submit a generation job,
or run a migration. Generation remains controlled by the backend's explicit
authorization contract.

Slide, quiz, and interactive scene generation retain only safe completion
metadata (`finishReason`, output/reasoning/text token counts and text length).
When their parser returns no scene content after the provider reports `length`
or reaches the 8192 output window, generation fails once with the stable code
`structured_output_exhausted`; it does not repeat the same four-minute call six
times. Prompts, generated text, reasoning content, response bodies, headers and
keys are never included in this diagnostic. A result that parses successfully
is accepted even if it ended exactly at the output boundary.

PBL has its own single-call planner, targeted retry and loop fallback. The
server-controlled thinking route applies to PBL, but the direct fail-fast
side-channel described above covers the ordinary slide/quiz/interactive
`AICallFn` path; it does not claim to replace PBL's internal failure policy.

Strict TTS pins the teacher voice binding to
`qwen-tts/qwen3-tts-flash/Serena` for both generated lecture audio and live
classroom discussion. The controlled sample roster separately fixes the visible
teacher name and avatar. Every generated `speech` action must carry a readable,
non-empty audio file plus:

```json
{
  "audioMetadata": {
    "schemaVersion": "mira.openmaic.speech-audio.v1",
    "providerId": "qwen-tts",
    "modelId": "qwen3-tts-flash",
    "voiceId": "Serena",
    "fallbackUsed": false
  }
}
```

The generated teacher roster entry carries
`voiceConfig={providerId,modelId,voiceId}` with the same identity. If one
speech action lacks audio or provenance, the async generation job fails instead
of being marked successful. No browser/native or alternate-provider fallback is
accepted by this strict contract.

Student voice input is likewise fixed to
`qwen-asr/qwen3-asr-flash` with `fallbackAllowed=false`. A gateway-attested
Mira runtime request may submit only the recorded audio and language to
`POST /api/transcription`; another provider/model or any client key/base URL is
rejected before the provider call. The classroom recorder ignores a local
browser-native selection and uploads to the server-owned Qwen route. Provider
errors are generalized for the student response and are not logged with their
raw secret-bearing details.

Start the gateway in another terminal. `MIRA_INTERNAL_API_TOKEN` must equal the
backend's private `INTERNAL_API_TOKEN`, but is supplied through the process
environment rather than committed to this directory:

```bash
cd openmaic-runtime/gateway
PORT=3101 \
OPENMAIC_UPSTREAM_URL=http://127.0.0.1:3100 \
MIRA_BACKEND_INTERNAL_URL=http://127.0.0.1:8000 \
MIRA_RUNTIME_PUBLIC_ORIGIN=http://127.0.0.1:3101 \
MIRA_STUDENT_WEB_ORIGIN=http://127.0.0.1:3000 \
MIRA_INTERNAL_API_TOKEN="$INTERNAL_API_TOKEN" \
npm start
```

Backend configuration:

```dotenv
OPENMAIC_FULL_RUNTIME_ENABLED=1
OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED=0
OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS=20
OPENMAIC_FULL_RUNTIME_INTERNAL_URL=http://127.0.0.1:3100
OPENMAIC_FULL_RUNTIME_PUBLIC_URL=http://127.0.0.1:3101
OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS=300
OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS=60
OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS=14400
OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED=1
LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED=1
```

Keep `OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED=0` until sending course metadata to the configured external model provider has been explicitly approved. Playback of already released classrooms can remain enabled independently.

`LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED=1` is also required because a full
runtime is always bound to the already published Mira LessonPackage pinned by
the student's learning session. Enabling the OpenMAIC runtime alone never
bypasses the Mira catalog, media or pronunciation release gates.

## Internal generation contract

```http
POST /internal/learning/openmaic/classrooms/generate
X-Mira-Internal-Token: ...
Content-Type: application/json

{
  "requestId": "runtime-primary-1-chinese-pinyin-v1",
  "courseId": "course-id",
  "courseVersion": "1",
  "features": [
    "slides",
    "video",
    "3d_visualization",
    "simulation",
    "html_game",
    "pbl",
    "multi_agent_roundtable",
    "realtime_whiteboard",
    "teacher_actions"
  ],
  "options": {
    "enableWebSearch": false,
    "enableImageGeneration": true,
    "enableVideoGeneration": true,
    "enableTTS": true,
    "agentMode": "generate"
  }
}
```

Only courses in an active Mira release with a published LessonPackage can be submitted. The backend sends grade, subject, title, objective, teacher style and requested features. It never sends private answers or evaluator data.

Poll:

```http
GET /internal/learning/openmaic/classrooms/jobs/{openmaicJobId}
```

Generation completes in `pending_review`. A content operator must review the
full playback, Agent behavior, game/simulation controls, video, captions and
pronunciation before students can launch it:

```http
POST /internal/learning/openmaic/classrooms/{runtimeId}/review
X-Mira-Internal-Token: ...
Content-Type: application/json

{
  "decision": "approve",
  "reviewerId": "content-operator-id",
  "notes": "All scenes and pronunciation reviewed on desktop and tablet"
}
```

`reject` keeps the generated artifact unavailable to students. It is not a
silent approval or a request-time fallback.

Student Web calls:

```http
POST /api/v2/student/learning/sessions/{sessionId}/openmaic-launch
Authorization: Bearer <student access token>
```

The returned `launchUrl` is single use and expires in 60 seconds.

### Student classroom chrome

The gateway-controlled classroom URL carries the exact `?mira=1` marker. Only
that exact value enables the student presentation context: the classroom is
kept on the playback track, Chinese (`zh-CN`) and light theme are enforced, the
home/back affordance and language/theme/settings/export/edit controls are
removed, and the sidebar plus PBL/editor fallback chrome use neutral classroom
identity. Classroom title, description and icons are also Mira-specific. These
route-scoped language/theme overrides do not rewrite the operator's persisted
preferences. A missing marker, `mira=0`, duplicate marker, or any other value
preserves the upstream operator UI and its metadata; the query never grants
authorization by itself.

When generation is enabled, a backend worker processes one active release at a time. It first advances an existing OpenMAIC job, then starts the next released LessonPackage that does not yet have a full classroom. It never invokes a model from `today`, `start session`, or another student-facing request.

## Runtime gateway policy

Allowed for the bound classroom:

- classroom document and classroom media
- PBL v2 runtime
- multi-agent chat / roundtable SSE
- server-managed TTS and transcription
- quiz feedback
- static application assets

Blocked from the student gateway:

- classroom generation
- editor and arbitrary classroom writes
- settings and provider configuration
- client-supplied API keys and base URLs
- arbitrary media proxying
- other classroom IDs
- MP4 render jobs (content-operations only)
- Next.js development HMR, hot-update and React Refresh assets

## VoxCPM2

See [`deploy/voxcpm2/README.md`](deploy/voxcpm2/README.md). VoxCPM2 is a private GPU service, not a browser dependency.

## Verification

```bash
cd openmaic-runtime
./scripts/test-native-runtime.sh
./scripts/test-local-test-stack.sh
./scripts/healthcheck.sh

cd openmaic-runtime/gateway
npm test
npm run check
```

`native-runtime.sh status` and `healthcheck.sh` return non-zero unless both the
OpenMAIC `1.0.0` health payload on `127.0.0.1:3100` (including the exact
`mira-student-chrome.v6` attestation, the Node-only persistence instrumentation
boundary, student-session auto-play default-off, forced student ASR without
mutating the operator preference, and the fixed controlled sample-teacher
avatar) and the pinned gateway payload on
`127.0.0.1:3101` match their expected JSON contracts.

`test-native-runtime.sh` uses a temporary fake Next entry point to verify the
production build/start command, environment allowlist, secret exclusion, and
`.next/BUILD_ID` gate; it does not perform a real production build or start a
service.

Patch `0055` projects real mouse clicks through the scaled sandbox iframe during formal scene inspection, with inner and outer hit tests. It also surfaces the remaining quality-review budget and terminates the quality tool batch when the last review fails. The three-review cap and publication evidence contract are unchanged.

Patch `0056` treats a draining persistence pool as loss of the formal completion owner, retaining the existing durable job for reattachment instead of recording a shutdown as a content rejection. A missing stage caused by an observed search HTTP 429 has a specific diagnostic. Before restarting, inspect both backend Runtime jobs and PostgreSQL Agent sessions; a failed outer job can still have a running Agent.

Patch `0057` preserves the JSON Schema in the system message when the DeepSeek wire adapter falls back to JSON-object mode. This keeps the required review field names available to the model; strict schema, quote/evidence checks and review budgets remain unchanged. Wire-level tests cover the actual provider fetch adapter, as well as the creator/verifier route.
