# Grade-Triggered Formal Production Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the production-grade vertical flow where a parent selects a primary-school grade, Mira asynchronously prepares the complete three-subject catalog, produces validated ten-scene interactive classrooms and Qwen3 speech, atomically publishes a grade release, lets an authenticated student learn it, and writes progress, completion, mastery, and reports back without human review or generation from student requests.

**Architecture:** Grade save only reserves a child plan. A lease runner coordinates a shared grade build. A content-only state machine advances one durable named Provider phase per tick, first through three production canaries and then through all thirty Grade-1 targets. A classroom pipeline consumes only validated content candidates, produces immutable full Runtime artifacts and Qwen3 audio, validates them with independent Host and route receipts, then atomically switches a grade-scoped release pointer. Student launch reads only the active grade release. A signed, session-bound Runtime event bridge records progress and authoritative answers in Mira before completion/report publication. All external work is gated, audited, bounded, and recoverable.

**Tech Stack:** Python 3, Flask, MySQL/PyMySQL, `unittest`, Node.js/ESM, OpenMAIC/Next.js, Qwen3-TTS/Qwen3-ASR, Kimi, Flutter/Dart/Riverpod/Dio, Student Web/React/Playwright.

**Specs:**

- `docs/superpowers/specs/2026-08-21-grade-triggered-preparation-checkpoint-2-design.md`
- `docs/superpowers/specs/2026-08-20-grade-triggered-curriculum-preparation-design.md`

## Global Constraints

- This is not a demo path. No mocked success, prefilled classroom, manually flipped status, or sample-only hard-coded launch counts as completion.
- The first production rollout is exact `primary_1`: Chinese 12, math 9, English 9, three variants per registered boundary. Other grades remain closed until their versioned boundary/voice contracts pass the same rollout gates.
- The exact production canaries are `chinese/pinyin_syllables/1`, `math/number_sense_20/1`, and `english/letters_sounds/1`. They are ordinary members of the same thirty-item build, not disposable test rows.
- Parent grade save, preparation GET/retry, Today, assign, student library, student launch, and report reads never call a model or create content.
- Checkpoint 2 is content-only: package, media, Runtime, TTS, ASR, activation, and student visibility deltas must all be zero. Thirty validated content candidates are a handoff, not a finished course release.
- Production completion requires every target to have one immutable ten-scene Runtime with exact 5 slide / 2 quiz / 1 simulation / 1 game / 1 visualization3d distribution, one teacher plus four peers, per-scene speech, two peer discussions, teacher actions, real interactive behavior, and no whiteboard requirement.
- Every classroom has exactly ten unique speech assets, one per scene. Each uses server-owned Qwen `qwen3-tts-flash`, a subject-approved voice, no fallback, bounded timeout, durable attempted/completed evidence, media hashing, format/duration/non-silence validation, and Qwen ASR round-trip evidence.
- Kimi chat and Qwen ASR/TTS identities are server-owned; client provider/model/key/base overrides are rejected. Conversation readiness must separate authenticated route proof from real provider acceptance.
- Release is grade-scoped and atomic. A failed candidate never hides or mutates the current active grade release; historical sessions stay pinned to their original release/package/runtime versions.
- Student Runtime events are authenticated, session/classroom/release bound, monotonic, idempotent, allowlisted, and unable to manufacture authoritative mastery. The backend remains answer/report authority.
- All generation/runner flags default off. Production rollout requires exact allowlist, readiness attestation, migration readback, zero-bypass tests, rollback proof, and an explicit enable step.
- Preserve all unrelated dirty and untracked workspace changes. The current checkout contains user-owned untracked Grade-1 code, so do not create a worktree that omits it, do not reset, do not clean, and do not overwrite whole files from another branch.
- Do not run `git add` or `git commit`. Before each task capture hashes for its file set, edit with narrow `apply_patch`, and write a task report under `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/`.
- MySQL suites that reset `ai_camera_app_test` run serially. No test may connect until the exact local test database guard succeeds.
- Use RED then minimal GREEN for every production change. A task is not complete until its focused tests, relevant regression, `py_compile`/typecheck, and `git diff --check` pass.

---

## Phase I — Durable Content Production

### Task 1: Freeze the V2 Target, Phase Graph, and Grade-1 Content Authority

**Files:**

- Create: `backend/content/primary_1_content_validation.v1.json`
- Create: `backend/services/learning_question_phase_contract.py`
- Modify: `backend/content/primary_skill_boundaries.py`
- Modify: `backend/services/learning_curriculum_preparation_contract.py`
- Modify: `backend/openmaic-sidecar/src/question-contract.mjs`
- Create: `backend/tests/test_learning_question_phase_contract.py`
- Create: `backend/tests/test_primary_grade_one_subject_validators.py`
- Modify: `backend/tests/test_learning_curriculum_preparation_contract.py`
- Create: `backend/openmaic-sidecar/test/question-phase-contract.test.mjs`

**Interfaces:**

