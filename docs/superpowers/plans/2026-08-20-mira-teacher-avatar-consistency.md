# Mira Teacher Avatar Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the fixed Mira sample teacher display a female avatar consistently with the server-owned Qwen3-TTS Serena voice, including the already-published immutable sample classroom.

**Architecture:** Add one client/server-safe Mira teacher identity module containing the fixed agent ID and avatar. Future deterministic artifacts write that avatar directly; legacy artifacts are normalized only while hydrating the exact fixed teacher into the in-memory registry. Classroom UI selects the loaded generated teacher instead of the unrelated default teacher, while ordinary operator/default agents remain unchanged.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zustand, Vitest, Bash runtime health checks, replayable upstream patch chain.

**Spec:** User feedback in the 2026-08-20 staged classroom review; existing Qwen teacher contract in `backend/content/teacher_profiles.py` and runtime policy in `openmaic-runtime/.runtime/OpenMAIC/lib/server/mira-tts-policy.ts`.

## Global Constraints

- Do not modify the immutable published classroom JSON or its content/audio hashes.
- Do not call Kimi, Qwen TTS, Qwen ASR, or any other provider.
- Do not approve, release, assign, or create student data.
- Preserve the ordinary operator/default teacher avatar and all non-teacher avatars.
- Ship the runtime change as a new patch after `0009`; do not rewrite prior patches.
- The shared worktree is already dirty with user-owned work, so use scoped diffs instead of commits.

---

### Task 1: Freeze the visual teacher identity in tests

**Files:**
- Modify: `openmaic-runtime/.runtime/OpenMAIC/tests/server/mira-sample-deterministic-classroom.test.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/tests/lib/orchestration/apply-generated-agents.test.ts`
- Create: `openmaic-runtime/.runtime/OpenMAIC/tests/lib/orchestration/classroom-teacher-selection.test.ts`

**Interfaces:**
- Consumes: existing deterministic classroom and generated-agent registry APIs.
- Produces: failing contracts for the fixed female avatar, legacy-roster normalization, and generated-teacher selection.

- [ ] **Step 1: Add literal expectations**

  Assert the exact teacher tuple `{id: "mira-sample-teacher", role: "teacher", avatar: "/avatars/teacher-2.png", voiceConfig: {providerId: "qwen-tts", modelId: "qwen3-tts-flash", voiceId: "Serena"}}`. Assert a legacy sample teacher carrying `/avatars/teacher.png` hydrates as `/avatars/teacher-2.png`, while `default-1` and unrelated generated teachers retain their configured avatars. Assert classroom teacher selection prefers the loaded generated teacher and falls back to the default teacher only when no generated teacher exists.

- [ ] **Step 2: Run the three focused test files**

  Run `pnpm exec vitest run tests/server/mira-sample-deterministic-classroom.test.ts tests/lib/orchestration/apply-generated-agents.test.ts tests/lib/orchestration/classroom-teacher-selection.test.ts` from `openmaic-runtime/.runtime/OpenMAIC` and confirm failures are caused by the current male avatar/default-teacher selection.

### Task 2: Implement one teacher identity source

**Files:**
- Create: `openmaic-runtime/.runtime/OpenMAIC/lib/mira/sample-teacher-identity.ts`
- Create: `openmaic-runtime/.runtime/OpenMAIC/lib/orchestration/registry/classroom-teacher-selection.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/lib/server/mira-sample-deterministic-classroom.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/lib/server/mira-sample-structural-policy.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/lib/orchestration/registry/store.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/components/agent/agent-bar.tsx`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/components/chat/use-chat-sessions.ts`

**Interfaces:**
- Produces: `MIRA_SAMPLE_TEACHER_ID`, `MIRA_SAMPLE_TEACHER_AVATAR`, `normalizeMiraSampleTeacherAvatar`, and `selectLoadedClassroomTeacher`.
- Consumes: the fixed teacher ID in the deterministic roster and loaded generated-agent flags in the registry.

- [ ] **Step 1: Add the minimal identity module**

  Normalize only the exact `mira-sample-teacher` with role `teacher`; return all other agents unchanged.

- [ ] **Step 2: Write the correct avatar at source and fail closed**

  The deterministic factory uses the fixed avatar for the teacher and the existing palette for peers. The structural validator rejects a sample teacher with any other avatar.

- [ ] **Step 3: Support the immutable current classroom**

  Apply the same exact normalization while hydrating generated agents. This changes only the in-memory display identity and does not rewrite the classroom artifact.

- [ ] **Step 4: Select the loaded classroom teacher in UI**

  AgentBar and lecture-session metadata use the generated classroom teacher when present, otherwise retain the existing default teacher behavior.

- [ ] **Step 5: Re-run focused tests**

  Run the Task 1 command and require zero failures.

### Task 3: Make runtime readiness distinguish the fix

**Files:**
- Modify: `openmaic-runtime/.runtime/OpenMAIC/lib/mira/student-runtime.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/tests/runtime/mira-student-runtime.test.ts`
- Modify: `openmaic-runtime/.runtime/OpenMAIC/tests/server/health-route.test.ts`
- Modify: `openmaic-runtime/scripts/native-runtime.sh`
- Modify: `openmaic-runtime/scripts/test-native-runtime.sh`
- Modify: `openmaic-runtime/README.md`

**Interfaces:**
- Produces: exact `mira-student-chrome.v2` health attestation with the fixed teacher agent ID and avatar.

- [ ] **Step 1: Add failing readiness expectations**

  Expect student chrome policy v2 plus `teacherIdentity: {agentId: "mira-sample-teacher", avatar: "/avatars/teacher-2.png"}`.

- [ ] **Step 2: Update the health policy and native validator**

  Use exact JSON equality so a process still serving the male-avatar policy is not accepted as healthy.

- [ ] **Step 3: Run runtime policy and shell tests**

  Run focused Vitest policy/health tests and `bash scripts/test-native-runtime.sh`.

### Task 4: Package and verify the stage

**Files:**
- Create: `openmaic-runtime/patches/0010-mira-sample-teacher-identity.patch`
- Modify: `openmaic-runtime/README.md`

**Interfaces:**
- Produces: replayable patch 0010 based on the pinned upstream plus patches 0001 through 0009.

- [ ] **Step 1: Generate patch 0010 from a clean 0001-0009 baseline**

  Include only the files changed by Tasks 1-3; do not fold earlier patch content into 0010.

- [ ] **Step 2: Verify patch replay and static quality**

  Run focused Vitest, `pnpm exec tsc --noEmit`, targeted ESLint, Prettier check, native shell tests, `git diff --check`, clean bootstrap replay, and byte comparison of patch targets.

- [ ] **Step 3: Verify the real classroom without provider calls**

  Open the existing sample with `?mira=1` and confirm the visible teacher image is `/avatars/teacher-2.png`; confirm Qwen audio playback remains the existing artifact and no model/provider endpoint is called.

- [ ] **Step 4: Review scoped changes**

  Confirm no backend, database, classroom artifact, approval, release, or student task files were changed by this fix.
