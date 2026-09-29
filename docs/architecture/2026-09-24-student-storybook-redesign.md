# Student picture-book redesign

The user selected concept 2 on 2026-09-24. Student Web now uses a warm paper reading surface across unlock, pairing, the schoolbag homepage, textbook contents and picture guides.

## Scope and decisions

- Retain Radix primitives for keyboard/focus behavior and replace Mira's previous card-heavy visual skin. No new UI dependency is needed.
- Keep the shared Three.js schoolbag, authentication-success trigger and pick-up/return timelines. No backend, database, course-publication or parent-selection contract changes.
- Preserve the real textbook catalogue and per-student progress. Preparation and unavailable states remain visible; a child click never generates a course.
- Remove duplicate home navigation and image-play buttons. Collapse refresh and parent preferences, keep a single audio control, and show narration only on demand.
- Load textbook base CSS before the picture-book theme at the root. Previously, client navigation could load the base stylesheet after the theme and restore old cards and oversized headings.

## Assets

- `student-web/public/images/storybook/welcome-school-hero.webp`: original 1774 × 887 landscape illustration, 154,524 bytes. Its prompt/provenance is recorded in `docs/design-assets/2026-09-24-welcome-school-hero.json`.
- `paper-texture.webp`: 512 × 512 repeatable warm paper texture.
- `paper-edge-mask.png`: 1792 × 896 RGBA shallow organic edge, used for small illustrations and phone crops.
- `story-spread-mask.png`: 1792 × 896 RGBA asymmetric title opening, used for the matching landscape spread on desktop.
- `student-web/public/fonts/mira-storybook.woff`: local subset of the official Google Fonts Ma Shan Zheng font. No network font request at runtime; OFL license included. Course text was subsetted locally.

Existing published image and synthesized voice assets continue to supply the other scenes. This is a visual and interaction refinement, not a new content-generation run.

## Verification

See root `design-qa.md` for the source-to-browser comparison, responsive checks and known limits. Lint, TypeScript, the existing test suite and the managed production build are required. The local managed runtime is updated with the curriculum worker disabled.
