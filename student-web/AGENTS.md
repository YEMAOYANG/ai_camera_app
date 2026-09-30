# Student Web Instructions

This directory is the child-facing Mira learning website.

- Use Next.js App Router, React, TypeScript strict mode, and Tailwind CSS 4.
- Keep Python backend APIs as the source of truth for identity, courses, answers, progress, and mastery.
- Never expose parent access tokens, AI provider keys, private answers, or family/device APIs to the browser.
- Server auth tokens belong in HttpOnly cookies. Do not store them in localStorage.
- Build Server Components by default. Limit Client Components to interactive learning and authentication islands.
- Use the Mira student tokens from `src/styles/tokens.css`; do not apply default shadcn/OpenMAIC themes wholesale.
- Schoolbag UI buttons must use `components/ui/button.tsx`. `src/styles/buttons.css` is the single source of button dimensions: `size="compact"` for toolbar, narration, refresh and return actions (36px visual height); default for main actions (48px); `size="icon"` for icon-only controls (48px). Icons are 18px. Compact controls retain a 48px touch area. Do not add page-specific button height, padding, font size or icon-size overrides; update the shared standard instead. Picture choices, playback overlays and learning activities retain their dedicated interaction design.
- 1–2 grade flows need large type, at least 48px touch targets, one primary action, and reduced-motion support.
- Grade 1–2 must work without independent reading: meaningful scene illustrations, distinct picture choices and prerecorded teacher narration are required for most learning tasks. Text supports pictures; it cannot be the only way to identify an answer or operate the page. Follow `../docs/learning/low-reading-interaction-rule.md` and the root AGENTS rule, including native classroom integrations.
- Navigation is quiet by default: entering, returning to, refreshing or focusing the homepage must not autoplay narration. Keep one explicit teacher-listen control per navigation surface. Completion narration belongs to a newly completed learning action, never to loading a saved result; historical lesson progress must not be described as today's tasks being complete.
- Run `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build` before handoff.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