```python
QUESTION_CONTRACT_VERSION = "mira.learning.question-contract.v2"
CONTENT_VALIDATION_CONTRACT_VERSION = "mira.learning.primary-1-content-validation.v1"
PROVIDER_PHASES = (
    ("outline", 1), ("raw_candidate", 2),
    ("candidate_repair", 3), ("candidate_repair_retry", 4),
    ("lesson_text", 5), ("reconciliation", 6),
    ("reconciliation_retry", 7), ("practice_leak_repair_1", 8),
    ("practice_leak_repair_2", 9), ("choice_prompt_repair", 10),
    ("independent_verification", 11), ("consistency_repair", 12),
    ("consistency_repair_retry", 13), ("verification_after_repair", 14),
)

def provider_phase(phase: str, phase_ordinal: int) -> ProviderPhase: ...
def primary_one_content_contract() -> Mapping[str, object]: ...
```

- [ ] Write tests that reject a fifteenth phase, duplicate phase/ordinal, caller-chosen ordinal, ambiguous English `language=zh-CN`, missing prerequisite inventory, and all invalid mutations for the ten Grade-1 boundaries.
- [ ] Assert the target manifest has exact subject/boundary/variant ordinals, `zh-CN/en-US` for English, exact three canaries, and that the dataset hash participates in the preparation fingerprint.
- [ ] Run RED:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_contract_pycache \
python3 -m unittest tests.test_learning_question_phase_contract \
tests.test_primary_grade_one_subject_validators -v
cd backend/openmaic-sidecar && node --test test/question-phase-contract.test.mjs
```

- [ ] Implement the shared versioned data authority and exact phase dependency graph without Provider calls.
- [ ] Run the same commands GREEN, then `cd backend/openmaic-sidecar && npm test`.

### Task 2: Add Migration 056 and the Append-Only Dispatch Ledger

**Files:**

- Create: `backend/migrations/056_learning_curriculum_preparation_content_stage.sql`
- Modify: `backend/repositories/learning_curriculum_preparation_repository.py`
- Modify: `backend/repositories/learning_catalog_repository.py`
- Modify: `backend/repositories/dynamic_learning_course_repository.py`
- Create: `backend/tests/test_learning_curriculum_preparation_content_stage_migration.py`
- Create: `backend/tests/test_learning_course_provider_dispatch_repository.py`
- Extend: `backend/tests/test_learning_curriculum_preparation_repository.py`
- Extend: `backend/tests/test_dynamic_learning_course_repository.py`

**Interfaces:**

```python
def begin_provider_dispatch(
    conn, *, build_item_id: str, logical_attempt: int, phase: str,
    phase_ordinal: int, generation_request_id: str, item_lease_token: str,
    provider: str, model: str, profile: str, input_sha256: str,
    attempt_started_at: int, attempt_hard_deadline_at: int, dispatched_at: int,
) -> Mapping[str, object]: ...

def complete_provider_dispatch(
    conn, *, dispatch_id: str, build_item_id: str,
    generation_request_id: str, item_lease_token: str,
    outcome: str, checkpoint: Mapping[str, object] | None,
    output_sha256: str | None, provider_request_id_hash: str | None,
    input_tokens: int | None, output_tokens: int | None,
    billing_evidence: str, safe_error_code: str | None, completed_at: int,
) -> bool: ...
```

- [ ] Write real-MySQL RED tests for two replays, partial-DDL restart, legacy 054/055 backfill, MySQL NULL/UNKNOWN counterexamples, plan/build/item state shapes, two dispatch UNIQUE keys, `logical_attempt BETWEEN 1 AND 2`, terminal receipt shapes, and late-token CAS rejection.
- [ ] Run RED:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_migration_pycache \
python3 -m unittest tests.test_learning_curriculum_preparation_content_stage_migration \
tests.test_learning_course_provider_dispatch_repository -v
```

- [ ] Implement restartable 056 using `INFORMATION_SCHEMA`; never edit registered 054/055. Backfill historical builds/items to `full_pipeline/active_release/legacy_full_pipeline/not_applicable` and branch plan CHECKs by the immutable target schema in `target_spec_json` (`mira.learning.preparation-target.v1|v2`). The separate `preparation_contract_version` column remains the existing `mira.learning.grade-preparation.v1` envelope authority and is not an invented future discriminator.
- [ ] Run GREEN plus repository regressions serially:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_migration_pycache \
python3 -m unittest tests.test_learning_curriculum_preparation_content_stage_migration \
tests.test_learning_course_provider_dispatch_repository \
tests.test_learning_curriculum_preparation_repository \
tests.test_dynamic_learning_course_repository -v
```

### Task 3: Create the Immutable Content-Only Build and Enforce Old-Path Isolation

**Files:**

- Modify: `backend/repositories/learning_catalog_repository.py`
- Modify: `backend/services/learning_catalog_release_service.py`
- Extend: `backend/tests/test_learning_catalog_release.py`
- Extend: `backend/tests/test_learning_catalog_release_state_machine_unit.py`
- Create: `backend/tests/test_learning_catalog_content_repository.py`

**Interfaces:**

```python
def create_preparation_content_build(
    self, *, request_id: str, title: str,
    preparation_target: Mapping[str, object], target_fingerprint: str,
) -> dict[str, object]: ...

