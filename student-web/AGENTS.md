# Student Web Instructions

This directory is the child-facing Mira learning website.

- Use Next.js App Router, React, TypeScript strict mode, and Tailwind CSS 4.
- Keep Python backend APIs as the source of truth for identity, courses, answers, progress, and mastery.
- Never expose parent access tokens, AI provider keys, private answers, or family/device APIs to the browser.
- Server auth tokens belong in HttpOnly cookies. Do not store them in localStorage.
- Build Server Components by default. Limit Client Components to interactive learning and authentication islands.
- Use the Mira student tokens from `src/styles/tokens.css`; do not apply default shadcn/OpenMAIC themes wholesale.
- 1–2 grade flows need large type, at least 48px touch targets, one primary action, and reduced-motion support.
- Run `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build` before handoff.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
