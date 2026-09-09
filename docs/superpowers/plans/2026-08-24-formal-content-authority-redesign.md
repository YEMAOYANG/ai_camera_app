# Formal Content Authority Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two failed substring validators with versioned, bounded formal authorities that Task 4, Task 5 and Task 6 can prove before the production content flow continues.

**Architecture:** Task 4 owns a pure tri-state tens/ones lexer and Task 5 mirrors its behavior before ledger reservation through a literal cross-runtime corpus. Task 1 owns all ambiguous Grade-1 sentence vocabulary; Task 6 parses only complete productions projected from that sealed dataset. No database or public-wire change is permitted.

**Tech Stack:** Node.js ESM (`node:test`), Python 3 `unittest`, canonical JSON/SHA-256.

**Spec:** `docs/superpowers/specs/2026-08-24-formal-content-authority-redesign.md`

## Global Constraints

- Existing Scheme A authority applies; do not request another internal design confirmation.
- TDD is mandatory: each production change follows a recorded behavioral RED.
- Do not stage, commit, reset, clean or overwrite unrelated user changes.
- Do not call a database, Provider, Runtime, media, TTS, ASR, service or publication endpoint.
- Migration 056 and public API schemas remain byte-identical.
- Task 7 remains blocked until Tasks 4–6 independently pass their final gates.

---

### Task 1: Replace Task-4 number-sense searches with a tri-state lexer

**Files:**
- Modify: `backend/openmaic-sidecar/src/question-contract.mjs`
- Modify: `backend/openmaic-sidecar/test/question-phase-contract.test.mjs`

**Interfaces:**
- Produces: `classifyNumberSenseUnitPhrases(text)` returning exact keys `status,representations`.
- Consumes: existing NFKC and Python-whitespace helpers plus the sealed 0–20 pair authority.

- [ ] **Step 1: Add literal RED tables**

  Add independent literal expectations for the reviewer corpus: canonical pair/tens/context, placeholder and standalone-ones controls, plus missing tens, malformed connector/suffix, signs, decimals, exponent/radix, ASCII and Unicode division, repeated operators and trailing numeric continuation.

- [ ] **Step 2: Run the phase-contract test and record RED**

  Run: `cd backend/openmaic-sidecar && node --test test/question-phase-contract.test.mjs`

  Expected: current search implementation accepts the breaker examples.

- [ ] **Step 3: Implement the pure finite-state classifier**

  Replace `previousNonPythonWhitespaceIndex`, `isNumericLikeUnitTokenCharacter`, `numericLikeComponentBeforeUnit`, `associatedOnesComponent` and their search loop. Scan complete unit phrases and return one of the three frozen statuses; do not add another expanding regex.

- [ ] **Step 4: Route every Task-4 number-sense artifact through it**

  `assertNumberSenseRepresentations` rejects only `malformed`, preserves valid controls, and visits every nested string as before.

- [ ] **Step 5: Run focused and full Sidecar suites**

  Run the phase file, the Task-4 focused files, full `npm test`, and five `node --check` targets. All must pass without network.

### Task 2: Mirror the approved lexer before Task-5 ledger reservation

**Files:**
- Modify: `backend/integrations/openmaic_question_adapter.py`
- Modify: `backend/tests/test_openmaic_question_phase_adapter.py`
- Modify: `backend/tests/test_staged_content_candidate_generator.py`

**Interfaces:**
- Consumes: Task-4 literal tri-state behavior and the approved final Node file SHA.
- Produces: Python classification parity used by every phase 3/6/11/14 preflight path.

- [ ] **Step 1: Add Python literal RED and cross-runtime parity corpus**

  Each expected status is a test literal. Invoke the real Node export for parity, but do not use Node output as the expected value.

- [ ] **Step 2: Prove invalid artifacts currently reach Python acceptance**

  Run the adapter tests and generator zero-ledger tests; record the exact malformed cases that fail.

- [ ] **Step 3: Implement the Python mirror**

  Use NFKC and `str.isspace()` semantics, the same complete grammar and the same three statuses. Keep the classifier recursively immutable if included in exported authority.

- [ ] **Step 4: Prove zero-ledger/zero-process behavior**

  Phase 3/6 compiled artifacts and phase 11/14 course/repair artifacts with malformed phrases must fail before reservation. Existing dispatched-result ambiguity behavior remains unchanged.