def claim_next_content_item(
    self, conn, *, build_id: str, now: int, lease_ms: int,
) -> Mapping[str, object] | None: ...
```

- [ ] RED-test exact thirty ordered items, exact three canaries, `allowPartial=false`, `execution_mode=content_only`, `stage_ceiling=content_ready`, one live item per build, fair subject selection, and a single winner under two real MySQL connections.
- [ ] RED-test that public/operator `create()` cannot accept an execution mode, and old `run()`, `claim_package_for_item()`, and `activate()` reject content-only builds after locking the stable release sentinel, then the owning build and items.
- [ ] Implement the immutable manifest path. Eligibility must be derived from the stored manifest, never accepted from a caller list.
- [ ] Run GREEN:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_catalog_pycache \
python3 -m unittest tests.test_learning_catalog_content_repository \
tests.test_learning_catalog_release_state_machine_unit \
tests.test_learning_catalog_release -v
```

### Task 4: Make Sidecar V2 Execute At Most One Provider HTTP Call

**Files:**

- Modify: `backend/openmaic-sidecar/src/cli.mjs`
- Modify: `backend/openmaic-sidecar/src/provider.mjs`
- Modify: `backend/openmaic-sidecar/src/question-contract.mjs`
- Create: `backend/openmaic-sidecar/test/provider.test.mjs`
- Extend: `backend/openmaic-sidecar/test/question-phase-contract.test.mjs`

**Wire Contract:**

```text
mira.openmaic.question_phase.v2
  -> mira.openmaic.question_phase_result.v2
```

- [ ] RED-test exact request/response keys, one fake/live call maximum per process, retry count zero, phase timeout classification, hashed Provider request ID, nullable non-negative token usage, and `billingEvidence=reported|unknown`.
- [ ] Keep legacy V1 CLI for full-pipeline operator work; make content-only use only V2.
- [ ] Classify explicit pre-send rejection as safe; any timeout/connection/lost-response uncertainty is `ambiguous`. Do not expose raw Provider body/error/key.
- [ ] Run GREEN:

```bash
cd backend/openmaic-sidecar && node --test test/provider.test.mjs \
test/question-phase-contract.test.mjs test/question-contract.test.mjs
cd backend/openmaic-sidecar && npm test
```

### Task 5: Add the Python Phase Adapter and Restricted Candidate Generator

**Files:**

- Modify: `backend/integrations/openmaic_question_adapter.py`
- Modify: `backend/services/dynamic_learning_course_generation_service.py`
- Modify: `backend/repositories/dynamic_learning_course_repository.py`
- Create: `backend/tests/test_openmaic_question_phase_adapter.py`
- Create: `backend/tests/test_staged_content_candidate_generator.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class QuestionPhaseCommand:
    build_item_id: str
    logical_attempt: int
    phase: str
    phase_ordinal: int
    generation_request_id: str
    grade_code: str
    subject: str
    instruction_language_code: str
    target_language_code: str
    boundary: Mapping[str, object]
    checkpoint: Mapping[str, object]

class ContentCandidateGenerator(Protocol):
    def advance(self, work: ContentPhaseWork, *, heartbeat) -> ContentPhaseAdvance: ...
```

- [ ] RED-test preflight before ledger insert, ledger commit before process spawn, exactly one concurrent reservation winner/process, succeeded checkpoint recovery with zero Provider delta, and dispatched/lost response becoming an authoritative unknown with zero replay. Task 5 must reject caller-forged attempt 2; Task 7 alone may authorize it after locking immutable course plus deterministic Host-rejection evidence.
- [ ] Implement `StagedContentCandidateGenerator` with no `enqueue_classroom`, package, Runtime, media, TTS, ASR, or activation capability. The subprocess timeout must be below the two-minute work-unit deadline.
- [ ] Preserve legacy `generate()`/`generate_for_skill()` for full-pipeline callers, but do not inject them into the preparation runner.
- [ ] Run GREEN:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_phase_adapter_pycache \
python3 -m unittest tests.test_openmaic_question_phase_adapter \
tests.test_staged_content_candidate_generator \
tests.test_openmaic_question_adapter \
tests.test_dynamic_learning_course_generation_service -v
```

### Task 6: Implement Ten-Boundary Host Validation and Variant Deduplication

**Files:**

- Modify: `backend/services/learning_generated_course_validator.py`
- Modify: `backend/services/learning_catalog_validator.py`
- Extend: `backend/tests/test_learning_generated_course_validator.py`
- Extend: `backend/tests/test_learning_catalog_validator.py`
- Extend: `backend/tests/test_primary_grade_one_subject_validators.py`

- [ ] For each of the ten boundaries, add one valid golden and mutations for answer leakage, prerequisite drift, out-of-range content, ambiguous scoring, wrong language target, missing q1–q5 roles, and invalid deterministic answer.
- [ ] Add three-variant semantic fingerprint tests proving ID/order/whitespace/punctuation changes cannot bypass duplicate detection.
- [ ] Run RED, implement only repository-owned deterministic rules, and run GREEN:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_validator_pycache \
python3 -m unittest tests.test_primary_grade_one_subject_validators \
tests.test_learning_generated_course_validator \
tests.test_learning_catalog_validator -v
```

