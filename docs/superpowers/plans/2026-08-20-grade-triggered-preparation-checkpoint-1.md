# Grade-Triggered Preparation Checkpoint 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-safe vertical slice where saving a primary-school grade atomically reserves an idempotent curriculum-preparation plan and the parent app shows its real status without invoking any model or modifying historical learning data.

**Architecture:** A versioned target-contract module produces a canonical grade target and shared fingerprint. Setup/Profile save the grade and reserve a child-scoped plan in the same MySQL transaction. A separate authenticated parent API exposes the current plan and successor retries; a disabled-by-default lease runner proves recovery and shared-build binding without executing catalog items. Flutter renders preparation status first and only loads `/learning/today` after the plan is ready.

**Tech Stack:** Python 3, Flask, MySQL/PyMySQL, `unittest`, Flutter/Dart, Riverpod 3, Dio, Material 3.

**Spec:** `docs/superpowers/specs/2026-08-20-grade-triggered-curriculum-preparation-design.md`

## Global Constraints

- Initial target is exactly three variants per current boundary: `primary_1` has 30 courses; `primary_2` through `primary_6` have 27.
- Subjects are exactly `chinese`, `math`, and `english`; the API supplies the labels and counts instead of Flutter hard-coding completion claims.
- Grade-save, GET, retry, and student requests make zero OpenMAIC, Kimi, Qwen TTS, or Qwen ASR calls.
- No real generation, catalog activation, Runtime, Gateway, Student Web, Provider configuration, or development-database test records are in this checkpoint.
- The existing Serena policy is recorded only as the already-proven math-sample readiness baseline. Checkpoint 1 does not claim unregistered formal Chinese or English voice IDs; their required Qwen3 selections remain a fingerprinted fail-closed target that Checkpoint 2/3 must replace with a versioned approved subject-voice registry before Runtime generation.
- Do not modify or delete historical tasks, sessions, reports, courses, releases, or runtime rows.
- Repeated grade submissions are idempotent; `primary_1 -> primary_2 -> primary_1` creates a new grade-selection revision.
- A failed plan is immutable; retry creates one idempotent successor linked by `retry_of_plan_id`.
- The runner is disabled by default and may only reserve/bind a shared build; it must not call `LearningCatalogReleaseService.run()`.
- `/learning/today` remains read-only with respect to generation and is not requested by Flutter before preparation is ready.
- Preserve all unrelated dirty and untracked workspace changes. This shared worktree already contains user-owned changes in several target files, so implementation tasks must not run `git add` or `git commit`. Capture a path-scoped baseline before editing and hand off a path/hunk inventory; integration is deferred until the user reviews the checkpoint.

---

### Task 1: Canonical Preparation Target Contract

**Files:**
- Create: `backend/services/learning_curriculum_preparation_contract.py`
- Create: `backend/tests/test_learning_curriculum_preparation_contract.py`

**Interfaces:**
- Consumes: `PRIMARY_CURRICULUM_VERSION`, `PRIMARY_SKILL_BOUNDARIES`, `TEACHER_REGISTRY_VERSION`, `get_teacher_profile`, `OPENMAIC_QWEN3_VOICE_CONTRACT_VERSION`, `LESSON_PACKAGE_COMPILER_VERSION`, `SAMPLE_REQUIREMENT_SCHEMA`, `OpenMaicFullRuntimeService.MANIFEST_SCHEMA`, and `OpenMaicFullRuntimeClient.SAMPLE_RUNTIME_VERSION`.
- Produces: `PREPARATION_SCHEMA_VERSION`, `PREPARATION_CONTRACT_VERSION`, `build_preparation_target(grade_code: str) -> dict[str, object]`, and `preparation_target_fingerprint(target: Mapping[str, object]) -> str`.

- [ ] **Step 1: Write failing target-contract tests**

```python
class LearningCurriculumPreparationContractTest(unittest.TestCase):
    def test_primary_one_target_has_three_subjects_and_thirty_courses(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(target["schemaVersion"], "mira.learning.preparation-target.v1")
        self.assertEqual(target["subjects"], ["chinese", "math", "english"])
        self.assertEqual(target["variantsPerBoundary"], 3)
        self.assertEqual(target["boundaryCount"], 10)
        self.assertEqual(target["totalCourseCount"], 30)
        self.assertEqual(
            target["subjectTargets"],
            {
                "chinese": {"boundaryCount": 4, "totalCourseCount": 12},
                "math": {"boundaryCount": 3, "totalCourseCount": 9},
                "english": {"boundaryCount": 3, "totalCourseCount": 9},
            },
        )

    def test_other_primary_grades_have_twenty_seven_courses(self):
        for grade in range(2, 7):
            target = build_preparation_target(f"primary_{grade}")
            self.assertEqual(target["boundaryCount"], 9)
            self.assertEqual(target["totalCourseCount"], 27)
            self.assertEqual(
                target["subjectTargets"],
                {
                    "chinese": {"boundaryCount": 3, "totalCourseCount": 9},
                    "math": {"boundaryCount": 3, "totalCourseCount": 9},
                    "english": {"boundaryCount": 3, "totalCourseCount": 9},
                },
            )

    def test_formal_teacher_targets_are_subject_specific_and_sample_policy_is_scoped(self):
        target = build_preparation_target("primary_1")
        self.assertEqual(
            [target["teacherTargets"][subject]["teacherProfile"]["id"] for subject in target["subjects"]],
            ["mira_chinese_gentle", "mira_math_clear", "mira_english_standard"],
        )
        for subject in target["subjects"]:
            voice = target["teacherTargets"][subject]["formalVoiceSelection"]
            self.assertEqual(voice["status"], "required_before_runtime_generation")
            self.assertEqual(voice["providerId"], "qwen-tts")
            self.assertEqual(voice["modelId"], "qwen3-tts-flash")
            self.assertNotIn("voiceId", voice)
        self.assertEqual(
            target["sampleRuntimeReadiness"]["scope"],
            "primary_1_math_number_sense_20_only",
        )
        self.assertNotIn("ttsPolicy", target)

    def test_fingerprint_is_canonical_and_contract_sensitive(self):
        target = build_preparation_target("primary_1")
        first = preparation_target_fingerprint(target)
        reordered = dict(reversed(list(target.items())))
        self.assertEqual(first, preparation_target_fingerprint(reordered))
        changed = {**target, "fullRuntimeContractVersion": "mira.openmaic.formal-classroom.v2"}
        self.assertNotEqual(first, preparation_target_fingerprint(changed))

    def test_non_primary_grade_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported primary grade"):
            build_preparation_target("kindergarten_middle")
```

- [ ] **Step 2: Run the tests and confirm RED**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_contract_pycache python3 -m unittest tests.test_learning_curriculum_preparation_contract -v`

Expected: import failure for `services.learning_curriculum_preparation_contract`.

- [ ] **Step 3: Implement canonical target generation**

```python
PREPARATION_SCHEMA_VERSION = "mira.learning.preparation.v1"
PREPARATION_TARGET_SCHEMA_VERSION = "mira.learning.preparation-target.v1"
PREPARATION_CONTRACT_VERSION = "mira.learning.grade-preparation.v1"
VARIANTS_PER_BOUNDARY = 3
MAX_PARENT_RETRIES = 1
PREPARATION_SUBJECTS = ("chinese", "math", "english")
FORMAL_SUBJECT_TEACHERS = {
    "chinese": "mira_chinese_gentle",
    "math": "mira_math_clear",
    "english": "mira_english_standard",
}
FORMAL_SUBJECT_VOICE_CONTRACT_VERSION = (
    "mira.openmaic.subject-qwen3-voice-selection.pending.v1"
)

FORMAL_RUNTIME_CONTRACT_VERSION = "|".join(
    (
        OpenMaicFullRuntimeClient.SAMPLE_RUNTIME_VERSION,
        SAMPLE_REQUIREMENT_SCHEMA,
        OpenMaicFullRuntimeService.MANIFEST_SCHEMA,
    )
)

