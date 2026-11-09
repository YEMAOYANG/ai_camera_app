# Agent Instructions

## Project Scope

This repository is for the Mira Guardian parent-facing app. Keep work focused on the parent mobile app experience: onboarding, auth, child profile, device binding, daily care dashboard, tasks, live care, alerts, rewards, privacy, family members, and settings.

Do not drift into hardware roadmap, RTSP/go2rtc internals, backend migration, or model-router work unless the user explicitly asks.

## Product References

Use these files as product and flow references:

- `README.md`
- `docs/app-design-brief.md`
- `docs/app-flow-and-state-matrix.md`
- `docs/mira_guardian_app_design_guidelines.md`
- `app-prototype-v4/index.html`
- `design/mira_guardian_high_fidelity_ui.html`

When implementing app screens, treat the HTML prototypes as business and interaction references unless the user says a specific design is the visual source of truth.

## Long-Term Product Architecture

This is not a throwaway app demo. Mira Guardian is a long-term parent-facing product that will connect to a self-developed AI camera hardware platform. When the user explicitly mentions `backend`, AI, Prompt, camera capability, device binding, self-developed hardware, hardware integration, camera runtime, go2rtc, RTSP, or device protocol work, treat the request as part of the broader architecture:

```text
Flutter parent App
  -> App backend API
  -> AI orchestration / prompt and policy registry
  -> device platform / camera runtime adapter
  -> future self-developed camera hardware
```

Python backend code should act as the App API, device-control orchestrator, AI Provider/Model/Prompt/Policy management center, and adapter boundary. Do not hard-code media-stream core logic, provider keys, RTSP URLs, camera models, or prompt text inside random routes, pages, or `server.py`-style files.

AI Prompt, model configuration, provider configuration, policy rules, and eval cases must be structured. Prefer prompt registries, versioned prompt files, provider/model registries, and scenario configs over scattered strings in route handlers or UI code.

## V1 Scope Discipline

V1 should complete the main product loop, not every future complex feature.

V1 must include the parent-side foundation for points, rewards, and redemption:

- point account
- point ledger
- reward items
- redemption records
- task reward grants
- parent-side manual redemption and fulfillment

Because V1 has no child-side App, child-initiated reward requests and parent approval can be represented as backend state/API boundaries and lightweight entry points, without a full child-app UI loop.

V1 does not implement a full alert business loop, but should preserve clear boundaries for alert center, safety alerts, safety zones, and safety events.

V1 does not execute real hardware OTA updates, but firmware version, device version, OTA job, rollout policy, update status, command, and device receipt models/interfaces should be reserved.

V1 may use mock/dev SMS verification, but the backend must abstract an `SmsProvider` so Aliyun, Tencent Cloud, Ronglian, Twilio, or another provider can be integrated without changing Flutter login logic.

Complex AI evaluation backend UI should be evaluated before implementation. V1 does not need a full eval UI, but should reserve structures such as prompt registry, prompt version, scenario case, and eval result.

Do not create a standalone "today flow", "today plan", `daily_flow`, or `daily_plan` domain. The product now has only the `tasks` module for plans, schedules, to-dos, sleep tasks, schoolbag tasks, and parent confirmations. The home screen may show a today task summary, but the underlying business data belongs to tasks.

## Reference Priority

For business flow, page inventory, and interaction state, `app-prototype-v4/index.html` is the current primary reference. Requirements documents are still required reading for product goals, user scenarios, state matrices, design principles, and roadmap context.

If documents and `app-prototype-v4/index.html` conflict, default to `app-prototype-v4/index.html`. If the prototype contains an obviously unreasonable business flow, copy, state, or page structure, explain why and then adjust using README/docs product judgment.

Before backend, device, AI, or Flutter integration changes, output the architecture impact, planned file changes, and API contract before editing code.

## Design Rules

- Preserve the requested business flow and page map. Do not drop secondary pages, detail pages, dialogs, sheets, toasts, loading states, empty states, error states, or success states.
- If the user provides a Stitch/Figma/screenshot design, that design controls visual style and layout. The HTML prototype then controls business logic, states, copy intent, and navigation.
- Avoid generic AI UI patterns: card piles, overused blue-purple gradients, decorative glassmorphism, emoji icons, and backend-admin layouts.
- Keep the app parent-facing: calm, trustworthy, precise, and warm without becoming childish.

