# OpenMAIC full-runtime capability manifest v2

Mira treats the pinned `OpenMAIC 0.3.2` classroom document as untrusted
generated output. A successful upstream generation job is not enough to mark a
runtime classroom ready. The backend validates the document and builds
`mira.openmaic.runtime-features.v2` first.

## Stage 2 sample generation request

`POST /internal/learning/openmaic/classrooms/sample` (with
`/classrooms/generate` retained as an internal compatibility alias) accepts
exactly two fields:

```json
{
  "requestId": "runtime-primary-1-math-number-sense-20-v1",
  "sampleMode": "primary_1_math_number_sense_20_v1"
}
```

The browser cannot send a grade, subject, skill, course, teacher, voice,
features, or generation options. The backend resolves the exact
`primary_1/math/number_sense_20` course from the active published catalog
release and compiles a `mira.openmaic.sample-classroom.v2` contract into the
free-form OpenMAIC requirement. The fixed required feature set is `slides`,
`quiz`, `simulation`, `html_game`, `3d_visualization`,
`multi_agent_roundtable`, and `teacher_actions`. The sample must contain exactly
ten ordered scenes, including at least two slides plus a real simulation, game,
and 3D interactive. Whiteboard evidence is deliberately not a Stage 2 release
requirement.

The initial request is idempotent by `requestId`. A failed sample is terminal
and is not retried automatically. At most two separately approved manual
retries may be created through this internal-token-only contract:

```text
POST /internal/learning/openmaic/classrooms/{sourceRuntimeId}/retry
```

```json
{
  "retryRequestId": "stage2-primary1-math-number-sense20-v1-retry2",
  "expectedPreviousJobId": "<attempt-one-upstream-job-id>",
  "reason": "approved_stage2_retry"
}
```

No course, grade, model, provider, voice, feature or generation option is
accepted. The attempt-two source must be attempt one in terminal `failed` state with
`error_code=openmaic_sample_generation_stale`, the expected job must match,
and the active server-owned generation contract must still be exact. Attempt
two is a new runtime row (`attempt_ordinal=2`, `retry_of_runtime_id=<attempt
one>`); attempt one's upstream job, error and timestamps are never overwritten.

After a separately recorded user approval, the same endpoint may create the
third and final attempt using attempt two as its source:

```json
{
  "retryRequestId": "stage2-primary1-math-number-sense20-v1-retry3",
  "expectedPreviousJobId": "<attempt-two-upstream-job-id>",
  "reason": "approved_stage2_retry_3"
}
```

The attempt-three source must be attempt two in terminal `failed` state with
`error_code=openmaic_generation_process_restarted`. Its audit link back to
attempt one, stored reason and expected attempt-one job ID must be intact. The
new row is `attempt_ordinal=3` with `retry_of_runtime_id=<attempt two>`. The
package/attempt ordinal, retry source, request ID and upstream job remain
database-unique. The database constraint permits only attempts one, two and
three, with fixed reasons for attempts two and three.

Attempt three is also the only permitted contract-upgrade boundary. Its source
may contain the original `mira.openmaic.sample-classroom.v1` five-feature
contract while the new reservation contains the current server-built v2 parity
contract. The upgrade validator allows changes only to `schemaVersion`,
`requiredClassroom`, `speechAudioContract`, and the added
`conversationContract`. Course/package identity, authority, learner limits,
teacher identity, Qwen voice, sample mode, and generation options must remain
exactly equal. No request field can supply either contract.

Each retry is committed as `pending` before the external call. Replaying the
same `retryRequestId` returns that stored row and never dispatches again,
including when runtime health, catalog data or the teacher registry later
changes. A different key for an already-reserved ordinal and any attempt four
are rejected. If the external call succeeds but its job ID cannot be persisted,
the pending reservation is left fail-closed and same-key replay still performs
zero additional model calls. The public status contract reports
`maxAttempts=3`, `manualRetries=2`, and `automaticRetries=0`. The background
runner is separately guarded by
`OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED=0` and only polls an already-created
task. It never scans an active release or starts another classroom.