def build_preparation_target(grade_code: str) -> dict[str, object]:
    normalized = str(grade_code or "").strip()
    if normalized not in {f"primary_{grade}" for grade in range(1, 7)}:
        raise ValueError("unsupported primary grade")
    boundaries = [
        boundary
        for boundary in PRIMARY_SKILL_BOUNDARIES
        if boundary.grade_code == normalized
    ]
    boundary_targets = sorted(
        (
            {
                "subject": boundary.subject,
                "skillId": boundary.skill_id,
                "boundaryVersion": boundary.boundary_version,
            }
            for boundary in boundaries
        ),
        key=lambda item: (item["subject"], item["skillId"]),
    )
    subject_targets = {
        subject: {
            "boundaryCount": sum(
                1 for boundary in boundaries if boundary.subject == subject
            ),
            "totalCourseCount": sum(
                1 for boundary in boundaries if boundary.subject == subject
            ) * VARIANTS_PER_BOUNDARY,
        }
        for subject in PREPARATION_SUBJECTS
    }
    if any(item["boundaryCount"] <= 0 for item in subject_targets.values()):
        raise ValueError("primary grade target must include all three subjects")
    teacher_targets = {}
    for subject in PREPARATION_SUBJECTS:
        profile = get_teacher_profile(FORMAL_SUBJECT_TEACHERS[subject])
        if profile.subject != subject:
            raise ValueError("teacher target subject mismatch")
        teacher_targets[subject] = {
            "teacherProfile": {
                "id": profile.profile_id,
                "version": profile.version,
                "languageCode": profile.language_code,
                "avatarPath": profile.avatar_path,
            },
            "formalVoiceSelection": {
                "schemaVersion": FORMAL_SUBJECT_VOICE_CONTRACT_VERSION,
                "status": "required_before_runtime_generation",
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "fallbackAllowed": False,
            },
        }
    return {
        "schemaVersion": PREPARATION_TARGET_SCHEMA_VERSION,
        "preparationContractVersion": PREPARATION_CONTRACT_VERSION,
        "gradeCode": normalized,
        "subjects": list(PREPARATION_SUBJECTS),
        "curriculumVersion": PRIMARY_CURRICULUM_VERSION,
        "boundaries": boundary_targets,
        "boundaryVersions": [
            item["boundaryVersion"] for item in boundary_targets
        ],
        "boundaryCount": len(boundary_targets),
        "subjectTargets": subject_targets,
        "variantsPerBoundary": VARIANTS_PER_BOUNDARY,
        "totalCourseCount": len(boundary_targets) * VARIANTS_PER_BOUNDARY,
        "lessonPackageCompilerVersion": LESSON_PACKAGE_COMPILER_VERSION,
        "teacherRegistryVersion": TEACHER_REGISTRY_VERSION,
        "formalSubjectVoiceContractVersion": FORMAL_SUBJECT_VOICE_CONTRACT_VERSION,
        "teacherTargets": teacher_targets,
        "fullRuntimeContractVersion": FORMAL_RUNTIME_CONTRACT_VERSION,
        "sampleRuntimeReadiness": {
            "scope": "primary_1_math_number_sense_20_only",
            "voiceContractVersion": OPENMAIC_QWEN3_VOICE_CONTRACT_VERSION,
            "ttsPolicy": dict(OpenMaicFullRuntimeClient.SAMPLE_TTS_POLICY),
        },
        "asrPolicy": dict(OpenMaicFullRuntimeClient.SAMPLE_ASR_POLICY),
        "dialoguePolicy": dict(
            OpenMaicFullRuntimeClient.SAMPLE_STRUCTURED_SCENE_POLICY
        ),
    }

def preparation_target_fingerprint(target: Mapping[str, object]) -> str:
    canonical = json.dumps(
        dict(target), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run the contract tests and syntax check**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_contract_pycache python3 -m unittest tests.test_learning_curriculum_preparation_contract -v`

Expected: 5 tests pass.

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_contract_pycache python3 -m py_compile services/learning_curriculum_preparation_contract.py tests/test_learning_curriculum_preparation_contract.py`

Expected: exit 0 with no output.

- [ ] **Step 5: Record the contract-unit diff**

Run path-scoped `git status --short` and `git diff --check` for the two Task 1 files. Record their pre-edit and post-edit status; do not stage or commit in the shared dirty worktree.

---

### Task 2: Durable Plan Schema and Repository

**Files:**
- Create: `backend/migrations/054_learning_curriculum_preparations.sql`
- Create: `backend/repositories/learning_curriculum_preparation_repository.py`
- Create: `backend/tests/test_learning_curriculum_preparation_repository.py`

**Interfaces:**
- Consumes: canonical target JSON/fingerprint from Task 1 and existing `DatabaseConnection` transaction boundaries.
- Produces: `LearningCurriculumPreparationRepository` with `reserve_plan`, `get_plan`, `get_current_for_child`, `get_plan_for_family`, `create_retry_successor`, `supersede_current_nonterminal`, `supersede_other_nonterminal`, `claim_next`, `heartbeat`, `transition_stage`, `bind_shared_build`, `mark_retry_wait`, `mark_failed`, `mark_ready`, `release_lease`, and `append_event`.

- [ ] **Step 1: Write failing migration/repository tests**

Create tests that use `fresh_test_config()` and assert all of these exact behaviors:

```python
def test_same_revision_and_target_returns_one_plan(self):
    first, first_created = self.repository.reserve_plan(
        self.conn,
        family_id="fam_1",
        child_id="child_1",
        grade_code="primary_1",
        school_year_start_year=2026,
        grade_selection_revision=1,
        target=self.target,
        target_fingerprint=self.fingerprint,
        request_id="grade:child_1:1",
        shared_build_request_id=f"grade-build:{self.fingerprint}",
        now=1000,
    )
    second, second_created = self.repository.reserve_plan(
        self.conn,
        family_id="fam_1",
        child_id="child_1",
        grade_code="primary_1",
        school_year_start_year=2026,
        grade_selection_revision=1,
        target=self.target,
        target_fingerprint=self.fingerprint,
        request_id="grade:child_1:1",
        shared_build_request_id=f"grade-build:{self.fingerprint}",
        now=1001,
    )
    self.assertTrue(first_created)
    self.assertFalse(second_created)
    self.assertEqual(first["id"], second["id"])

def test_two_children_share_build_request_not_plan(self):
    self.assertNotEqual(first_child_plan["id"], second_child_plan["id"])
    self.assertEqual(
        first_child_plan["shared_build_request_id"],
        second_child_plan["shared_build_request_id"],
    )

def test_retry_creates_one_successor_and_keeps_failed_row(self):
    successor_a, created_a = self.repository.create_retry_successor(
        self.conn,
        failed_plan_id=failed["id"],
        family_id="fam_1",
        request_id="retry-1",
        now=2000,
    )
    successor_b, created_b = self.repository.create_retry_successor(
        self.conn,
        failed_plan_id=failed["id"],
        family_id="fam_1",
        request_id="retry-1",
        now=2001,
    )
    self.assertTrue(created_a)
    self.assertFalse(created_b)
    self.assertEqual(successor_a["id"], successor_b["id"])
    self.assertEqual(self.repository.get_plan(self.conn, failed["id"])["status"], "failed")

def test_claim_is_single_winner_and_lease_token_guards_late_writer(self):
    claimed = self.repository.claim_next(self.conn, now=3000, lease_ms=60_000)
    self.assertIsNotNone(claimed)
    self.assertIsNone(self.repository.claim_next(self.conn, now=3001, lease_ms=60_000))
    updated = self.repository.heartbeat(
        self.conn,
        plan_id=claimed["id"],
        lease_token="wrong-token",
        now=3002,
        lease_ms=60_000,
    )
    self.assertFalse(updated)

def test_current_prefers_current_revision_and_retry_successor(self):
    self.assertEqual(
        self.repository.get_current_for_child(
            self.conn,
            family_id="fam_1",
            child_id="child_1",
            grade_selection_revision=3,
            target_fingerprint=self.fingerprint,
        )["id"],
        retry_successor["id"],
    )

def test_full_fake_state_flow_is_monotonic(self):
    claimed = self.repository.claim_next(
        self.conn, now=4000, lease_ms=60_000
    )
    current_stage = "queued"
    stages = [
        "planning",
        "generating_content",
        "building_classrooms",
        "generating_speech",
        "validating",
        "publishing",
    ]
    for offset, stage in enumerate(stages, start=1):
        self.assertTrue(
            self.repository.transition_stage(
                self.conn,
                plan_id=claimed["id"],
                lease_token=claimed["lease_token"],
                expected_stage=current_stage,
                next_stage=stage,
                ready_course_count=min(offset * 4, 29),
                failed_course_count=0,
                subject_progress=self._subject_progress(min(offset * 4, 29)),
                now=4000 + offset,
                hard_deadline_at=60_000 + offset,
            )
        )
        current_stage = stage
    self.assertTrue(
        self.repository.mark_ready(
            self.conn,
            plan_id=claimed["id"],
            lease_token=claimed["lease_token"],
            expected_stage="publishing",
            ready_course_count=30,
            subject_progress=self._subject_progress(30),
            now=5000,
        )
    )
    self.assertFalse(
        self.repository.transition_stage(
            self.conn,
            plan_id=claimed["id"],
            lease_token=claimed["lease_token"],
            expected_stage="completed",
            next_stage="planning",
            ready_course_count=30,
            failed_course_count=0,
            subject_progress=self._subject_progress(30),
            now=5001,
            hard_deadline_at=65_000,
        )
    )
```

Use two independent MySQL connections plus a barrier to prove `claim_next` has one winner under `FOR UPDATE SKIP LOCKED`; the sequential wrong-token assertion is not sufficient by itself. Also execute `SHOW CREATE TABLE learning_curriculum_preparation_plans` and assert the unique keys for plan identity, request ID, and single retry successor are present.

- [ ] **Step 2: Run repository tests and confirm RED**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_repo_pycache python3 -m unittest tests.test_learning_curriculum_preparation_repository -v`

Expected: migration/table or repository import failure.

- [ ] **Step 3: Add migration 054**

The migration must be restart-safe under MySQL DDL implicit commits. Add the child column with the same `INFORMATION_SCHEMA.COLUMNS` + prepared-statement pattern used by migration 030, and use `CREATE TABLE IF NOT EXISTS` for both tables:

```sql
SET @add_children_grade_selection_revision = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE children ADD COLUMN grade_selection_revision INTEGER NOT NULL DEFAULT 0 AFTER grade_confirmed_at',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade_selection_revision'
);
PREPARE add_children_grade_selection_revision_stmt
  FROM @add_children_grade_selection_revision;
EXECUTE add_children_grade_selection_revision_stmt;
DEALLOCATE PREPARE add_children_grade_selection_revision_stmt;