## Courseware

The single standard for every new courseware lesson, across subjects and grades, is `docs/learning/courseware-standard.md`: official-resource notes before authoring, the 1280×720 interactive page frame and shared kit, teacher-led pages, subject-teacher voices, the grade 1–2 low-reading rule (pictures carry meaning, narration carries instructions, and covering the non-target text must still leave the task playable), the picture quiz, the weekly question pack, and the release gates run by `publish_courseware.py check`. Read it before authoring, reviewing or changing any lesson.

It replaces `docs/learning/low-reading-interaction-rule.md`, `backend/content/textbook_interaction_policy.v1.json`, `backend/content/textbook_courseware_quality.v1.json` and `backend/content/low_reading_policy.v1.json`. Those files stay only while published legacy lessons still need validating; do not apply them to new work, and never rewrite the frozen requests, receipts or review records of lessons that are already published.

Interactive pages are real-time mini-games (standard rule 8). Build them on the shared engine `courseware/kit/game.py` (page scripts call `K.game`; usage is in that file and `courseware/kit/tests/test_game.py`). Give every game an autopilot, because the G6 robot (`courseware/tools/autoplay.mjs`) finishes every level twice with it. Let the teacher demonstrate with `setState {demo:true}` and hand over with `{demo:false, level:1}`, and put anchor elements over canvas regions so the teacher's highlights have real targets. Working examples on this machine: `courseware/lessons/pep-math-g1-upper-recognize10-games` (published) and `courseware/lessons/pep-math-g1-upper-add-subtract10-games`.

Courseware engineering rules, for every code change that serves courseware:

- Course-specific content (lesson names, node ids, textbook editions) lives in course data, never in shared code.
- Models, prompts and providers come from the registries; do not hard-code them.
- New code needs tests. Never edit an existing test just to make it pass.
- Do not create Markdown reports or one-off scripts (see Repository Hygiene). Reusable operator tools belong in `courseware/tools/`.
- Delete code only from a reference-graph list that proves no live reader remains, and keep each batch separately revertible.
- Do not touch secrets or `.env`, MinIO, the real database, `output/`, `openmaic-runtime/.runtime/` or other courses' data unless the task says so. Delegated workers do not commit, push or use the network.
- Before changing backend, device or AI code, state the files to change and whether any external interface changes.

## Flutter Work

Flutter code lives in `mobile/`. Follow `mobile/AGENTS.md` for all Flutter changes.

## Verification

For mobile work, run from `mobile/`:

```sh
flutter analyze
flutter test
```

If either command cannot run, report the reason and the remaining risk.

## Repository Hygiene

- Report ordinary changes and verification in chat. Do not create a new Markdown report, dated plan, acceptance note, or screenshot gallery unless the user asks or a necessary workflow explicitly requires it. Update an existing relevant document when lasting guidance changes.
- Show routine lint, typecheck, test and build results in the terminal. Do not save a separate success log, JSON report, screenshot gallery, or duplicate result for every command. Prefer existing tools or code passed through stdin over creating a new one-time script.
- When temporary files are necessary, use one private directory per task through `python3 tools/task_tmp.py --name <task> -- <command...>`. The command receives `MIRA_TASK_TMPDIR` and `TMPDIR`; explicitly direct screenshots and other independent tools to that same directory. Do not scatter dated files directly into `/tmp` or `/private/tmp`.
- Successful foreground checks clean their temporary workspace automatically. A failed check retains nonempty diagnostics and prints their location; `--keep` retains an explicitly needed workspace. Remove retained task output after the issue is resolved. Commit only reusable operator tools and meaningful regression tests, never a script for each fixed job, course, or recovery attempt.
- Do not use automatic task cleanup for background services, database clusters, paid-call receipts, original private attachments, or recovery backups. These belong in their existing managed locations. Before removing any task directory, account for its running processes and live consumers; never sweep the shared system temporary directory by age or filename alone.
- Keep test fixtures, golden baselines, prompt Markdown, migrations, private ownership manifests, paid-call receipts, published media, and active runtime dependencies when they have live consumers. File extensions and directory names alone do not establish redundancy.
- Audit references, runtime ownership, and existing uncommitted work before cleanup. Use a verified recovery copy for unique historical data. Do not delete whole test, output, data, or database-table categories merely because they are large or currently empty.