### Task 7: Implement `advance_content()` and Canary-to-Thirty Expansion

**Files:**

- Modify: `backend/services/learning_catalog_release_service.py`
- Modify: `backend/repositories/learning_catalog_repository.py`
- Create: `backend/tests/test_learning_catalog_content_only.py`
- Create: `backend/tests/test_learning_checkpoint2_zero_bypass.py`
- Extend: `backend/tests/test_learning_checkpoint_request_path_zero_calls.py`

**Interface:**

```python
@dataclass(frozen=True)
class ContentAdvanceResult:
    kind: Literal["progressed", "busy", "dependency_retry", "failed", "handoff", "stale"]
    build_id: str
    item_id: str | None
    content_summary: Mapping[str, object]

def advance_content(self, build_id: str, *, heartbeat) -> ContentAdvanceResult: ...
```

- [ ] RED-test exact canary eligibility, no expansion before 3/3, same-build expansion after 3/3, immediate terminal fence on canary failure, host-gate-only recovery after course persistence, at most three Host claims, immutable first-attempt course/rejection evidence before the only attempt-2 authorization, no attempt 2 for failed-safe/ambiguous/incomplete Provider work, and 30/30 handoff. Under the formal release/build/item locks, variant N must pass Task 6 the exact prior `1..N-1` immutable passed course+receipt+receipt-hash proofs for the same boundary; empty/forged provenance fails closed, and ordinal 3 cannot complete the boundary until the three-variant-set gate revalidates all three. Commands must be assembled only from Task-5-authenticated predecessor artifacts; Task 7 must rebuild the exact non-secret generator/verifier Provider profiles from stable configuration, prove their canonical hashes against every relevant locked dispatch row, and pass that typed evidence to Task 6 so solver identity and same/distinct-profile isolation cannot be forged. Package/media/Runtime/TTS/ASR/activation counters remain exactly zero.
- [ ] Implement one phase per invocation and one Provider subcall maximum. `failed_safe` and `ambiguous` terminalize the shared build; normal progress never uses `retry_wait`.
- [ ] Run GREEN:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_advance_pycache \
python3 -m unittest tests.test_learning_catalog_content_only \
tests.test_learning_checkpoint2_zero_bypass \
tests.test_learning_checkpoint_request_path_zero_calls -v
```

### Task 8: Bind Preparation Plans to Shared Item Work Units

**Files:**

- Modify: `backend/repositories/learning_curriculum_preparation_repository.py`
- Modify: `backend/services/learning_curriculum_preparation_runner.py`
- Modify: `backend/services/service_factory.py`
- Extend: `backend/tests/test_learning_curriculum_preparation_repository.py`
- Extend: `backend/tests/test_learning_curriculum_preparation_runner.py`
- Create: `backend/tests/test_learning_curriculum_preparation_shared_build.py`

**Interfaces:**

```python
def bind_content_work_unit(
    self, conn, *, plan_id: str, plan_lease_token: str,
    target_fingerprint: str, catalog_build_id: str, catalog_item_id: str,
    content_lease_token: str, logical_attempt: int, content_phase: str,
    item_work_unit_deadline_at: int, now: int,
) -> Mapping[str, object] | None: ...

def reconcile_shared_build(
    self, conn, *, build_id: str, target_fingerprint: str, now: int,
) -> int: ...
```

- [ ] RED-test coordinator two-minute deadline, item phase two-minute deadline, immutable thirty-minute logical-attempt deadline, joint heartbeat, stale lease without deadline extension, busy follower scheduling, child revision recheck, terminal build fan-out, and 30/30 plan state `running/building_classrooms/35%/ready=0`.
- [ ] Implement normal scheduled-unleased continuation instead of `retry_wait`; use retry_wait only for an explicitly retryable dependency with exact resume binding.
- [ ] Replace background `except Exception: pass` with structured safe observation/logging.
- [ ] Run GREEN:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_runner_pycache \
python3 -m unittest tests.test_learning_curriculum_preparation_repository \
tests.test_learning_curriculum_preparation_shared_build \
tests.test_learning_curriculum_preparation_runner -v
```

### Task 9: Add Exact V1/V2 Parent API and Read-Only Runner Status

**Files:**

- Modify: `backend/services/learning_curriculum_preparation_contract.py`
- Modify: `backend/services/learning_curriculum_preparation_service.py`
- Modify: `backend/routes/api/v1/learning.py`
- Create: `backend/routes/internal/learning_curriculum_preparations.py`
- Modify: `backend/app.py`
- Modify: `backend/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/README.md`
- Extend: `backend/tests/test_learning_curriculum_preparation_api.py`
- Create: `backend/tests/test_internal_learning_curriculum_preparation_status_api.py`

