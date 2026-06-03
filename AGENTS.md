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
- `design/mira_guardian_high_fidelity_ui.html`

When implementing app screens, treat the HTML prototypes as business and interaction references unless the user says a specific design is the visual source of truth.

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