CREATE TABLE IF NOT EXISTS learning_curriculum_preparation_plans (
  id VARCHAR(128) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  school_year_start_year INTEGER NOT NULL,
  grade_selection_revision INTEGER NOT NULL,
  curriculum_version VARCHAR(128) NOT NULL,
  preparation_contract_version VARCHAR(128) NOT NULL,
  target_spec_json LONGTEXT NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  request_id VARCHAR(128) NOT NULL,
  shared_build_request_id VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  stage VARCHAR(64) NOT NULL,
  catalog_build_id VARCHAR(128),
  catalog_release_id VARCHAR(128),
  total_course_count INTEGER NOT NULL,
  ready_course_count INTEGER NOT NULL DEFAULT 0,
  failed_course_count INTEGER NOT NULL DEFAULT 0,
  progress_percent INTEGER NOT NULL DEFAULT 0,
  subject_progress_json LONGTEXT NOT NULL,
  retry_of_plan_id VARCHAR(128),
  retry_ordinal INTEGER NOT NULL DEFAULT 0,
  resume_stage VARCHAR(64),
  lease_token VARCHAR(128),
  lease_expires_at BIGINT,
  heartbeat_at BIGINT,
  next_run_at BIGINT,
  hard_deadline_at BIGINT,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  last_progress_at BIGINT,
  started_at BIGINT,
  completed_at BIGINT,
  superseded_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_prep_identity(
    child_id, grade_selection_revision, target_fingerprint, retry_ordinal
  ),
  UNIQUE KEY uq_learning_prep_request(request_id),
  UNIQUE KEY uq_learning_prep_retry_source(retry_of_plan_id),
  INDEX idx_learning_prep_claim(status, stage, next_run_at, lease_expires_at),
  CONSTRAINT fk_learning_prep_family FOREIGN KEY (family_id) REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_learning_prep_child FOREIGN KEY (child_id) REFERENCES children(id) ON DELETE CASCADE,
  CONSTRAINT fk_learning_prep_retry FOREIGN KEY (retry_of_plan_id) REFERENCES learning_curriculum_preparation_plans(id) ON DELETE CASCADE,
  CONSTRAINT chk_learning_prep_status CHECK (
    status IN ('queued', 'running', 'ready', 'failed', 'superseded')
  ),
  CONSTRAINT chk_learning_prep_counts CHECK (
    total_course_count > 0
    AND ready_course_count >= 0
    AND failed_course_count >= 0
    AND ready_course_count + failed_course_count <= total_course_count
    AND progress_percent BETWEEN 0 AND 100
  )
);

CREATE TABLE IF NOT EXISTS learning_curriculum_preparation_events (
  id VARCHAR(128) PRIMARY KEY,
  plan_id VARCHAR(128) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  stage VARCHAR(64) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  created_at BIGINT NOT NULL,
  INDEX idx_learning_prep_events(plan_id, created_at),
  CONSTRAINT fk_learning_prep_event_plan FOREIGN KEY (plan_id)
    REFERENCES learning_curriculum_preparation_plans(id) ON DELETE CASCADE
);
```

Add explicit CHECK branches that require `completed_at` for `ready|failed|superseded`, require `error_code/error_message_safe` for `failed`, require `superseded_at` for `superseded`, and require lease fields to be either all NULL or all non-NULL. Constrain `stage` to `queued|planning|generating_content|building_classrooms|generating_speech|validating|publishing|retry_wait|completed`; terminal status/stage pairs must be `ready/completed`, `failed/completed`, and `superseded/completed`. Every terminal row clears `lease_token`, `lease_expires_at`, `heartbeat_at`, `next_run_at`, `hard_deadline_at`, and `resume_stage`. A ready row additionally requires `progress_percent=100`, `ready_course_count=total_course_count`, `failed_course_count=0`, and all error fields NULL. An unclaimed `status='queued', stage='queued'` row requires non-null `next_run_at` and null lease/deadline fields. A claimed `status='running', stage='queued'` row is also legal for the create-succeeded/bind-not-persisted recovery window and requires non-null lease/deadline fields while preserving the due `next_run_at`. Every other claimed nonterminal work stage requires non-null lease fields and `hard_deadline_at`; `retry_wait` requires non-null `next_run_at`, null lease fields, and a non-null `resume_stage` selected from the nonterminal work stages. Add `CHECK(JSON_VALID(target_spec_json))`, `CHECK(JSON_VALID(subject_progress_json))`, `CHECK(retry_ordinal BETWEEN 0 AND 1)`, and `CHECK(retry_of_plan_id IS NULL)` for ordinal 0 versus `IS NOT NULL` for ordinal 1. Use `IS NOT NULL` in every nullable evidence branch so MySQL UNKNOWN cannot bypass a CHECK.

Migration tests must simulate a partial apply by adding only `children.grade_selection_revision`, then rerun the migration and prove both tables/constraints are created exactly once. Add an account/family cleanup regression proving plan, retry successor, and event rows cascade before the child/family deletion completes.

- [ ] **Step 4: Implement repository CAS operations**

Use deterministic IDs derived from server-scoped request keys and an INSERT statement ending in `ON DUPLICATE KEY UPDATE id = id`. On a duplicate, re-read and compare family, child, revision, fingerprint, retry source, and retry ordinal before treating it as idempotent; any mismatch is a conflict. Every CAS state-changing method must return `cursor.rowcount == 1`. `claim_next` uses one `FOR UPDATE SKIP LOCKED` transaction and filters `next_run_at <= now`, `status IN ('queued','running')`, expired-or-null lease, and either a directly supported stage or `stage='retry_wait'` whose `resume_stage` is supported. Build the SQL `IN` parameter markers from the adapter's server-owned allowlisted tuple and bind every stage; never interpolate caller input. The winning update assigns `lease_token`, `lease_expires_at`, `heartbeat_at`, and `status='running'` before returning.

Define one allowed transition map in the repository/service and reject backward or terminal transitions. `progress_percent` is calculated server-side from stage weights plus completed course counts; it never uses elapsed frontend time. A `retry_wait` transition stores the previous work stage in `resume_stage`, clears the lease, and reclaims to that exact stage using the same request/build identity. Heartbeats extend only `lease_expires_at` and `heartbeat_at`; they never extend `hard_deadline_at`. `get_current_for_child` filters by the child's current revision and target fingerprint, orders by `retry_ordinal DESC`, and returns the successor over its failed source.

Use fixed stage floors `queued=0`, `planning=5`, `generating_content=10`, `building_classrooms=40`, `generating_speech=65`, `validating=85`, `publishing=95`, `completed=100`. Within a work stage, interpolate only from persisted completed-item facts and cap below the next floor; `retry_wait` keeps the last persisted percentage. Frontend clocks never alter progress.

`reserve_plan` initializes `subject_progress_json` from the canonical target's `subjectTargets` in the fixed chinese/math/english order, with ready/failed counts zero and exact totals 12/9/9 for Grade 1 or 9/9/9 for Grades 2–6. It also sets `next_run_at=now_ms`, `last_progress_at=now_ms`, `hard_deadline_at=NULL`, and all three lease fields to NULL. Every count update validates that per-subject sums equal the plan totals before the CAS is allowed.

`create_retry_successor` copies the immutable target, shared build identity, and already persisted catalog build/release references from its failed source, starts at `queued` with retry ordinal 1, sets `next_run_at=now_ms` and `last_progress_at=now_ms`, and clears `hard_deadline_at`, lease, error, and terminal timestamps. It may carry only downstream completion counts that the later stage adapter revalidates from authoritative tables; it never changes or reopens the failed source row.

Sanitize public errors through `DynamicLearningCourseRepository.sanitize_error`; event payloads may contain IDs, counts, stages, and safe codes only.

- [ ] **Step 5: Run repository and migration tests**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_repo_pycache python3 -m unittest tests.test_learning_curriculum_preparation_repository -v`

Expected: all repository tests pass.

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_repo_pycache python3 -m py_compile repositories/learning_curriculum_preparation_repository.py tests/test_learning_curriculum_preparation_repository.py`

Expected: exit 0.

- [ ] **Step 6: Record the schema/repository diff**

Run path-scoped status and whitespace checks for the three Task 2 files. Do not stage or commit; preserve any pre-existing untracked-file ownership in the handoff.

---

### Task 3: Atomic Grade Save and Plan Reservation

**Files:**
- Create: `backend/services/learning_curriculum_preparation_service.py`
- Modify: `backend/repositories/setup_repository.py:417-510`
- Modify: `backend/repositories/profile_repository.py:761-805`
- Modify: `backend/services/setup_service.py:55-75,265-405`
- Modify: `backend/services/profile_service.py:168-175,716-760,1663-1705`
- Modify: `backend/services/service_factory.py:130-150,500-520`
- Modify: `backend/tests/test_setup_api.py`
- Modify: `backend/tests/test_profile_family_settings_api.py`

**Interfaces:**
- Consumes: Task 1 target builder and Task 2 repository.
- Produces: `LearningCurriculumPreparationService.next_grade_selection_revision`, `reserve_for_saved_child`, `current`, `retry`, and `preparation_payload`. Setup/Profile responses expose `learningPreparation`.

- [ ] **Step 1: Add failing grade-save tests**

Add API assertions for:

```python
saved = self.client.post("/api/setup/child", json={
    "name": "乐乐",
    "nickname": "乐乐",
    "gradeCode": "primary_1",
    "schoolYearStartYear": current_year,
}, headers=self._auth_headers(access_token))
self.assertEqual(saved.status_code, 200)
self.assertEqual(saved.json["learningPreparation"]["status"], "queued")
self.assertEqual(saved.json["learningPreparation"]["totalCourseCount"], 30)
self.assertEqual(saved.json["learningPreparation"]["gradeLabel"], "一年级")
self.assertEqual(
    [item["label"] for item in saved.json["learningPreparation"]["subjects"]],
    ["语文", "数学", "英语"],
)