- [ ] RED-test unauthenticated-first behavior, exact V1 without header, exact V2 with `X-Mira-Preparation-Schema: mira.learning.preparation.v2`, unknown schema 406, `Vary`, exact nested count invariants, setup/profile remaining V1, and one shared `parent_retry_decision` used by display and transactionally revalidated POST.
- [ ] RED-test internal status auth before query/read, exact whitelist response, guard audit as the only write, no run endpoint, business zero-write, and Provider zero-call.
- [ ] Implement then run GREEN:

```bash
cd backend && PYTHONPYCACHEPREFIX=/private/tmp/mira_cp2_api_pycache \
python3 -m unittest tests.test_learning_curriculum_preparation_api \
tests.test_internal_learning_curriculum_preparation_status_api \
tests.test_setup_api tests.test_profile_family_settings_api -v
```

### Task 10: Add Flutter V2 Content Progress Without Opening Today

**Files:**

- Modify: `mobile/lib/src/features/learning/domain/learning_preparation_models.dart`
- Modify: `mobile/lib/src/features/learning/application/learning_preparation_repository.dart`
- Modify: `mobile/lib/src/features/learning/presentation/widgets/learning_preparation_card.dart`
- Modify only if required: `mobile/lib/src/features/home/presentation/widgets/home_primary_learning_preview.dart`
- Extend: `mobile/test/learning_preparation_models_test.dart`
- Extend: `mobile/test/learning_preparation_repository_test.dart`
- Extend: `mobile/test/learning_preparation_card_test.dart`
- Extend: `mobile/test/home_realtime_preparation_gate_test.dart`
- Extend: `mobile/test/learning_repository_test.dart`

- [ ] RED-test exact V1/V2 key sets, strict integer-not-bool counts, nested canary invariants, three-subject sums, future schema rejection, `3/30` and `30/30` both not ready, repository V2 header on current/retry, and all malformed mutations producing zero Today/assign calls.
- [ ] Show `内容已通过 X/30`; at 30/30 show `30 门课程内容已通过，等待制作完整互动课件`. Keep server progress 35%; do not infer progress locally.
- [ ] Preserve the existing fresh authority sequence before Today and before assign.
- [ ] Run GREEN and full Flutter verification:

```bash
cd mobile && flutter test test/learning_preparation_models_test.dart \
test/learning_preparation_repository_test.dart \
test/learning_preparation_card_test.dart \
test/home_realtime_preparation_gate_test.dart \
test/learning_repository_test.dart
cd mobile && flutter analyze
cd mobile && flutter test
```

### Task 11: Verify Checkpoint 2 Without Real Provider, Then Run the Authorized Production Canaries

**Files:**

- Create: `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/checkpoint-2-evidence.md`
- No product edits during evidence collection.

- [ ] Run all CP2 backend suites serially, Sidecar tests, Flutter tests, `py_compile`, `node --check`, `flutter analyze`, and `git diff --check`.
- [ ] Apply migration 056 first to guarded test MySQL, replay it, test invalid DML, and prove residue zero. Then preflight development DB read-only; apply once only after exact schema/fingerprint/flag checks.
- [ ] Prove setup/profile/current/retry/today/assign/student and old catalog paths have zero Provider/package/Runtime/TTS/ASR/activation deltas.
- [ ] Enable only the CP2 runner/content flags and exact `primary_1` allowlist. Run the three ordinary build canaries through the worker, not through an ad-hoc generation endpoint.
- [ ] If all three pass, let the same build expand automatically to thirty. If any fails/ambiguous, stop; do not replay or widen.
- [ ] Record exact non-sensitive build/fingerprint/item/attempt/phase receipts, 30 immutable course identities, validator versions, content hashes, old release/task/session/report hashes, and all zero-bypass counters.
- [ ] Close CP2 flags after terminal handoff. Do not mark the plan ready and do not expose the candidate release to students.

---

## Phase II — Full Classroom, Audio, and Automatic Publication

### Task 12: Add the Grade-Scoped Candidate-to-Classroom State Contract

**Files:**

- Create: `backend/migrations/057_learning_curriculum_classroom_publication.sql`
- Modify: `backend/repositories/learning_curriculum_preparation_repository.py`
- Modify: `backend/repositories/learning_catalog_repository.py`
- Modify: `backend/repositories/openmaic_runtime_repository.py`
- Create: `backend/tests/test_learning_curriculum_classroom_publication_migration.py`
- Create: `backend/tests/test_learning_curriculum_classroom_repository.py`

**Data Contract:**

- Add grade-scoped active release pointer with `grade_code`, target fingerprint, contract version, release ID, activated timestamp, and prior pointer history.
- Add candidate runtime ownership binding to exact build item/course/package/target fingerprint before the release is active.
- Add per-item classroom, TTS, ASR-roundtrip, conversation-provider, and publication receipt state; separate machine `auto_validated` from human `approved`.
- Add plan stages `building_classrooms`, `generating_speech`, `validating`, and `publishing` with exact leases/deadlines and a completed formal-ready shape.