- [ ] **Step 5: Run Task-2, V1 and Task-5 regressions**

  Run pure adapter/generator tests first, then guarded MySQL suites serially only if required by the existing Task-5 brief.

### Task 3: Seal sentence word-boundary and identity-complement authority

**Files:**
- Modify: `backend/content/primary_1_content_validation.v1.json`
- Modify: `backend/content/primary_skill_boundaries.py`
- Modify: `backend/tests/test_primary_grade_one_subject_validators.py`
- Modify: `backend/tests/test_learning_curriculum_preparation_contract.py`

**Interfaces:**
- Produces: grammar-v2 rules containing exact `markerBearingSubjectNouns` and `identityComplements`, a new canonical dataset hash, boundary version and target fingerprint.

- [ ] **Step 1: Write Task-1 authority REDs**

  Add exact-shape, missing/extra key, duplicate, empty, non-Han and rehashed-semantic mutation cases for both new inventories. Add literal assertions that the boundary projection exposes both lists.

- [ ] **Step 2: Run authority/preparation tests and record RED**

  Expected: missing keys and old grammar version fail the new contract.

- [ ] **Step 3: Amend the sealed JSON and typed projector**

  Add only the spec's bounded lists, advance the predicate grammar version, project the values into allowed content, recompute the canonical dataset pin and update exact target expectations.

- [ ] **Step 4: Verify hash and mutation authority**

  Run `json.tool`, Task-1 phase/authority/preparation tests and literal mutation tests. Record final dataset/boundary/target hashes for downstream tasks.

### Task 4: Replace Task-6 marker heuristics with complete productions

**Files:**
- Modify: `backend/services/learning_catalog_validator.py`
- Modify: `backend/tests/test_learning_catalog_validator.py`
- Modify: `backend/tests/test_learning_generated_course_validator.py`

**Interfaces:**
- Consumes: only Task-1 grammar-v2 typed inventories.
- Produces: deterministic content pass/rejection and unchanged Host receipt schema.

- [ ] **Step 1: Add full Host receipt REDs**

  Include every Task-6 breaker example, `太太工作。`, `老太太工作。`, `妈妈是太空人。`, existing controls, and invalid identity complements. Construct complete evidence and independently verify receipt outcome/hash.

- [ ] **Step 2: Run focused Host tests and record RED**

  Expected: current index-zero exception accepts malformed sentences and rejects valid ambiguous nouns.

- [ ] **Step 3: Implement whole-production parsing**

  Validate the subject with the sealed marker-bearing noun list, match bare/aspect/identity/description productions in full, and require exact identity/state complements. Delete fallback and marker-position heuristics; add no local vocabulary.

- [ ] **Step 4: Run Task-6, Task-1 and Task-3 regressions**

  Run the existing Task-6 focused suite, Task-1 authority/preparation suite and Task-3 pure state-machine suite; run `py_compile`, `tabnanny`, JSON hash and whitespace checks.

### Task 5: Freeze evidence and unblock Task 7

**Files:**
- Modify: `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/task-4-brief.md`
- Modify: `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/task-6-brief.md`
- Modify: `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/task-7-brief.md`
- Modify: `.superpowers/sdd/2026-08-21-grade-triggered-formal-production-flow/progress.md`

**Interfaces:**
- Produces: final Task-4/5/6 hashes and Task-7 dependency table.

- [ ] **Step 1: Record final fresh verification**

  Capture exact counts, hashes and zero-external-call evidence. Do not claim approval from implementation tests alone.

- [ ] **Step 2: Perform independent review locally against breaker matrices**

  Re-run the fixed literal matrices and inspect the final diff. Any same-root fail-open returns to the architecture, not another regex patch.

- [ ] **Step 3: Update dependency contracts**

  Replace provisional Task-4/5/6 hashes in Task 7 and retain its exact lease-identity ruling.

- [ ] **Step 4: Mark Task 7 executable**

  Only after all checks are green and no load-bearing P0/P1 remains.

## Self-Review

- Spec coverage: both five-round breakers, cross-runtime parity, sealed dataset
  drift and Task-7 handoff have explicit tasks.
- Placeholders: none; every step names the production boundary and command.
- Type consistency: Node/Python share the three statuses; Task 6 consumes only
  the two new Task-1 inventory names.
- Repository rule: commit steps are intentionally omitted because the active
  formal-flow plan forbids staging/committing the user's untracked worktree.