with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
    child = conn.execute("SELECT * FROM children WHERE id = ?", (saved.json["child"]["id"],)).fetchone()
    self.assertEqual(child["grade_selection_revision"], 1)
    self.assertEqual(
        conn.execute(
            "SELECT COUNT(*) AS count FROM learning_curriculum_preparation_plans WHERE child_id = ?",
            (child["id"],),
        ).fetchone()["count"],
        1,
    )
```

Then save the identical grade five times and assert revision and plan count remain 1; change to `primary_2` and assert revision 2 plus the old nonterminal plan is `superseded`; change back to `primary_1` and assert revision 3 with a new plan. Add a test that changing only nickname creates no plan and does not change revision. Patch `dynamic_learning_course_generation_service`, OpenMAIC, and TTS factories to fail the test if called; assert zero calls.

Add two real-MySQL concurrency tests with independent connections and a barrier: concurrent first Setup saves for one family must produce one child, revision 1, and one plan; concurrent Profile grade changes must serialize on the child and produce one current revision/plan without duplicate or lost supersede events.

- [ ] **Step 2: Run setup/profile tests and confirm RED**

Add a focused `ProfileFamilySettingsApiTest.test_child_grade_selection_reserves_preparation_plan` test, then run:

`cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_grade_pycache python3 -m unittest tests.test_setup_api.SetupApiTest.test_grade_based_setup_requires_name_and_nickname_then_persists tests.test_profile_family_settings_api.ProfileFamilySettingsApiTest.test_child_grade_selection_reserves_preparation_plan -v`

Expected: missing `learningPreparation` and missing `grade_selection_revision` assertions fail.

- [ ] **Step 3: Implement transaction-aware service**

Use this contract:

```python
class LearningCurriculumPreparationService:
    def next_grade_selection_revision(
        self,
        current: Mapping[str, object] | None,
        *,
        grade_code: str | None,
        school_year_start_year: int | None,
    ) -> int:
        previous = (
            str((current or {}).get("grade_code") or ""),
            int((current or {}).get("grade_school_year_start") or 0),
        )
        incoming = (str(grade_code or ""), int(school_year_start_year or 0))
        revision = int((current or {}).get("grade_selection_revision") or 0)
        return revision if current is not None and previous == incoming else revision + 1

    def reserve_for_saved_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child: Mapping[str, object],
        now: int,
    ) -> dict[str, object] | None:
        grade_code = str(child.get("grade_code") or "")
        if grade_code not in {f"primary_{grade}" for grade in range(1, 7)}:
            self.repository.supersede_current_nonterminal(
                conn, family_id=family_id, child_id=str(child["id"]), now=now
            )
            return None
        target = build_preparation_target(grade_code)
        fingerprint = preparation_target_fingerprint(target)
        revision = int(child["grade_selection_revision"])
        request_digest = hashlib.sha256(
            f"{child['id']}|{revision}|{fingerprint}".encode("utf-8")
        ).hexdigest()
        request_id = f"grade-prep:{request_digest}"
        shared_id = f"grade-build:{fingerprint}"
        plan, _ = self.repository.reserve_plan(
            conn,
            family_id=family_id,
            child_id=str(child["id"]),
            grade_code=grade_code,
            school_year_start_year=int(child["grade_school_year_start"]),
            grade_selection_revision=revision,
            target=target,
            target_fingerprint=fingerprint,
            request_id=request_id,
            shared_build_request_id=shared_id,
            now=now,
        )
        self.repository.supersede_other_nonterminal(
            conn,
            child_id=str(child["id"]),
            keep_plan_id=str(plan["id"]),
            now=now,
        )
        return self.preparation_payload(plan, now_ms=now)
```

The service constructor takes `database_url`, `auth_service`, and an optional repository for tests. It must not import or call Provider adapters.

- [ ] **Step 4: Lock child rows and reserve inside existing transactions**

For Setup, add `lock_family(conn, family_id)` using `SELECT id FROM families WHERE id = ? FOR UPDATE` before reading or creating the first child; locking an absent child row is not a concurrency boundary. Add `for_update: bool = False` to `SetupRepository.current_child`. Extend `save_child` to persist `grade_selection_revision` on both INSERT and UPDATE.

For Profile, add `for_update: bool = False` to `ProfileRepository.get_child` and make `_child_or_error(conn, family_id, child_id, for_update=True)` use it inside the update transaction. Both save flows calculate the revision while holding the stable lock, persist it with the grade fields, re-read the saved row, and call `reserve_for_saved_child(conn, family_id=family_id, child=saved_child, now=now)` before the transaction exits.

`SetupService.save_child` keeps its existing `_response(progress, details)` envelope. Add the preparation to `details` before calling `_response`:

```python
details = {"child": child_profile_payload(saved_child)}
if preparation is not None:
    details["learningPreparation"] = preparation
response = self._response(progress, details)
```

`ProfileService.update_child` keeps its direct response envelope:

```python
response = {"ok": True, "child": child_profile_payload(child)}
if preparation is not None:
    response["learningPreparation"] = preparation
```

Do not call the preparation service when no grade/school-year field was submitted and the current grade selection is unchanged. Explicitly re-submitting the same grade may call the idempotent reservation and return the existing plan; it must not increment the revision.

- [ ] **Step 5: Wire the singleton without nested transactions**

Add `learning_curriculum_preparation_service()` to `service_factory.py`. Inject that same instance into `SetupService` and `ProfileService`. The injected service receives the caller's `conn`; it must not open a transaction during reservation.

- [ ] **Step 6: Run grade-save regressions**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_grade_pycache python3 -m unittest tests.test_setup_api tests.test_profile_family_settings_api -v`

Expected: all setup/profile tests pass.

- [ ] **Step 7: Record the atomic-reservation diff**

Run path-scoped status and whitespace checks for Task 3 files and record which files were already dirty before implementation. Do not stage or commit.

---

### Task 4: Parent Status and Idempotent Retry API

**Files:**
- Modify: `backend/routes/api/v1/learning.py`
- Modify: `backend/services/learning_curriculum_preparation_service.py`
- Create: `backend/tests/test_learning_curriculum_preparation_api.py`

**Interfaces:**
- Consumes: authenticated service and repository from Tasks 2–3.
- Produces: `GET /api/learning/preparations/current` and `POST /api/learning/preparations/<plan_id>/retry`.

- [ ] **Step 1: Write failing API tests**

Cover 200 current, uniform 404 for unknown/other-family child or plan, non-primary `preparation: null`, 409 retry of non-failed or no-longer-current plan, 400 missing/extra request fields, cross-family reuse of the same client request ID, idempotent retry, one-manual-retry limit, and safe-error payload. Core assertions:

```python
current = self.client.get(
    "/api/learning/preparations/current",
    query_string={"childId": self.child_id},
    headers=self._auth_headers(),
)
self.assertEqual(current.status_code, 200)
self.assertEqual(current.json["preparation"]["schemaVersion"], "mira.learning.preparation.v1")
self.assertEqual(current.json["preparation"]["gradeLabel"], "一年级")
self.assertEqual(
    current.json["preparation"]["subjects"],
    [
        {
            "code": "chinese",
            "label": "语文",
            "readyCourseCount": 0,
            "failedCourseCount": 0,
            "totalCourseCount": 12,
        },
        {
            "code": "math",
            "label": "数学",
            "readyCourseCount": 0,
            "failedCourseCount": 0,
            "totalCourseCount": 9,
        },
        {
            "code": "english",
            "label": "英语",
            "readyCourseCount": 0,
            "failedCourseCount": 0,
            "totalCourseCount": 9,
        },
    ],
)
self.assertEqual(current.json["preparation"]["totalCourseCount"], 30)
self.assertNotIn("targetSpec", current.json["preparation"])
self.assertNotIn("leaseToken", current.json["preparation"])

self.clock.now_ms = self.plan_last_progress_at + 125_000
stale = self.client.get(
    "/api/learning/preparations/current",
    query_string={"childId": self.child_id},
    headers=self._auth_headers(),
)
self.assertEqual(stale.json["preparation"]["retryAfterMs"], 30_000)

first = self.client.post(
    f"/api/learning/preparations/{failed_plan_id}/retry",
    json={"requestId": "parent-retry-1"},
    headers=self._auth_headers(),
)
second = self.client.post(
    f"/api/learning/preparations/{failed_plan_id}/retry",
    json={"requestId": "parent-retry-1"},
    headers=self._auth_headers(),
)
self.assertEqual(first.status_code, 202)
self.assertEqual(second.status_code, 200)
self.assertEqual(first.json["preparation"]["id"], second.json["preparation"]["id"])
```

- [ ] **Step 2: Run API tests and confirm RED**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_api_pycache python3 -m unittest tests.test_learning_curriculum_preparation_api -v`

Expected: route 404 or import failure.

- [ ] **Step 3: Add routes**

```python
@learning_bp.get("/preparations/current")
def current_preparation():
    try:
        return jsonify(
            learning_curriculum_preparation_service().current(
                bearer_token(request), request.args
            )
        )
    except ApiError as exc:
        return error_response(exc)

@learning_bp.post("/preparations/<plan_id>/retry")
def retry_preparation(plan_id: str):
    try:
        payload, created = learning_curriculum_preparation_service().retry(
            bearer_token(request), plan_id, json_body(request)
        )
        return jsonify(payload), 202 if created else 200
    except ApiError as exc:
        return error_response(exc)