- [ ] RED-test restartable migration, legacy active release backfill, grade-pointer uniqueness, cross-grade isolation, nullable CHECK counterexamples, candidate runtime binding, terminal evidence, and rollback/readback.
- [ ] Implement only after tests fail; run repository/migration GREEN serially.

### Task 13: Generalize the Full Runtime Generator to Candidate Releases

**Files:**

- Modify: `backend/services/openmaic_full_runtime_service.py`
- Modify: `backend/repositories/openmaic_runtime_repository.py`
- Modify: `backend/services/openmaic_runtime_generation_runner.py`
- Modify: `backend/services/learning_classroom_generation_runner.py`
- Modify: `backend/services/lesson_package_service.py`
- Modify: `backend/services/lesson_package_validator.py`
- Modify: `backend/repositories/lesson_package_repository.py`
- Modify: `backend/integrations/openmaic_classroom_adapter.py`
- Modify: `backend/integrations/openmaic_full_runtime_client.py`
- Modify: `backend/services/learning_curriculum_preparation_contract.py`
- Modify: `backend/services/service_factory.py`
- Modify: `backend/core/config.py`
- Create: `openmaic-runtime/patches/0012-mira-candidate-runtime-idempotency.patch`
- Extend: `backend/tests/test_openmaic_full_runtime.py`
- Extend: `backend/tests/test_learning_classroom_generation_runner.py`
- Create: `backend/tests/test_formal_runtime_candidate_generation.py`

**Interface:**

```python
def issue_candidate_generation(
    self, *, build_item_id: str, course_id: str, course_version: str,
    package_id: str, package_version: int, target_fingerprint: str,
    runtime_request_id: str,
) -> Mapping[str, object]: ...
```

- [ ] RED-test removal of the active/sample-only hard-code, exact candidate binding, one classroom job per item, safe lost-response reconciliation, no fourth attempt, and no student launch while the candidate grade pointer is inactive.
- [ ] Require the formal classroom structural policy: exact ten ordered scenes, 5/2/3 distribution, exact widget config/behavior, one teacher plus four peers, all-scene speech, two distinct peer discussions, and real spotlight/highlight evidence.
- [ ] Keep whiteboard optional and fail closed on simplified, no-op, fake 3D, empty script, missing speech, or missing roster.
- [ ] Run focused Runtime and runner suites GREEN; no real Provider in tests.

### Task 14: Produce and Auto-Validate Subject Qwen3 Audio

**Preflight authority:** `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/task-14-preflight.md`

**Files:**

- Create: `backend/migrations/058_learning_formal_qwen_audio_receipts.sql`
- Modify: `backend/content/teacher_profiles.py`
- Modify: `backend/services/learning_media_materialization_service.py`
- Modify: `backend/services/learning_media_worker_runner.py`
- Modify: `backend/repositories/learning_teacher_media_repository.py`
- Modify: `backend/services/openmaic_full_runtime_service.py`
- Modify: `backend/integrations/openmaic_full_runtime_client.py`
- Modify: `backend/services/learning_curriculum_preparation_contract.py`
- Modify: `backend/repositories/learning_curriculum_preparation_repository.py`
- Modify: `backend/services/learning_classroom_generation_runner.py`
- Modify: `backend/repositories/learning_catalog_repository.py`
- Modify: `backend/core/config.py`
- Modify: `backend/services/service_factory.py`
- Create: `openmaic-runtime/patches/0013-mira-formal-subject-qwen-audio.patch`
- Modify: `openmaic-runtime/upstream.lock.json`
- Modify: `openmaic-runtime/scripts/native-runtime.sh`
- Modify: `openmaic-runtime/scripts/test-native-runtime.sh`
- Modify: `openmaic-runtime/docker-compose.yml`
- Modify: `openmaic-runtime/README.md`
- Extend: `backend/tests/test_teacher_profile_registry.py`
- Extend: `backend/tests/test_learning_curriculum_preparation_contract.py`
- Extend: `backend/tests/test_learning_teacher_media_assets.py`
- Extend: `backend/tests/test_openmaic_full_runtime.py`
- Create: `backend/tests/test_learning_formal_qwen_audio_migration.py`
- Create: `backend/tests/test_formal_qwen_audio_validation.py`

