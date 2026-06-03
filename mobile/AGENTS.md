# Flutter Agent Instructions

## Scope

This directory is the Flutter implementation of the Mira Guardian parent app. When the user asks for a new page, implement only the requested page or flow unless they explicitly expand the scope.

Do not rewrite the app structure, route map, theme, welcome page, or existing flows as a side effect of adding a page.

## Current Stack

- Flutter / Dart
- `flutter_riverpod` for dependency injection and state
- `go_router` for routing
- `dio` for API work
- `shared_preferences` for lightweight local flags
- Material 3 theme in `lib/src/core/theme`

## Project Structure

Use the existing layout:

```text
lib/src/
  app/              # App shell and routing
  core/             # environment, network, storage, theme
  features/         # feature-owned pages and state
  shared/widgets/   # reusable UI primitives
```

New feature screens should usually live at:

```text
lib/src/features/<feature>/presentation/<screen_name>.dart
```

Feature state and models should live under that feature's `application/` or `domain/` folder when needed.

## Design Tokens and Shared Widgets

Always inspect and reuse these before creating new styling:

- `lib/src/core/theme/app_tokens.dart`
- `lib/src/core/theme/app_theme.dart`
- `lib/src/shared/widgets/mira_button.dart`
- `lib/src/shared/widgets/info_card.dart`
- `lib/src/shared/widgets/status_chip.dart`

Use `AppColors`, `AppRadii`, `AppMotion`, and `AppTypography` instead of local magic values when possible.

Use `MiraPrimaryButton` and `MiraSecondaryButton` for primary and secondary actions unless the requested design clearly needs a new shared primitive. If a new button/input/sheet pattern is likely to repeat, add it under `lib/src/shared/widgets/` instead of duplicating it in a feature file.

## Routing

Routes are defined in:

- `lib/src/app/router/app_route.dart`
- `lib/src/app/router/app_router.dart`

When adding a page:

- Add a route only when the user asks for a navigable page.
- Keep shell tab routes inside the existing `ShellRoute`.
- Keep one-off onboarding/auth/setup pages outside the tab shell unless the user says otherwise.
- Avoid dead ends. Detail/setup pages need an obvious way back except where the product flow intentionally disallows it.

## API and Feature Boundaries

Flutter pages must not assemble raw API URLs or depend on RTSP, go2rtc, specific camera models, device private protocols, SMS providers, AI provider keys, or prompt text. Pages should read and mutate data through feature repositories/use cases backed by the shared Dio API client.

Keep clear feature boundaries for login, setup, family, child, device, camera, tasks, points, rewards, AI summaries, and legal/privacy. Do not add one-off mock structures inside a screen if the data shape should become a backend contract; mock data should resemble the API response that will replace it.

App startup routing should combine:

- onboarding status
- auth session / refresh token
- backend setup status
- device binding status

Do not rely on one local boolean to represent the whole lifecycle.

Do not create a standalone `daily_flow`, `daily_plan`, "今日流程", or "今日计划" feature. Day-specific content belongs to `tasks`; home may render a today task summary, but it should still come from task data.

## Welcome and Login Rules

The welcome/onboarding screen is already a designed flow. Do not redesign it unless the user explicitly asks.

Welcome behavior:

- First app launch shows welcome/onboarding.
- Completing welcome stores `hasSeenOnboarding`.
- Later launches skip welcome.

The storage key lives in `lib/src/core/storage/onboarding_store.dart`.

Login behavior, unless the user changes it:

- Phone number plus SMS code login only.
- Unregistered phone numbers auto-create the family account after verification.
- No email/password login.
- No third-party login.
- If login follows welcome completion, login should not expose a back button to welcome.
- Implement mock logic until backend endpoints are requested.

## Screen Implementation Checklist

Before coding a new screen, identify:

- Business purpose
- Route or entry point
- Required fields and actions
- Loading, empty, error, disabled, pressed, and success states
- Dialogs, action sheets, toasts, and validation messages
- Whether the screen is inside the tab shell or outside it
- Which existing tokens/widgets can be reused

After coding:

- Check 390x844 layout first.
- Respect SafeArea, status bar, keyboard insets, and bottom safe area.
- Avoid text overflow, clipped buttons, and horizontal scrolling.
- Use `AppMotion.duration(context, ...)` or `MediaQuery.disableAnimations` aware logic for animations.
- Run `flutter analyze`.
- Run `flutter test` when tests are present or affected.

## Visual Quality Rules

- Do not use emoji as UI icons.
- Do not create generic white-card piles.
- Do not overuse gradients, glassmorphism, or large shadows.
- Do not invent a new visual system per page.
- Keep copy specific and parent-facing.
- Preserve the user's chosen design source of truth. If the user says "one-to-one", match it closely and do not improve creatively.

## Test Notes

Widget tests that construct `MiraGuardianApp` may need provider overrides for dependencies such as `appEnvironmentProvider` and `sharedPreferencesProvider`.

Prefer focused tests around navigation gates, validation logic, countdown behavior, and screen smoke rendering for new flows.
