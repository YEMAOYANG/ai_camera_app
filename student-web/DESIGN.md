# Student textbook space

This is the child-facing Student Web, separate from the parent app described in the root PRODUCT.md. Primary scene: a child using a tablet or computer at home in daylight, opening their schoolbag and choosing a school subject.

## Direction

A real-time three-dimensional schoolbag is the homepage's central interactive object. Four physical books represent Chinese, mathematics, English and science. The user selected the second picture-book concept on 2026-09-24: warm ivory paper, charcoal text, yellow playback accents, soft illustration edges and spacious, continuous reading surfaces. The yellow bag and coral/blue/green/ochre book covers connect these surfaces. No cosmic background, floating particles, dashboard statistics or course-generation controls. Original editable geometry is authored in `scripts/build-schoolbag-model.mjs` and exported to `public/models/schoolbag/schoolbag-v5.glb`. Book positions and cloth/cover colors share `src/components/schoolbag/book-layout.json`; overlapping silhouettes must occupy separate depth lanes, with every subject title visible.

The selected source image is `/Users/sqcopenclaw/.codex/generated_images/01a0cd8e-df23-7cf3-b520-8068c9a6b875/exec-284b3e6b-ffc5-4f93-b94c-68567b1cf10c.png` (1487 × 1058). The first welcome-school spread follows its asymmetric illustration opening, small chapter indicators and one audio control. On phones the title, portrait crop, prompt and controls stack in reading order.

References reviewed on 2026-09-24:

- [Miro analysis](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/miro/DESIGN.md): white canvas and purposeful colour differentiation.
- [Airbnb analysis](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/airbnb/DESIGN.md): images carry hierarchy; restrained typography and clear navigation.
- [Khan Academy Kids Library](https://khankids.zendesk.com/hc/en-us/articles/4403657703821-Find-books-and-lessons-in-the-Khan-Kids-Library): recognizable visual destinations and subject exploration.
- [MotionSites](https://motionsites.ai/), [Bento Grids](https://bentogrids.com/) and [21st.dev](https://21st.dev/): reviewed for intentional motion, spatial hierarchy and restrained controls. The chosen image, rather than a copied showcase layout, controls this implementation.

These are principles, not copied branding, characters or textbook covers. The book-cover designs in the interface are original subject navigation, not reproductions of official book artwork.

## Interaction and authority

- Grade 1–2 experiences assume the child cannot independently read. Use meaningful scene illustrations, distinguishable picture answers, consistent character portraits and prerecorded teacher narration. Text is supplementary; native OpenMAIC activities follow the same rule as generated courseware. Apply `../docs/learning/low-reading-interaction-rule.md` and verify the task with non-target text covered.

- `/learning` is the homepage. Children choose subjects; parents select school system, edition and volume in the parent App's existing School Textbooks screen.
- Unlock and pairing show a closed bag. Only successful authentication triggers lid opening and books flying into the bag, followed by a continuous landing on the homepage. The scene is shared across these routes.
- A confirmed book lifts out, rotates toward the child and opens along its spine before entering its exact edition and immutable directory revision. Returning via the homepage or directory back link folds and returns that book. Modified clicks retain normal link behaviour. OS reduced motion or the persisted homepage motion toggle navigates immediately.
- Every transition has a visible skip control and a bounded routing fallback. Renderer failures never block authentication or course navigation; semantic DOM subject links remain independently available.
- No idle animations. Navigation must remain usable after browser Back; cancel delayed navigation when unmounted.
- Four subject slots remain visible. Missing subject catalogues say unavailable; an available but unconfirmed subject asks a parent to confirm. Neither case links to fabricated lessons.
- Extract vertically before moving a book across the other depth lanes. Close the cover and restore its lane before lowering it back into the bag. Follow the lift with the camera so taller middle books do not clip at the top. Check both geometry clearance and real rendered frames when changing the model.
- Directory, picture guide, pairing and unlock share the same light reading environment. Keep a clear homepage/back route and pause/lock access.
- Keep one playback control per spread. Transcripts are optional via the header's subtitle toggle. Picture choices, try-it feedback and the final return to the book remain interactive.
- Fixed textbooks govern course authoring and reuse only. Preserve OpenMAIC's working classroom features: subject teacher, companion classmates, multi-agent discussion, text questions, synthesized speech, microphone input, whiteboard, and discussion-to-playback transitions. A visual redesign must not hide or disable these features. Adapt the toolbar and participant area to the width left between the resizable sidebars.
- Parent settings and refresh live in a disclosure; unit selection remains visible in the directory. Do not put edition or school-system choices in front of a child.

## System

Theme tokens live in `src/styles/tokens.css`, scoped to `.schoolbag-shell` and `.mira-ui-surface` so historical classroom renderers retain their own contracts. `src/styles/storybook.css` supplies the chosen visual language after the base styles; all textbook CSS is imported in root layout to avoid route-dependent cascade changes. `src/styles/schoolbag-motion.css` covers the persistent 3D scene, subject links and transitions. Radix remains the headless behavior layer for accessible selects, disclosures and switches; Mira owns their appearance.

Short editorial headings use a locally subsetted Ma Shan Zheng font (SIL Open Font License, included in `public/fonts/OFL.txt`), with system Kaiti fallback. Controls, body copy and textbook lesson names use the system sans-serif stack. Targets are at least 48 px; visible focus, error/retry, loading, unavailable and reduced-motion states are required. Limit render resolution, release GPU resources and stop drawing when the scene is idle.

The original welcome illustration and reusable paper assets are in `public/images/storybook/`. The landscape substitution is tied to the exact published illustration hash and panel in `textbook-picture.tsx`; other panels retain their authored art. The paper mask must remain fully opaque inside, with transparency only at its boundary. Desktop's asymmetric mask leaves room for the title; phones use the shallow edge mask to preserve the child's face and bag.

Use the pre-generated image and voice assets. Do not create content on student clicks. Preserve formal publication, media, identity and prerequisite gates.