After a read-only idempotency/source-chain check and before any reservation
write, the backend probes `GET /api/health`. Generation is allowed only when
the response has `success=true`, `status=ok`,
`version=0.3.2`, `capabilities.tts=true`, `capabilities.asr=true`, and this exact
policy:

```json
{
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
        "scene-content:pbl",
        "scene-actions"
      ],
      "thinking": {"mode": "disabled", "enabled": false}
    }
  }
}
```

Missing, extra, reordered, null, disabled, or mismatched policy returns
`openmaic_sample_generation_not_ready` with HTTP 503. No runtime row is
created and `/api/generate-classroom` is not called. The status endpoint may
show only the bounded version, TTS boolean and allowlisted non-secret policy
fields. A new retry applies this preflight before any database write or
external generation call; replay of an existing attempt-two reservation is a
read-only exception because it never dispatches.

## Manifest

New runtime rows store an additive v2 manifest:

```json
{
  "schemaVersion": "mira.openmaic.runtime-features.v2",
  "enabled": ["slides", "quiz"],
  "requested": ["slides", "quiz"],
  "required": ["slides"],
  "present": ["quiz", "slides"],
  "missing": [],
  "evidence": {
    "slides": {
      "verified": true,
      "signals": ["scene:slide-1:slide-elements:4"],
      "reasons": []
    }
  },
  "platform": {
    "mp4Export": false,
    "mp4ExportConfigured": false,
    "mp4ExportCapabilityProbed": false,
    "mp4ExportClassroomDryRun": false,
    "assessmentAuthority": "mira_backend"
  }
}
```

`requested` remains an alias of `enabled` for generic v1 consumers. A Stage 2
sample cannot be approved, issued a launch ticket, exchanged, or used to
refresh a runtime session unless its strict generation contract, teacher
identity, and speech-audio evidence all revalidate.

## Stage 2 strict fields

`generationContract` has this exact object shape. Angle-bracket values come
from the one matching active catalog release; every other value is fixed by
the backend:

