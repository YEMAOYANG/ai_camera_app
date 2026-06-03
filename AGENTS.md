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

## Flutter Work

Flutter code lives in `mobile/`. Follow `mobile/AGENTS.md` for all Flutter changes.

## Verification

For mobile work, run from `mobile/`:

```sh
flutter analyze
flutter test
```

If either command cannot run, report the reason and the remaining risk.
