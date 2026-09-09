# Learning teacher and media materialization

This slice turns approved lesson narration intent into server-owned audio for
the student Web product. It does not let OpenMAIC, a browser, or a student
choose a provider URL, an API key, a voice prompt, or voice-cloning material.

## Architecture boundary

```text
validated private Mira lesson package (`media_pending`)
  -> LearningMediaMaterializationService.enqueue_narration
  -> learning_media_generation_jobs + narration segments
  -> server-configured TtsProvider
  -> server-configured LearningMediaAssetStore
  -> checksum + technical validation + quality review
  -> required `learning_lesson_package_assets` narration bindings
  -> atomic lesson-package publication + `audioAssetRef` attachment
  -> owned student session -> approved asset delivery
```

OpenMAIC may propose teaching copy and narration intent. It is not the asset
authority. Mira chooses the teacher profile, performs TTS, owns storage, applies
the release policy, and exposes only approved media.

The Flask factory now wires a server-only materializer, a background worker,
internal operations routes, and a student delivery route. A missing VoxCPM2
endpoint leaves the worker disabled and queued jobs explicitly `pending`; it
never creates a fake `ready` asset.

## Migration 040

`migrations/040_learning_teacher_media_assets.sql` adds:

- `learning_teacher_profiles`: immutable `(id, version)` teacher snapshots,
  including the server-only voice prompt and a content hash.
- `learning_student_teacher_preferences`: one version-pinned teacher per
  family, child, and subject.
- `learning_media_generation_jobs`: idempotent generation request, provider
  binding, package/course context, status, and safe failure state.
- `learning_narration_segments`: ordered copy, subtitle, text hash, audio
  checksum, and per-segment status.
- `learning_media_asset_variants`: content-addressed variants under the
  existing `learning_media_assets` authority.
- `learning_media_quality_reviews`: required review evidence and decision.

The existing `learning_media_assets` table remains the canonical asset record.
The existing lesson package gate still requires `status=ready`,
`scan_status=passed`, `moderation_status=passed`, and a passed or unnecessary
transcode.

## Controlled teacher registry

`content/teacher_profiles.py` currently publishes three version-1 profiles:

| Profile | Subject | Language | Product behavior |
| --- | --- | --- | --- |
| `mira_chinese_gentle` | Chinese | `zh-CN` | `/teachers/mi-chinese-v1.png`; gentle guided reading; pinyin is review-gated |
| `mira_math_clear` | Math | `zh-CN` | `/teachers/ashu-math-v1.png`; clear steps and worked examples |
| `mira_english_standard` | English | `en-US` | `/teachers/coco-english-v1.png`; listen/repeat and standard pronunciation; always review-gated |

Every profile is `voice_mode=prompt`, `clone_allowed=false`, and contains no
reference audio or registered/cloned voice identifier. Changing any profile
content requires incrementing its version; repository synchronization rejects
an in-place mutation of a persisted version.

Public teacher payloads omit the provider ID, model, and voice prompt.

## VoxCPM2 adapter

`integrations/tts/voxcpm2.py` supports the two requested official protocols:

- vLLM-Omni: `POST /v1/audio/speech`, OpenAI-compatible JSON (`model`,
  `input`, `voice=default`, `response_format=wav`, `stream=false`).
- VoxCPM Python API: `POST /tts/upload`, multipart fields `text`, `cfg_value`,
  `inference_timesteps`, `normalize`, and `denoise`.

The controlled voice prompt is embedded in target text using the same prompt
mode convention as OpenMAIC. The adapter deliberately has no API-key parameter,
no clone mode, no reference-audio parameter, and no registered-voice path. The
base URL must be a server-owned HTTP(S) configuration without URL credentials,
query parameters, or fragments.

The adapter rejects empty bodies, non-audio content types, unsupported output
formats, and responses over 32 MiB. Upstream bodies are never persisted as a
safe error message.

Server-owned configuration:

```text
LEARNING_VOXCPM_BASE_URL
LEARNING_VOXCPM_BACKEND=vllm-omni|python-api
LEARNING_VOXCPM_MODEL=openbmb/VoxCPM2
LEARNING_VOXCPM_TIMEOUT_SECONDS=30
LEARNING_MEDIA_STORAGE_ROOT
LEARNING_MEDIA_WORKER_ENABLED=0|1
LEARNING_MEDIA_WORKER_INTERVAL_SECONDS=15
```