```json
{
  "schemaVersion": "mira.openmaic.sample-classroom.v2",
  "sampleMode": "primary_1_math_number_sense_20_v1",
  "authority": {
    "courseContext": "mira_active_catalog_release",
    "studentContext": "authenticated_learning_session",
    "clientOverridesAllowed": false
  },
  "course": {
    "id": "<published-course-id>",
    "version": "<published-course-version>",
    "releaseId": "<active-release-id>",
    "packageId": "<published-package-id>",
    "packageVersion": 1,
    "gradeCode": "primary_1",
    "gradeLabel": "小学一年级",
    "subjectCode": "math",
    "subjectLabel": "数学",
    "skill": {
      "gradeCode": "primary_1",
      "subject": "math",
      "curriculumVersion": "mira.primary.2026-fall.v1",
      "boundaryVersion": "mira.primary.2026-fall.v1:number_sense_20:4c771187db7ced28",
      "skillId": "number_sense_20",
      "skillTitle": "20以内数感",
      "learningObjectives": ["比较20以内数的大小", "理解数的组成与顺序"],
      "allowedContent": ["数数", "数位雏形", "大小比较"],
      "excludedContent": ["负数", "乘除法", "分数", "小数"],
      "prerequisiteSkills": [],
      "language": "zh-CN",
      "estimatedMinutes": 10
    },
    "title": "<published-title>",
    "objective": "<published-objective>"
  },
  "learnerConstraints": {
    "developmentStage": "early_primary_grade_1",
    "recommendedAgeBand": "6-8",
    "language": "zh-CN",
    "durationMinutes": 10,
    "reading": "短句、口语化指令、一次只要求一个动作",
    "visuals": "用可数物和数轴支持20以内数量、顺序和大小比较",
    "prohibitedContent": ["负数", "乘除法", "分数", "小数"]
  },
  "teacher": {
    "profile": {
      "id": "mira_math_clear",
      "version": 2,
      "displayName": "小数老师",
      "languageCode": "zh-CN",
      "teachingStyle": "clear_structured"
    },
    "voiceIdentity": {
      "schemaVersion": "mira.openmaic.qwen3-voice.v1",
      "teacherProfile": {"id": "mira_math_clear", "version": 2},
      "voiceConfig": {
        "providerId": "qwen-tts",
        "modelId": "qwen3-tts-flash",
        "voiceId": "Serena"
      },
      "selectionId": "qwen-tts::Serena",
      "displayName": "苏瑶 (Serena)",
      "languageCode": "zh-CN"
    }
  },
  "requiredClassroom": {
    "features": [
      "slides",
      "quiz",
      "simulation",
      "html_game",
      "3d_visualization",
      "multi_agent_roundtable",
      "teacher_actions"
    ],
    "exactSceneCount": 10,
    "minimumSlideScenes": 2,
    "sceneTypes": ["slide", "quiz", "interactive"],
    "interactive": {
      "requiredWidgetTypes": ["simulation", "game", "visualization3d"],
      "widgetOutlineRequired": true,
      "embeddedHtmlRequired": true,
      "controlsRequired": true
    },
    "multiAgent": {
      "teacherRequired": true,
      "minimumPeerAgents": 3,
      "minimumDiscussionActions": 2,
      "distinctPeerDiscussionsRequired": true
    },
    "teacherActionsRequired": true,
    "narration": {
      "requiredForEveryScene": true,
      "transcriptRequired": true
    }
  },
  "speechAudioContract": {
    "schemaVersion": "mira.openmaic.speech-audio.v1",
    "requiredForEverySpeechAction": true,
    "requiredForEveryScene": true,
    "uniqueAudioRequired": true,
    "audioUrlMustBeReadable": true,
    "metadataField": "audioMetadata",
    "fallbackMetadataField": "fallbackUsed",
    "providerId": "qwen-tts",
    "modelId": "qwen3-tts-flash",
    "voiceId": "Serena",
    "fallbackAllowed": false
  },
  "conversationContract": {
    "textChatRequired": true,
    "voiceInputRequired": true,
    "asr": {
      "providerId": "qwen-asr",
      "modelId": "qwen3-asr-flash",
      "fallbackAllowed": false
    }
  },
  "generation": {
    "enableWebSearch": false,
    "enableImageGeneration": false,
    "enableVideoGeneration": false,
    "enableTTS": true,
    "agentMode": "generate",
    "automaticRetries": 0,
    "staleAfterMs": 1800000
  }
}
```

The generated stage and every speech action must provide these runtime fields:

```json
{
  "teacherAgent": {
    "name": "小数老师",
    "role": "teacher",
    "voiceConfig": {
      "providerId": "qwen-tts",
      "modelId": "qwen3-tts-flash",
      "voiceId": "Serena"
    }
  },
  "speechAction": {
    "audioId": "<persisted-audio-id>",
    "audioUrl": "<same-origin-readable-audio-url>",
    "audioMetadata": {
      "schemaVersion": "mira.openmaic.speech-audio.v1",
      "providerId": "qwen-tts",
      "modelId": "qwen3-tts-flash",
      "voiceId": "Serena",
      "fallbackUsed": false
    }
  }
}
```

After byte/MIME probing, the manifest records:

```json
{
  "teacherIdentity": {
    "verified": true,
    "agentId": "<teacher-agent-id>",
    "teacherProfile": {
      "id": "mira_math_clear",
      "version": 2,
      "displayName": "小数老师",
      "languageCode": "zh-CN",
      "teachingStyle": "clear_structured"
    },
    "voiceConfig": {
      "providerId": "qwen-tts",
      "modelId": "qwen3-tts-flash",
      "voiceId": "Serena"
    },
    "selectionId": "qwen-tts::Serena"
  },
  "speechAudio": {
    "verified": true,
    "speechActionCount": 10,
    "verifiedAssetCount": 10,
    "signals": ["scene:<id>:action:<id>:audio:<id>:asset-probed"],
    "providerId": "qwen-tts",
    "modelId": "qwen3-tts-flash",
    "voiceId": "Serena",
    "fallbackAllowed": false
  },
  "sceneNarration": {
    "verified": true,
    "sceneCount": 10,
    "narratedSceneCount": 10,
    "transcriptSceneCount": 10,
    "signals": ["scene:<id>:transcript:speech-actions:<count>"]
  },
  "conversation": {
    "verified": true,
    "textChat": true,
    "voiceInput": true,
    "asr": {
      "providerId": "qwen-asr",
      "modelId": "qwen3-asr-flash",
      "fallbackAllowed": false
    },
    "signals": ["runtime-policy:asr:qwen-asr:qwen3-asr-flash:no-fallback"]
  }
}
```

An upstream job that reports `succeeded` but omits audio, returns an unreadable
audio URL, reuses an audio ID/URL, changes provider/model/voice, or uses any
fallback is terminally failed before human review. macOS system speech is not
an allowed fallback for this sample.

If `required - present` is non-empty, the runtime row is marked `failed` with
`openmaic_required_features_missing`. It cannot enter `ready` or human review.

## Evidence rules

The validator uses the real v0.3.2 DSL discriminants and playback dependencies:

| Feature | Required evidence |
| --- | --- |
| `slides` | `scene.type=slide`, matching `content.type`, a canvas and at least one identified element |
| `quiz` | Matching quiz content with at least one structurally valid question; choice questions need at least two valid options |
| `simulation` | Embedded interactive HTML, executable script, real control, and explicit `widgetType=simulation` (or matching `widgetConfig.type`) |
| `html_game` | Embedded interactive HTML, executable script, real control, and explicit `widgetType=game` |
| `3d_visualization` | Embedded interactive HTML, executable script, real control/canvas, and explicit `widgetType=visualization3d`; library-name text scanning is not evidence |
| `video` | A valid `play_video` action targeting a video element in the same slide plus a same-origin video asset byte/MIME probe (or embedded video data) |
| `pbl` | A runnable PBL v2 project with an instructor and non-empty milestone microtasks, or a runnable legacy project with issues |
| `multi_agent_roundtable` | For the sample, one teacher plus at least three peers and two discussions naming different peers; every explicit action Agent must resolve in that roster |
| `realtime_whiteboard` | A valid, non-empty drawing action (`wb_draw_*`); supported generically but not required by the current Stage 2 sample |
| `teacher_actions` | A valid executable UI action with its dependency satisfied: slide target, playable video, productive whiteboard draw, or an interactive widget action whose HTML contains a real `message` listener and matching OpenMAIC message branch; a marker in text/comments and speech alone are not UI operation evidence |
| `mp4_export` | Kept outside scene `present`; it requires a live upstream render-service capability probe and a successful per-classroom export compiler dry run |

Every scene must also satisfy the stage/scene/content binding, and every action
must use the exact v0.3.2 action allowlist with its required fields. Unknown
actions such as `video`, `roundtable`, or `wb_draw` fail structural validation
instead of being counted by name.

Validation is bounded for untrusted generated documents: at most 32 stage
agents, 500 slide elements, 100 quiz questions, 20 options per question, and 200
actions per scene. Persisted evidence keeps at most 100 unique signals per
feature and uses `evidence-signals-truncated` as its final signal when more
valid signals exist, preserving the strict v2 object shape. Slide elements use
the pinned PPT element-type allowlist, choice keys must be unique, and an
interactive scene cannot be empty. Repeated references to the same video asset
are byte/MIME-probed once per classroom validation, with at most 100 unique
media probes.

The pinned v0.3.2 server exposes `/api/export-video/capability`, but it does not
expose a server-side per-classroom compiler dry-run endpoint. Therefore
`platform.mp4Export` may truthfully report a healthy render service, while
`mp4_export` remains absent from `present`; making it required fails closed until
that preflight boundary exists.