```

- [ ] **Step 4: Implement strict parent payloads**

`current()` requires `childId`, resolves AuthService context, and queries by both family and child. An unknown or other-family child/plan returns the same 404 so existence is not disclosed. `retry()` requires the exact key set `{"requestId"}`, validates `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`, locks the failed plan and its child, and verifies that grade revision and target fingerprint still match the child's current plan. It derives the stored global request key from `sha256(family_id + failed_plan_id + client_request_id)`; the client string is never used as a global key by itself:

```python
retry_digest = hashlib.sha256(
    f"{family_id}|{failed_plan_id}|{client_request_id}".encode("utf-8")
).hexdigest()
stored_retry_request_id = f"grade-prep-retry:{retry_digest}"
```

The duplicate path re-reads by `stored_retry_request_id` and verifies family, child, retry source, retry ordinal, grade revision, and target fingerprint before returning the existing successor. `current()` and `retry()` capture one server `now_ms` value and pass it to `preparation_payload(row, *, now_ms: int)`, which exposes only:

```python
{
    "schemaVersion": PREPARATION_SCHEMA_VERSION,
    "id": str(row["id"]),
    "childId": str(row["child_id"]),
    "gradeCode": str(row["grade_code"]),
    "gradeLabel": grade_definition_for_code(row["grade_code"]).label,
    "subjects": public_subject_progress(row),
    "status": str(row["status"]),
    "stage": str(row["stage"]),
    "progressPercent": int(row["progress_percent"]),
    "totalCourseCount": int(row["total_course_count"]),
    "readyCourseCount": int(row["ready_course_count"]),
    "failedCourseCount": int(row["failed_course_count"]),
    "attempt": int(row["retry_ordinal"]) + 1,
    "canRetry": (
        str(row["status"]) == "failed"
        and int(row["retry_ordinal"]) < MAX_PARENT_RETRIES
    ),
    "retryAfterMs": preparation_retry_after_ms(row, now_ms=now_ms),
    "message": safe_parent_message(row),
    "lastProgressAt": row.get("last_progress_at"),
    "updatedAt": int(row["updated_at"]),
    "completedAt": row.get("completed_at"),
    "error": public_safe_error(row),
}
```

`preparation_retry_after_ms` returns null outside `queued|running`. For active plans it derives an age only from the server clock and persisted `last_progress_at`: `<5s -> 2500`, `<15s -> 5000`, `<30s -> 10000`, `<60s -> 20000`, and otherwise `30000`. A real stage/count progress CAS updates `last_progress_at`, which resets the backoff; polling itself never does. `public_subject_progress` returns exactly three ordered entries `{code,label,readyCourseCount,failedCourseCount,totalCourseCount}` using labels owned by the backend contract. `public_safe_error` is either null or `{code,message}` after sanitization. Do not expose build IDs, release IDs, target spec, fingerprints, request IDs, lease values, raw errors, paths, prompts, or Provider details.

- [ ] **Step 5: Run API and authorization tests**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_api_pycache python3 -m unittest tests.test_learning_curriculum_preparation_api tests.test_learning_api -v`

Expected: all tests pass and `/learning/today` behavior is unchanged.

- [ ] **Step 6: Record the parent-API diff**

Run path-scoped status and whitespace checks for Task 4 files. Do not stage or commit.

---

### Task 5: Disabled-by-Default Lease Runner and Shared Build Reservation

**Files:**
- Create: `backend/services/learning_curriculum_preparation_runner.py`
- Modify: `backend/services/learning_curriculum_preparation_service.py`
- Modify: `backend/services/service_factory.py`
- Modify: `backend/core/config.py`
- Modify: `backend/app.py`
- Modify: `backend/.env.example`
- Modify: `backend/README.md`
- Create: `backend/tests/test_learning_curriculum_preparation_runner.py`
- Modify: `backend/tests/test_onvif_bootstrap_config.py`

**Interfaces:**
- Consumes: repository claims, a `PreparationStageAdapter` protocol, and `LearningCatalogReleaseService.create()` only in the production checkpoint adapter.
- Produces: `PreparationStageResult`, `CheckpointSharedBuildAdapter`, `LearningCurriculumPreparationRunner.run_once(app, now_ms)`, `start_learning_curriculum_preparation(app)`, and explicit config keys.

- [ ] **Step 1: Write failing runner tests**

Use fake repository/catalog services and assert:

```python
def test_run_once_reserves_shared_build_without_running_generation(self):
    result = runner.run_once(app, now_ms=1000)
    self.assertEqual(result["claimed"], 1)
    self.assertEqual(fake_catalog.create_calls[0]["variantsPerBoundary"], 3)
    self.assertEqual(fake_catalog.create_calls[0]["grades"], ["primary_1"])
    self.assertEqual(fake_catalog.create_calls[0]["subjects"], ["chinese", "math", "english"])
    self.assertEqual(fake_catalog.run_calls, [])
    self.assertEqual(repository.plan["stage"], "planning")
    self.assertEqual(repository.plan["next_run_at"], 121_000)
    self.assertIsNotNone(repository.plan["catalog_build_id"])

def test_lost_create_response_reuses_same_shared_request_after_lease_expiry(self):
    repository.crash_on_next_result_persist = True
    with self.assertRaises(SimulatedProcessCrash):
        runner.run_once(app, now_ms=1000)
    self.assertEqual(repository.plan["status"], "running")
    self.assertEqual(repository.plan["stage"], "queued")
    self.assertEqual(repository.plan["next_run_at"], 1000)
    first_request = fake_catalog.persisted_request_id

    repository.expire_lease(now_ms=92_000)
    repository.crash_on_next_result_persist = False
    second = runner.run_once(app, now_ms=92_001)
    self.assertEqual(second["sharedBuildRequestId"], first_request)
    self.assertEqual(fake_catalog.create_calls[-1]["requestId"], first_request)

def test_runner_disabled_does_not_claim(self):
    app.config["LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED"] = False
    runner.start(app)
    self.assertEqual(repository.claim_calls, 0)

def test_checkpoint_adapter_stops_at_planning_deadline_without_second_adapter_call(self):
    runner.run_once(app, now_ms=1000)
    self.assertEqual(len(fake_catalog.create_calls), 1)
    result = runner.run_once(app, now_ms=121_000)
    self.assertEqual(result["errorCode"], "preparation_stage_deadline_exceeded")
    self.assertEqual(repository.plan["status"], "failed")
    self.assertEqual(len(fake_catalog.create_calls), 1)
```

The fake repository defines `SimulatedProcessCrash(BaseException)` and raises it only at the boundary immediately before the result-persistence transaction. Production code gets no crash switch; because the claim transaction and adapter call have already completed while result persistence has not, the fixture faithfully leaves the committed lease/stage/identity for reclaim after expiry.

Also test:

- the claim transaction is closed before `adapter.advance()` and a fresh transaction is used for persistence;
- a deterministic catalog conflict becomes terminal `failed`;
- a transient unavailable result becomes `retry_wait` with `resume_stage='planning'` and `next_run_at`, then reclaims the same request/build identity;
- heartbeat extends only the lease, never the stage hard deadline;
- a plan at or beyond its stage hard deadline fails before the adapter is called;
- a late lease token cannot overwrite a newer claim;
- `TESTING=True` never starts the thread;
- an injected `FakePreparationStageAdapter` advances `queued -> planning -> generating_content -> building_classrooms -> generating_speech -> validating -> publishing -> ready` across separate `run_once` calls with zero Provider calls.
- fresh plans and retry successors are immediately claimable because `next_run_at == last_progress_at == created_at`, while lease fields and `hard_deadline_at` are NULL;
- every terminal transition clears lease, deadline, `next_run_at`, and `resume_stage` fields.

- [ ] **Step 2: Run runner tests and confirm RED**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_runner_pycache python3 -m unittest tests.test_learning_curriculum_preparation_runner -v`

Expected: runner import failure.

- [ ] **Step 3: Implement the generic coordinator and checkpoint adapter**

Define:

```python
@dataclass(frozen=True)
class PreparationStageResult:
    next_status: str
    next_stage: str
    ready_course_count: int
    failed_course_count: int
    subject_progress: Mapping[str, object]
    next_run_at: int
    catalog_build_id: str | None = None
    catalog_release_id: str | None = None
    hard_deadline_at: int | None = None

class PreparationStageAdapter(Protocol):
    @property
    def supported_stages(self) -> frozenset[str]:
        raise NotImplementedError

    def advance(
        self,
        plan: Mapping[str, object],
        *,
        now_ms: int,
        heartbeat: Callable[[], bool],
    ) -> PreparationStageResult:
        raise NotImplementedError

class PreparationTransientError(RuntimeError):
    """A safe, explicitly retryable dependency failure."""

class PreparationDeterministicError(RuntimeError):
    """A terminal contract, validation, authorization, or programming failure."""