Do not add these values to a student request or lesson-model output. If no real
VoxCPM endpoint and asset store are configured, do not construct a production
materialization worker. Jobs may remain pending; the application must not
substitute browser TTS or create a fake ready asset.

## Job and review states

```text
pending -> generating -> ready
                      \-> awaiting_review -> ready
                                           \-> rejected
          generating -> failed
```

- `english` always requires a `manual_pronunciation` review.
- Chinese `pinyin` always requires a `manual_pronunciation` review.
- Other controlled narration receives an approved automated integrity record
  after real bytes, MIME type, checksum, and immutable storage are verified.
- Review-pending, rejected, failed, or partially generated audio is excluded
  from the student library query.
- A failure after some segments have materialized leaves those partial assets
  outside a ready job, so the student query still cannot expose them.

An enqueue idempotency key is bound to a canonical request hash. Reusing the
same key and same body returns the original job; changing the body produces
`idempotency_conflict`.

## Production integration

The service factory constructs dependencies from trusted server configuration
only:

```python
repository = LearningTeacherMediaRepository(database)
tts = VoxCpm2HttpProvider(
    base_url=config["LEARNING_VOXCPM_BASE_URL"],
    backend=config["LEARNING_VOXCPM_BACKEND"],
    model_name=config["LEARNING_VOXCPM_MODEL"],
)
store = FilesystemLearningMediaAssetStore(config["LEARNING_MEDIA_STORAGE_ROOT"])
materializer = LearningMediaMaterializationService(
    repository,
    tts_provider=tts,
    asset_store=store,
)
```

The production flow is:

1. `LessonPackageService` validates OpenMAIC output, stores the public/private
   package at `media_pending`, extracts every `narrate` action, and creates the
   media job and narration segments in the same database transaction.
2. `LearningMediaWorkerRunner` invokes the server-configured VoxCPM2 adapter.
   Each real audio response is checksummed, stored under the safe media root,
   and registered as a required `usage_kind='narration'` package asset.
3. General Chinese/math narration becomes ready after the automated integrity
   record. Pinyin and English remain `awaiting_review` until an authorized human
   submits an approval through `POST /internal/learning/media/review`.
4. Once every expected segment, variant, technical gate, required review, and
   package binding is ready, finalization atomically publishes the package,
   activates the course binding, and writes opaque `asset:<assetId>` references
   into the matching narration actions. A failure/rejection never publishes.
5. Student Web obtains a manifest from
   `GET /api/v2/student/learning/sessions/<sessionId>/assets` and bytes from the
   exact BFF upstream path
   `GET /api/v2/student/learning/assets/<assetId>`. The latter requires a Student
   Bearer token and proves the current child's existing session is pinned to the
   same published package/content hash and package-asset/media-job chain.

Internal operations endpoints under `/internal/learning/media` are guarded by
the existing internal token/source audit:

- `GET /status` reports worker/provider/job/package state.
- `POST /materialize` processes one explicit or next pending job.
- `POST /review` records the human pronunciation decision and attempts package
  finalization.

Student delivery uses Flask conditional responses, including Range, ETag and
Last-Modified. It verifies the relative storage key stays under the configured
root, the file is regular, and its byte size and SHA-256 match the approved
variant. Responses use private revalidation, `nosniff`, same-origin resource
policy, and never expose a raw storage key.

## Verification

- `tests/test_teacher_profile_registry.py` checks subject coverage, versioned
  hashes, no-clone policy, and public-data redaction.
- `tests/test_voxcpm2_tts_provider.py` checks both HTTP contracts without a
  network connection and verifies no credential or clone fields are sent.
- `tests/test_learning_teacher_media_assets.py` applies the real MySQL
  migration and uses a test-only provider plus temporary filesystem to verify
  idempotency, preference pinning, checksum persistence, failure behavior, and
  the pinyin/English manual-review visibility gate.
- `tests/test_lesson_package_media_pipeline.py` verifies private staging,
  required narration bindings, action asset refs, automatic general narration,
  and the pinyin human-review publication gate.
- `tests/test_internal_learning_media_api.py` verifies internal authorization,
  worker behavior, materialization/review routes, and unconfigured-provider
  pending behavior.
- `tests/test_student_learning_media_api.py` verifies the owned-session chain,
  cross-student isolation, review regression, safe-root rejection, Range and
  ETag delivery.