- [ ] Freeze one approved female/male-consistent subject teacher and Qwen3 voice per subject; teacher avatar, name, prompt, and voice must agree.
- [ ] Freeze formal-only voice identities as Chinese `mira_chinese_gentle@2`/Serena/female/zh-CN, Math `mira_math_clear@2`/Ethan/male/zh-CN, and English `mira_english_standard@2`/Jennifer/female/en-US; keep legacy sample Math/Serena isolated.
- [ ] Require exactly one speech action in each of the exact ten classroom scenes. Attach the resulting audio sidecar manifest without mutating the Task-13 classroom content hash.
- [ ] RED-test attempted-before-call, completed-after-download/write, no retry, POST/download timeouts, exact provider/model/voice/fallback metadata, full audio hash, container/PCM validity, duration/non-silence, ASR round-trip transcript threshold, and partial/crash/stale terminal behavior.
- [ ] Replace phonics/manual-review dead ends with versioned machine evidence `auto_validated`; never rewrite it as human approval.
- [ ] Task 14 may set the per-item TTS and ASR-roundtrip receipts to passed, but it must leave overall classroom `auto_validated=0` and `approved=0` until Task 15 supplies the distinct conversation-provider receipt.
- [ ] Keep all Provider keys server-owned and responses sanitized. Run media and Runtime suites GREEN.

### Task 15: Prove Real Conversation and ASR Readiness

**Files:**

- Create: `backend/migrations/059_learning_openmaic_provider_readiness.sql`
- Modify: `backend/integrations/openmaic_conversation_probe_client.py`
- Modify: `backend/services/openmaic_conversation_probe_service.py`
- Modify: `backend/services/openmaic_full_runtime_service.py`
- Modify: `openmaic-runtime/gateway/src/server.mjs`
- Create: `openmaic-runtime/patches/0014-mira-formal-provider-readiness.patch`
- Extend: corresponding backend, gateway, and Runtime tests

- [ ] RED-test that gateway-only `providerCall=false` proof cannot satisfy formal provider readiness.
- [ ] Add a separate, bounded, server-owned provider-readiness receipt: authenticated Kimi text turn, one Qwen ASR transcript of a non-sensitive generated validation clip, fixed Qwen live TTS identity, no client overrides, bounded no-retry/explicit retry semantics, and no raw response persistence.
- [ ] Keep route/session proof and Provider proof distinct and require both for formal publication.
- [ ] Rebuild the numbered Runtime patch from the pinned upstream commit; clean replay twice, reverse-check, hash, TypeScript/Vitest/gateway/native health tests.

### Task 16: Atomically Publish One Complete Grade Release

**Files:**

- Modify: `backend/services/learning_catalog_release_service.py`
- Modify: `backend/repositories/learning_catalog_repository.py`
- Modify: `backend/repositories/learning_repository.py`
- Modify: `backend/repositories/student_learning_library_repository.py`
- Modify: `backend/services/learning_curriculum_preparation_runner.py`
- Modify: `backend/services/learning_curriculum_preparation_service.py`
- Create: `backend/tests/test_learning_grade_atomic_publication.py`
- Extend: `backend/tests/test_learning_catalog_release.py`
- Extend: `backend/tests/test_learning_curriculum_preparation_runner.py`

**Interface:**

```python
def activate_grade_release(
    self, *, grade_code: str, build_id: str,
    target_fingerprint: str, publication_request_id: str,
) -> Mapping[str, object]: ...
```

- [ ] RED-test all thirty course/package/runtime/audio/provider receipts, current contracts, no partial activation, same-key idempotency, different-key conflict, two concurrent publishers with one winner, old grade release preserved on any failure, other grades unchanged, and historical sessions pinned.
- [ ] In one transaction lock the grade pointer/build/release/items, revalidate all evidence, switch the pointer, publish the candidate release, write append-only event/receipt, and complete all matching current plans at `ready/completed/100%`.
- [ ] Remove any global curriculum-version retirement behavior from the grade-scoped path; retain it only for explicitly legacy operator calls.

---

## Phase III — Student Consumption and Learning Evidence

### Task 17: Make Student Library and Launch Resolve the Active Grade Pointer

**Files:**

- Create: `backend/migrations/060_learning_student_formal_session_bindings.sql`
- Modify: `backend/repositories/student_learning_library_repository.py`
- Modify: `backend/repositories/openmaic_runtime_repository.py`
- Modify: `backend/repositories/learning_repository.py`
- Modify: `backend/services/student_learning_service.py`
- Modify: `backend/services/learning_service.py`
- Modify: `backend/services/openmaic_full_runtime_service.py`
- Modify: `backend/routes/api/v2/student_learning.py`
- Modify: `student-web/src/lib/contracts/openmaic-runtime.ts`
- Extend: `backend/tests/test_student_learning_api.py`
- Extend: `backend/tests/test_student_classroom_release_gate.py`
- Extend: `backend/tests/test_openmaic_full_runtime.py`

- [ ] RED-test child-grade pointer selection, exact released course/package/runtime version, old-session pinning, sibling isolation, one-time 30–300 second launch ticket, no sample skill hard-code, no launch before formal ready, and zero generation from library/start/launch.
- [ ] Implement the active grade pointer join and remove the `primary_1/math/number_sense_20` production launch restriction.
- [ ] Preserve all existing session ownership, token hashing, revocation, CSP, gateway, and student white-label gates.

### Task 18: Add the Authenticated Runtime Progress and Completion Bridge

**Files:**