```

`LearningCurriculumPreparationRunner.run_once` uses three transaction boundaries:

1. Open claim transaction; call `claim_next` with `eligible_stages=adapter.supported_stages` so it assigns the lease. When entering a new work stage it also assigns that stage's immutable hard deadline; reclaiming the same stage preserves an existing non-null deadline byte-for-byte. Then commit/close.
2. With no DB transaction held, call `adapter.advance`. Its heartbeat callback opens a short independent transaction and CAS-updates only heartbeat/lease expiry.
3. Open a new persistence transaction and apply `PreparationStageResult` with plan ID + lease token + expected stage + target fingerprint CAS, then append the safe event and clear/release the lease as directed. Every nonterminal result supplies an explicit `next_run_at`; fake-adapter transitions use `now_ms` for immediate continuation, while the checkpoint production adapter uses the immutable planning deadline.

Before step 2, compare `now_ms` to the immutable stage `hard_deadline_at`; expiration marks the plan failed without calling the adapter. Only `PreparationTransientError` and an allowlist of dependency failures (`ApiError` status 429/502/503/504, connection timeout, and connection reset) may enter `retry_wait` before the deadline. `PreparationDeterministicError`, catalog 400/401/403/404/409/422 responses, validation failures, database errors, assertion failures, and every unclassified exception fail terminally with a sanitized code. A transient exception writes `retry_wait`, `resume_stage`, bounded backoff, and no new request ID. A stale/lost response is tested as a process crash after the idempotent `catalog_service.create()` has persisted its result but before the runner's bind transaction; the plan retains its claimed `queued` stage and due `next_run_at`, then an expired lease is reconciled by re-running with the same shared request identity. The production runner never invents a new build request.

`CheckpointSharedBuildAdapter.supported_stages` is `{'queued', 'planning'}`. It calls only:

```python
payload = catalog_service.create({
    "requestId": plan["shared_build_request_id"],
    "title": f"Mira {plan['grade_code']} 正式课程",
    "grades": [plan["grade_code"]],
    "subjects": ["chinese", "math", "english"],
    "variantsPerBoundary": 3,
    "allowPartial": True,
})
```

It returns a result that binds `payload['build']['id']` and `payload['release']['id']`, leaves the honest public stage as `planning`, and schedules `next_run_at` at the unchanged two-minute planning hard deadline. If someone explicitly enables the Checkpoint 1 runner without installing Checkpoint 2, the next claim terminates with safe `preparation_stage_deadline_exceeded` before any generation call instead of remaining running forever. It must never call `catalog_service.run()` or `activate()`. The catalog service's existing idempotent `create()` reconciles a lost response under the same shared request ID. The fake adapter is test-only and provides the remaining stage results without models, network, or database shortcuts.

Stage hard-deadline constants are explicit: a queued claim receives the planning deadline of 2 minutes; generating content is 10 minutes per work unit; classroom building is 45 minutes; speech is 30 minutes; validating is 10 minutes; publishing is 2 minutes. A heartbeat never moves these values.

- [ ] **Step 4: Add explicit configuration**

Add:

```text
LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED=0
LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS=15
LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS=90
```

Plan reservation is an invariant of successful primary-grade save and has no kill switch; only the worker is disabled by default. `apply_test_defaults()` sets runner false. `validate_flask_config()` requires interval at least 5 and lease at least 30. `create_app()` calls `start_learning_curriculum_preparation(app)` after existing daily preparation startup.

- [ ] **Step 5: Run runner/config regressions**

Run: `cd backend && PYTHONPYCACHEPREFIX=/tmp/mira_prep_runner_pycache python3 -m unittest tests.test_learning_curriculum_preparation_runner tests.test_onvif_bootstrap_config -v`

Expected: all tests pass; no thread starts in tests.

- [ ] **Step 6: Record the runner diff**

Run path-scoped status and whitespace checks for Task 5 files. Do not stage or commit.

---

### Task 6: Flutter Preparation Model and API Gateway

**Files:**
- Create: `mobile/lib/src/features/learning/domain/learning_preparation_models.dart`
- Create: `mobile/lib/src/features/learning/application/learning_preparation_repository.dart`
- Modify: `mobile/lib/src/features/auth/application/session_data_invalidation.dart`
- Create: `mobile/test/learning_preparation_models_test.dart`
- Create: `mobile/test/learning_preparation_repository_test.dart`
- Create: `mobile/test/session_data_invalidation_test.dart`

**Interfaces:**
- Consumes: parent API from Task 4 and shared `ApiClient`.
- Produces: `LearningPreparation`, `LearningPreparationStage`, `LearningPreparationGateway`, `learningPreparationRepositoryProvider`, and `currentLearningPreparationProvider`.

- [ ] **Step 1: Write failing Dart model tests**

```dart
test('parses running preparation and subject progress', () {
  final value = LearningPreparation.fromJson({
    'schemaVersion': 'mira.learning.preparation.v1',
    'id': 'lcp_1',
    'childId': 'child_1',
    'gradeCode': 'primary_1',
    'gradeLabel': '一年级',
    'subjects': [
      {
        'code': 'chinese',
        'label': '语文',
        'readyCourseCount': 4,
        'failedCourseCount': 0,
        'totalCourseCount': 12,
      },
      {
        'code': 'math',
        'label': '数学',
        'readyCourseCount': 4,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
      {
        'code': 'english',
        'label': '英语',
        'readyCourseCount': 4,
        'failedCourseCount': 0,
        'totalCourseCount': 9,
      },
    ],
    'status': 'running',
    'stage': 'generating_speech',
    'progressPercent': 40,
    'totalCourseCount': 30,
    'readyCourseCount': 12,
    'failedCourseCount': 0,
    'attempt': 1,
    'canRetry': false,
    'retryAfterMs': 2500,
    'message': '正在生成老师讲解语音',
    'updatedAt': 1787200000000,
  });
  expect(value.stage, LearningPreparationStage.generatingSpeech);
  expect(value.totalCourseCount, 30);
  expect(value.subjects[1].label, '数学');
  expect(value.subjects[1].totalCourseCount, 9);
  expect(value.shouldPoll, isTrue);
});

test('unknown stage fails closed as queued display state', () {
  final value = LearningPreparation.fromJson(_payload(stage: 'future_stage'));
  expect(value.stage, LearningPreparationStage.queued);
  expect(value.isReady, isFalse);
});

test('malformed or future ready payload never opens today learning', () {
  final wrongStage = LearningPreparation.fromJson(
    _payload(status: 'ready', stage: 'future_stage'),
  );
  expect(wrongStage.isReady, isFalse);
  expect(
    () => LearningPreparation.fromJson(
      _payload(schemaVersion: 'mira.learning.preparation.v2'),
    ),
    throwsA(isA<LearningPreparationFormatException>()),
  );
  final incompleteCounts = LearningPreparation.fromJson(
    _payload(
      status: 'ready',
      stage: 'completed',
      progressPercent: 100,
      totalCourseCount: 30,
      readyCourseCount: 29,
      failedCourseCount: 0,
    ),
  );
  expect(incompleteCounts.isReady, isFalse);

  final inconsistentSubjects = LearningPreparation.fromJson(
    _payload(
      status: 'ready',
      stage: 'completed',
      progressPercent: 100,
      totalCourseCount: 30,
      readyCourseCount: 30,
      failedCourseCount: 0,
      subjects: _subjectPayload(readyCounts: [12, 9, 8]),
    ),
  );
  expect(inconsistentSubjects.isReady, isFalse);

  final emptyReady = LearningPreparation.fromJson(
    _payload(
      status: 'ready',
      stage: 'completed',
      progressPercent: 100,
      totalCourseCount: 0,
      readyCourseCount: 0,
      failedCourseCount: 0,
      subjects: _subjectPayload(totals: [0, 0, 0], readyCounts: [0, 0, 0]),
    ),
  );
  expect(emptyReady.isReady, isFalse);
  expect(
    () => LearningPreparation.fromJson(
      _payload(readyCourseCount: -1),
    ),
    throwsA(isA<LearningPreparationFormatException>()),
  );
});
```

- [ ] **Step 2: Run Dart tests and confirm RED**

Run: `cd mobile && flutter test test/learning_preparation_models_test.dart test/learning_preparation_repository_test.dart`

Expected: missing files/classes.

- [ ] **Step 3: Implement immutable models**

Define stages `queued`, `planning`, `generatingContent`, `buildingClassrooms`, `generatingSpeech`, `validating`, `publishing`, `retryWait`, `completed`. Add immutable `LearningPreparationSubject` with `code`, API-owned `label`, `readyCourseCount`, `failedCourseCount`, and `totalCourseCount`; add `LearningPreparationSafeError` with `code` and `message`. `LearningPreparation` mirrors the server's `gradeLabel`, top-level counts, `progressPercent`, `canRetry`, `lastProgressAt`, and terminal timestamps exactly. Parsing rejects any schema other than `mira.learning.preparation.v1`, every negative count, and a failed/ready count greater than its total. `isReady` requires the supported schema, `status == 'ready'`, `stage == completed`, `progressPercent == 100`, `totalCourseCount > 0`, `readyCourseCount == totalCourseCount`, `failedCourseCount == 0`, exactly the three supported subject rows, every subject total greater than zero, and subject ready/failed/total sums equal the top-level counts. `isFailed` requires `status == 'failed'` and `stage == completed`; `shouldPoll` only allows `queued|running` with a nonterminal supported stage; `retryAfter` clamps server milliseconds to 2–30 seconds. Keep all JSON parsing fail-closed and never infer ready from `progressPercent == 100` alone.

- [ ] **Step 4: Implement repository and providers**

```dart
abstract interface class LearningPreparationGateway {
  Future<LearningPreparation?> current(String childId);
  Future<LearningPreparation> retry({
    required String planId,
    required String requestId,
  });
}

final currentLearningPreparationProvider =
    FutureProvider.autoDispose.family<LearningPreparation?, String>(
      (ref, childId) => ref.watch(learningPreparationRepositoryProvider).current(childId),
    );
```

`current()` calls `/learning/preparations/current?childId={childId}`; a null `preparation` returns null. `retry()` posts exactly `requestId`. Convert Dio errors to `LearningPreparationException`; do not treat network errors as generation failures.

Add `currentLearningPreparationProvider` and its repository provider to `invalidateAuthenticatedSessionData`, and test that logout/family switching invalidates preparation state so one household cannot retain another household's preparation card.

- [ ] **Step 5: Run Dart repository/model tests**

Run: `cd mobile && flutter test test/learning_preparation_models_test.dart test/learning_preparation_repository_test.dart test/session_data_invalidation_test.dart`

Expected: all tests pass.

- [ ] **Step 6: Format, analyze, and record the diff**

Run: `cd mobile && dart format lib/src/features/learning/domain/learning_preparation_models.dart lib/src/features/learning/application/learning_preparation_repository.dart lib/src/features/auth/application/session_data_invalidation.dart test/learning_preparation_models_test.dart test/learning_preparation_repository_test.dart test/session_data_invalidation_test.dart`

Run: `cd mobile && flutter analyze`

Expected: no issues.

Run path-scoped status and whitespace checks for Task 6 files. Do not stage or commit.

---

### Task 7: Parent Home Status Card, Polling, and Today Gate

**Files:**
- Create: `mobile/lib/src/features/learning/presentation/widgets/learning_preparation_card.dart`
- Verify: `mobile/lib/src/features/home/presentation/home_screen.dart:65-92`
- Modify: `mobile/lib/src/features/home/presentation/widgets/home_primary_learning_preview.dart`
- Modify: `mobile/lib/src/app/realtime/app_realtime_helpers.dart:128-143`
- Modify: `mobile/lib/src/features/learning/application/learning_repository.dart:11-33`
- Modify: `mobile/lib/src/features/profile/presentation/profile_pages.dart:2320-2375`
- Modify: `mobile/test/home_primary_learning_preview_test.dart`
- Modify: `mobile/test/learning_repository_test.dart`
- Create: `mobile/test/learning_preparation_card_test.dart`
- Create: `mobile/test/goldens/learning_preparation_home_queued.png`
- Create: `mobile/test/goldens/learning_preparation_profile_failed.png`
- Create: `mobile/test/home_realtime_preparation_gate_test.dart`
- Create: `mobile/test/profile_child_preparation_test.dart`

**Interfaces:**
- Consumes: `currentLearningPreparationProvider` and `LearningPreparationGateway` from Task 6.
- Produces: visible stage/count/error/retry UI; `/learning/today` is mounted only for an explicit ready preparation.

- [ ] **Step 1: Add failing widget tests**

Use fake preparation and learning gateways. Assert:

```dart
testWidgets('queued preparation is visible and today is not requested', (tester) async {
  final preparation = FakePreparationGateway.running(stage: 'queued');
  final learning = CountingLearningGateway();
  await tester.pumpWidget(_app(preparation: preparation, learning: learning));
  await tester.pumpAndSettle();
  expect(find.text('正在准备约 30 门一年级课程'), findsOneWidget);
  expect(find.text('排队中'), findsOneWidget);
  expect(learning.todayCalls, 0);
});

testWidgets('failed generation offers controlled retry', (tester) async {
  final preparation = FakePreparationGateway.failed(canRetry: true);
  await tester.pumpWidget(_app(preparation: preparation));
  await tester.pumpAndSettle();
  expect(find.text('课程准备未完成'), findsOneWidget);
  await tester.tap(find.text('重新准备'));
  await tester.pumpAndSettle();
  expect(preparation.retryCalls, 1);
});

testWidgets('network refresh error never calls retry endpoint', (tester) async {
  final preparation = FakePreparationGateway.networkFailure();
  await tester.pumpWidget(_app(preparation: preparation));
  await tester.pumpAndSettle();
  await tester.tap(find.text('重新获取状态'));
  await tester.pumpAndSettle();
  expect(preparation.retryCalls, 0);
});

testWidgets('ready preparation mounts today learning exactly once', (tester) async {
  final preparation = FakePreparationGateway.ready();
  final learning = CountingLearningGateway();
  await tester.pumpWidget(_app(preparation: preparation, learning: learning));
  await tester.pumpAndSettle();
  expect(learning.todayCalls, 1);
});

testWidgets('missing preparation fails closed and never loads today', (tester) async {
  final preparation = FakePreparationGateway.missing();
  final learning = CountingLearningGateway();
  await tester.pumpWidget(_app(preparation: preparation, learning: learning));
  await tester.pumpAndSettle();
  expect(find.text('课程还没有开始准备'), findsOneWidget);
  expect(learning.todayCalls, 0);
});

testWidgets('new grade plan cannot reuse the previous grade today cache', (tester) async {
  final preparation = MutablePreparationGateway(
    currentValue: _readyPreparation(id: 'plan-a'),
  );
  final learning = CountingLearningGateway(
    todayResponses: [_today(title: 'A年级课程'), _today(title: 'B年级课程')],
  );
  final harness = await _pumpApp(
    tester,
    preparation: preparation,
    learning: learning,
  );
  await tester.pumpAndSettle();
  expect(learning.todayCalls, 1);
  expect(find.text('A年级课程'), findsOneWidget);

  preparation.currentValue = _queuedPreparation(id: 'plan-b');
  harness.container.invalidate(
    currentLearningPreparationProvider('child-1'),
  );
  await tester.pumpAndSettle();
  expect(learning.todayCalls, 1);

  preparation.currentValue = _readyPreparation(id: 'plan-b');
  harness.container.invalidate(
    currentLearningPreparationProvider('child-1'),
  );
  await tester.pumpAndSettle();
  expect(learning.todayCalls, 2);
  expect(find.text('A年级课程'), findsNothing);
  expect(find.text('B年级课程'), findsOneWidget);
});

testWidgets('direct ready plan replacement uses a new today key', (tester) async {
  final preparation = MutablePreparationGateway(
    currentValue: _readyPreparation(id: 'plan-a'),
  );
  final learning = CountingLearningGateway(
    todayResponses: [_today(title: 'A年级课程'), _today(title: 'B年级课程')],
  );
  final harness = await _pumpApp(
    tester,
    preparation: preparation,
    learning: learning,
  );
  await tester.pumpAndSettle();

  preparation.currentValue = _readyPreparation(id: 'plan-b');
  harness.container.invalidate(
    currentLearningPreparationProvider('child-1'),
  );
  await tester.pumpAndSettle();

  expect(learning.todayCalls, 2);
  expect(find.text('A年级课程'), findsNothing);
  expect(find.text('B年级课程'), findsOneWidget);
});
```

Add fake-async tests proving poll timers stop after `ready`, `failed`, widget disposal, and each of `AppLifecycleState.paused|inactive|hidden|detached`. For both resume and pull-to-refresh, make the preparation GET take three seconds while the previous payload advertises a 2.5-second delay: `HomeScreen` must issue exactly one fresh request, the child wrapper must cancel its old timer as soon as the provider enters loading/refreshing, and only the fresh provider result may schedule the next timer. Test 320×760, 390×844, and text scale 2.0 for overflow.

At a fixed 390×844 surface, add two `matchesGoldenFile` assertions for the queued Home card and failed Profile card. Generate them once with `flutter test --update-goldens test/learning_preparation_card_test.dart`, then run the same test without `--update-goldens`; these PNGs are the user-visible Checkpoint 1 artifact and are not evidence of a development-database rollout.

Update every pre-existing `home_primary_learning_preview_test.dart` harness to override the preparation gateway/provider explicitly. Tests for the existing ready learning UI use a ready preparation fixture; no widget test may fall through to the real Dio client after the new gate is introduced. Queued/missing/error tests assert both `todayCalls == 0` and `assignCalls == 0`.

- [ ] **Step 2: Run widget tests and confirm RED**

Run: `cd mobile && flutter test test/learning_preparation_card_test.dart test/home_primary_learning_preview_test.dart test/home_realtime_preparation_gate_test.dart test/profile_child_preparation_test.dart test/learning_repository_test.dart`

Expected: missing card/provider behavior assertions fail.

- [ ] **Step 3: Implement the focused card**

The shared file exports `LearningPreparationCard`, `LearningPreparationLoadingCard`, `LearningPreparationNetworkErrorCard`, and `LearningPreparationMissingCard`. Each receives only data and callbacks. They use the neutral `mobile/lib/src/shared/widgets/app_surface.dart` `AppSurface`, `StatusChip`, `AppPrimaryButton`/`AppSecondaryButton`, `AppColors`, `AppRadii`, and `AppTypography`; the learning feature must not import `features/home/presentation/widgets/home_shared.dart`. The data card renders stage text from a total switch, uses the exact subject and grade labels returned by the API, shows `readyCourseCount / totalCourseCount`, and renders a determinate progress bar only when total is positive. None starts timers or calls repositories.

- [ ] **Step 4: Gate today loading behind preparation**

Keep `HomePrimaryLearningPreview` as the public wrapper. Move the current `/learning/today` implementation into a private `_ReadyPrimaryLearningPreview` widget. The wrapper watches only preparation first:

```dart
final preparation = ref.watch(currentLearningPreparationProvider(widget.child.id));
return preparation.when(
  loading: () => const LearningPreparationLoadingCard(),
  error: (error, _) => LearningPreparationNetworkErrorCard(
    onRetry: () => ref.invalidate(
      currentLearningPreparationProvider(widget.child.id),
    ),
  ),
  data: (value) {
    if (value?.isReady == true) {
      return _ReadyPrimaryLearningPreview(
        child: widget.child,
        preparationId: value!.id,
      );
    }
    if (value == null) {
      return LearningPreparationMissingCard(
        onRefresh: _refreshPreparation,
      );
    }
    return LearningPreparationCard(
      preparation: value,
      onRefresh: _refreshPreparation,
      onRetry: value.canRetry ? _retryPreparation : null,
    );
  },
);
```

For a primary-learning child, `preparation == null` is not a legacy-ready signal. It fails closed and does not mount `todayLearningProvider`; the parent can refresh the status or re-save the confirmed grade to reserve the missing plan. Non-primary children never mount `HomePrimaryLearningPreview` in the existing `HomeScreen` branch.

Define the provider exactly as follows; `preparationId` is a cache/authority boundary and is never sent as a generation trigger:

```dart
typedef LearningTodayRequestKey = ({
  String childId,
  String preparationId,
});

final todayLearningProvider =
    FutureProvider.autoDispose.family<LearningToday, LearningTodayRequestKey>((
      ref,
      key,
    ) async {
      final repository = ref.watch(learningRepositoryProvider);
      final today = await repository.today(key.childId);
      if (today.state != LearningTodayState.recommended || today.lesson == null) {
        return today;
      }
      try {
        return await repository.assignToday(
          childId: key.childId,
          date: DateTime.now(),
          scheduledStart: '19:30',
        );
      } catch (error) {
        final message = error is LearningException
            ? error.message
            : '课程自动准备失败，请稍后重试';
        return today.withPreparationError(message);
      }
    });
```

`_ReadyPrimaryLearningPreview` receives the ready preparation ID and watches `todayLearningProvider((childId: widget.child.id, preparationId: widget.preparationId))`. Thus both `ready A -> queued B -> ready B` and direct `ready A -> ready B` select a new provider key and cannot reuse A. Update all helper/tests to pass the composite key.

Generate retry request IDs once per button action using `parent-prep-retry:<planId>:<milliseconds>`; disable the button until the response returns. Network refresh only invalidates GET.

- [ ] **Step 5: Gate HomeScreen resume and pull-to-refresh traffic**

Change `refreshHomeDataSilently(ref)` so it refreshes `profileSummaryProvider` first and obtains the child ID only from that successful fresh result, then performs the other non-learning home refreshes. If the profile refresh fails, skip both preparation and today refresh rather than trusting a stale grade. For a primary child it must await a fresh `currentLearningPreparationProvider(childId).future`; only a successful response whose value has `isReady == true` may refresh `todayLearningProvider((childId: childId, preparationId: value.id))`. A missing preparation, active preparation, failed preparation, profile error, or preparation GET error produces zero today/assign calls. Never use a stale cached ready value after a failed preparation refresh. Update `learning_repository_test.dart` so every provider read uses the composite key and add an assertion that the same child with two preparation IDs produces two independent requests.

Add `home_realtime_preparation_gate_test.dart` with a provider container/fakes that proves resume/pull helper behavior for missing, queued, failed, network-error, and ready values. Only ready may make one today request. This closes the out-of-widget path that previously refreshed today unconditionally.

- [ ] **Step 6: Add lifecycle-safe polling**

The wrapper state owns one `Timer`. A `ref.listen` on the preparation provider first cancels the timer for every loading, refreshing, or error transition; it schedules only after a newly delivered `AsyncData` whose value has `shouldPoll == true`, using the server-owned `value.retryAfter`. Also cancel on `paused|inactive|hidden|detached`, terminal status, and in `dispose()`. On `resumed`, cancel/keep the timer cancelled and do not restart from the old payload. `HomeScreen.didChangeAppLifecycleState` and pull-to-refresh remain the sole owners of `refreshHomeDataSilently`; when their fresh provider result is delivered, the same listener schedules the next timer. Do not write local persistence.

- [ ] **Step 7: Refresh after profile grade change**

In `_ChildProfileFormState._save`, compare the old normalized grade/school year with the saved result. If changed, invalidate `currentLearningPreparationProvider(_draft.id)` and show `年级已保存，课程已开始准备`; otherwise keep `孩子资料已保存`. In the profile form's primary-grade section, render the same shared `LearningPreparationCard` from the learning feature for a non-ready plan; use GET status as the authority rather than extending the existing `ProfileRepository.updateChild` return type. The profile form offers manual status refresh but owns no timer, so a retained Home tab and Profile route cannot create duplicate pollers. Setup intentionally discards the extra save-response field because it navigates to a fresh home mount, which performs the authoritative GET.

Add `profile_child_preparation_test.dart` proving: queued status is visible in the profile form; a real grade change invalidates the preparation provider and shows the new toast; nickname-only save keeps the old toast and does not invalidate; a network refresh error never calls the generation retry endpoint.

- [ ] **Step 8: Run widget and learning regressions**

Run: `cd mobile && flutter test --update-goldens test/learning_preparation_card_test.dart`

Expected: the two fixed-size review PNGs are generated.

Run: `cd mobile && flutter test test/learning_preparation_card_test.dart test/home_primary_learning_preview_test.dart test/home_realtime_preparation_gate_test.dart test/profile_child_preparation_test.dart test/learning_repository_test.dart test/setup_text_field_style_test.dart`

Expected: all tests pass and today-call count remains zero before ready.

Run: `cd mobile && flutter analyze`

Expected: no issues.

- [ ] **Step 9: Format and record the parent-UI diff**

Run: `cd mobile && dart format lib/src/features/learning/presentation/widgets/learning_preparation_card.dart lib/src/features/home/presentation/widgets/home_primary_learning_preview.dart lib/src/app/realtime/app_realtime_helpers.dart lib/src/features/learning/application/learning_repository.dart lib/src/features/profile/presentation/profile_pages.dart test/learning_preparation_card_test.dart test/home_primary_learning_preview_test.dart test/home_realtime_preparation_gate_test.dart test/profile_child_preparation_test.dart test/learning_repository_test.dart`

Run path-scoped status and whitespace checks for Task 7 files. Do not stage or commit.

---

### Task 8: Checkpoint Verification and Handoff

**Files:**
- Modify only if required by verified behavior: `backend/README.md`, `mobile/README.md`
- Verify: every file touched by Tasks 1–7

**Interfaces:**
- Consumes: completed checkpoint.
- Produces: evidence that the checkpoint is safe to show before real generation is connected.

- [ ] **Step 1: Run backend focused suite**

Run:

```bash
cd backend
PYTHONPYCACHEPREFIX=/tmp/mira_prep_final_pycache python3 -m unittest \
  tests.test_learning_curriculum_preparation_contract \
  tests.test_learning_curriculum_preparation_repository \
  tests.test_learning_curriculum_preparation_api \
  tests.test_learning_curriculum_preparation_runner \
  tests.test_setup_api \
  tests.test_profile_family_settings_api \
  tests.test_learning_api -v
```

Expected: all tests pass with no Provider/network call.

- [ ] **Step 2: Run migration replay and schema readback on the test database**

Use `fresh_test_config()` to rebuild `ai_camera_app_test`, then assert migration 054 appears exactly once, the two new tables exist, all unique/FK/CHECK constraints are present, and invalid terminal/NULL evidence inserts fail. Do not run migration 054 on `ai_camera_app_dev` in this checkpoint.

- [ ] **Step 3: Run Flutter focused and global checks**

Run:

```bash
cd mobile
flutter test \
  test/learning_preparation_models_test.dart \
  test/learning_preparation_repository_test.dart \
  test/session_data_invalidation_test.dart \
  test/learning_preparation_card_test.dart \
  test/home_primary_learning_preview_test.dart \
  test/home_realtime_preparation_gate_test.dart \
  test/profile_child_preparation_test.dart \
  test/learning_repository_test.dart \
  test/setup_text_field_style_test.dart
flutter analyze
flutter test
```

Expected: focused tests and full Flutter suite pass; analyze reports no issues.

- [ ] **Step 4: Prove no generation on request paths**

Run the setup-save, profile-save, current-status, retry, repeated `/learning/today`, and home-widget tests with generation/OpenMAIC/TTS adapters replaced by call-counting fakes. Record exact zero counts in the handoff.

- [ ] **Step 5: Inspect scope and whitespace**

Compare the recorded pre-edit baseline with `git status --short` and run `git diff --check --` followed by the exact Task 1–7 paths only. For files that were already untracked, use a direct syntax/formatter check rather than treating the entire file as newly owned.

Expected: no checkpoint-path whitespace errors; unrelated pre-existing dirty files remain untouched. Confirm no `backend/.env`, development DB, OpenMAIC Runtime, Gateway, or Student Web file changed.

- [ ] **Step 6: Request two-stage review**

Use `superpowers:requesting-code-review` for spec compliance first, then code quality. Fix only findings related to this checkpoint and re-run Steps 1–5.

- [ ] **Step 7: Record any verification-only documentation**

If verification required a README correction, include its path and hunk in the final inventory. Do not stage or commit in this shared dirty worktree.

- [ ] **Step 8: Stop for user-visible review**

Report exactly what is visible: saving a grade reserves one plan, home shows queued/stages/failure/retry, and today does not load before ready. Include clickable links to `mobile/test/goldens/learning_preparation_home_queued.png` and `mobile/test/goldens/learning_preparation_profile_failed.png` so the user can review both states without a development-database write. State explicitly that real catalog generation remains disabled until Checkpoint 2. Do not start Checkpoint 2 without user review.