- Create: `backend/migrations/061_learning_openmaic_runtime_events.sql`
- Modify: `backend/repositories/lesson_package_repository.py`
- Modify: `backend/services/lesson_runtime_service.py`
- Modify: `backend/services/learning_service.py`
- Add: an internal Runtime-event route under `backend/routes/internal/openmaic_runtime.py`
- Modify: `openmaic-runtime/gateway/src/server.mjs`
- Create: `openmaic-runtime/patches/0015-mira-student-runtime-events.patch`
- Modify: `student-web/src/features/classroom/full-openmaic-classroom.tsx`
- Extend: backend/gateway/Runtime/Student Web tests

**Event Contract:**

```text
mira.openmaic.student-runtime-event.v1
scene_entered | action_completed | answer_submitted | classroom_completed
```

- [ ] RED-test cookie/session/runtime/classroom/release binding, increasing event sequence, deterministic idempotency key, allowlisted fields, replay returning the same receipt, gap/stale/wrong-session rejection, and zero arbitrary postMessage trust.
- [ ] Runtime sends to its same-origin gateway; gateway injects trusted session headers and forwards to backend. Student Web never becomes the authority for iframe payloads.
- [ ] Map authoritative answers through the existing Mira answer/scoring path; update cursor/runtime records transactionally; call `_complete_and_report` exactly once only after all required evidence is complete.
- [ ] Test pause/reload/resume, duplicate completion, lost response, session expiry, and historical version pinning.

### Task 19: Complete Parent and Student UI for the Formal States

**Files:**

- Modify: Flutter preparation card/Home/profile files from Task 10
- Modify: Student Web learning/library/classroom entry files
- Extend: Flutter widget/golden/integration tests
- Extend: Student Web Vitest/Playwright tests

- [ ] Show real stages: content, interactive classroom, speech, validation, publication, ready; show safe retry only when backend permits it.
- [ ] Open Today only after fresh formal-ready evidence; list only the active grade release; resume a pinned in-progress session even after a later release switch.
- [ ] Preserve student white-label chrome, hidden download/settings/theme/language controls, female-teacher avatar/voice consistency, autoplay default off/session-local, and no OpenMAIC branding in HTML/assets/errors/network-visible messages.
- [ ] Add no-mock browser tests against real local backend/gateway/Runtime services; mock-only tests remain unit contracts but are not release evidence.

### Task 20: Production Operations, Rollback, and Release Verification

**Files:**

- Modify: `backend/core/config.py`, `backend/.env.example`, `backend/README.md`
- Modify: Runtime managed-stack/native health policy and tests
- Create: `backend/scripts/verify_grade_release.py`
- Create: `docs/runbooks/grade-triggered-formal-learning-release.md`
- Create: `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/final-evidence.md`

- [ ] Add default-off independent gates for content generation, classroom generation, audio validation, automatic grade publication, and student release. Health must attest exact contract/patch/allowlist versions so an old healthy process cannot pass.
- [ ] Add safe runner metrics/structured observations: lease age, stage deadline, claimable/running/failed plans, build/item/dispatch counts, Provider usage evidence, publication pointer, and event lag without IDs, prompts, credentials, or child content.
- [ ] Implement read-only preflight and postflight verifier; no destructive rollback command. Rollback is one grade-pointer transaction to the previous fully validated release, never deletion or mutation of historical artifacts.
- [ ] Run all backend related suites serially, all Sidecar/Runtime/gateway/Student Web tests, full Flutter tests/analyze, clean Runtime patch replay, migration 056–061 replay/readback, and security/zero-call matrices.
- [ ] In development, run the actual parent grade selection through background preparation, thirty content candidates, thirty full classrooms/audio receipts, atomic publication, student authentication/library/session/launch, classroom interaction, completion, and parent report. No direct status edits or test fixture inserts.
- [ ] Repeat the same flow from a clean second child of the same grade and prove reuse: zero content/classroom/TTS generation delta, new child plan/session only, same active grade release.
- [ ] Keep production gates off until all evidence is signed off. Then enable one grade allowlist, monitor, and retain immediate pointer rollback.

## Completion Definition

This plan is complete only when all of the following are true:

1. Parent grade save atomically reserves/reuses a plan and returns immediately with zero external work.
2. The background pipeline creates the exact Grade-1 thirty-course shared build, passes the real three-course canary, and completes all content without hidden Provider replay.
3. All thirty courses have validated ten-scene interactive Runtime artifacts and subject-consistent Qwen3 speech with real route/provider receipts.
4. A single grade-scoped transaction publishes the release; partial or failed builds never affect students and the previous release remains recoverable.
5. An authenticated student can open the active release, complete interactions and authoritative answers, resume after refresh, and produce exactly one completion/report/mastery result.
6. A second same-grade child reuses the published release without generation.
7. Parent and student interfaces use real backend state, not mock success; Today/student requests never trigger generation.
8. Default-off gates, health attestation, observability, safe error handling, migration replay, and pointer rollback are verified.
9. No human course review is required, but every machine decision is versioned, auditable, and fail closed.
10. Only then may the flow be called production-ready and eligible for rollout.
