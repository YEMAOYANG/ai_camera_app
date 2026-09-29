# Student picture-book visual QA — 2026-09-24

final result: passed

## Source and implementation

- Source visual truth: `/Users/sqcopenclaw/.codex/generated_images/01a0cd8e-df23-7cf3-b520-8068c9a6b875/exec-284b3e6b-ffc5-4f93-b94c-68567b1cf10c.png`, the user's selected concept 2.
- Implementation: `http://localhost:3000/learning/textbooks/pep-chinese-g1-upper-2022-standard/20260924-directory-3/intro/welcome-school`.
- Implementation screenshot: `docs/design-assets/storybook-qa/guide-desktop.jpg`.
- Source pixels: 1487 × 1058. Implementation pixels and CSS viewport: 1487 × 1058; browser DPR 1. No resizing or density normalization was needed for the primary comparison. The captured image is JPEG, as returned by the browser tool.
- State: authenticated local test learner, first welcome-school spread, playback idle, subtitles hidden, scroll position at top.
- Full-view evidence: source image and implementation capture were emitted together in each comparison input, including the final post-fix comparison. This is a paired full-view comparison, not a claimed side-by-side composite.
- Focused inspection: the paired full views were readable at native size. The title opening, illustration crop, header controls and player were inspected within them; no separate crop was needed. Tablet title/image geometry and phone touch targets were additionally measured from the rendered DOM.

## Comparison history

1. **P2 — Illustration started too low.** `guide-before.jpg` showed a separate title row above a straight image edge, unlike the selected concept's title opening. Added an original asymmetric alpha mask and brought the wide scene up beneath the title. `guide-mid.jpg` confirmed the curve but showed the image/player still too low. The final desktop capture uses the revised image height, title offset and stronger short-heading typography; all primary controls fit the 1058 px viewport.
2. **P2 — Old directory card styles returned on navigation.** `directory-before.jpg` showed a rounded filled introduction card and oversized catalogue rows. Route-loaded base CSS was overriding the root theme. Moved textbook base CSS into root layout before the picture-book stylesheet. `directory-desktop.jpg` confirms the continuous paper surface and smaller unit index after client navigation.
3. **P2 — Mobile book title broke inside the grade.** `directory-mobile-before.jpg` split “一年级” across lines. Rendered title words as nonbreaking spans and adjusted the phone heading size. `directory-mobile.jpg` shows separate “语文” and “一年级上册” lines. The mobile brand link was also expanded from 36 × 40 to a measured 48 × 48 px target.
4. **P2 — Tablet title overlapped the art.** `guide-tablet-before.jpg` shows the last title characters over the picture at 834 × 1194. At widths up to 1200 px the title now precedes a shallow-edge image. `guide-tablet.jpg` confirms the fix: title bottom is y=211 and image top is y=211, with no overlap. The source and final desktop capture were compared together again after this change.
5. **P2 — Pairing verification code contrast.** The initial light yellow code was difficult to read on paper. The final rendered code uses RGB(41,56,59), and the redundant security explanation/footer and QR surface fill were removed. The QR screen was inspected in-browser; its live challenge was not saved into repository screenshots.

No actionable P0/P1/P2 findings remain in the checked surfaces.

## Responsive and interaction evidence

| Surface | CSS viewport | Capture | Result |
| --- | --- | --- | --- |
| Guide, desktop | 1487 × 1058 | `guide-desktop.jpg`, 1487 × 1058 pixels | Single audio control; header and next action visible; document width/height equal viewport |
| Guide, phone | 390 × 844 | `guide-mobile.jpg`, 390 × 844 pixels | Face and bag retained; prompt and controls visible; scrollWidth 390; home target 48 × 48 |
| Guide, tablet | 834 × 1194 | `guide-tablet.jpg`, 834 × 1194 pixels | Separate title and art; scrollWidth 834; player visible |
| Contents, desktop | 1487 × 1058 | `directory-desktop.jpg`, 1472 × 1047 pixels | Clean index, illustrated introduction and real lesson states |
| Contents, phone | 390 × 844 | `directory-mobile.jpg`, 375 × 812 pixels | Intact grade title; accessible unit selector and lesson list |
| Homepage, restored user window | 652 × 836 | `home-current-window.jpg` | Three subjects fit; controls under bag; parent settings collapsed |
| Unlock, desktop | 1487 × 1058 | `unlock-desktop.jpg` | Large closed bag; restrained four-slot PIN form; no floating form card |

Directory captures were returned slightly smaller by the browser capture surface (approximately 0.99× desktop and 0.962× phone). They are auxiliary responsive evidence and were not used for pixel-identical source comparison. Original bytes are retained without resampling.

Browser interactions exercised:

- Actual synthesized narration played; the control changed to pause. Subtitles opened and closed, moving between all four scenes stopped/replaced audio, a picture choice changed both caption and narration, try-it and completion states worked, and the completion link returned to the correct directory.
- The mobile Radix unit selector changed the real unit and lesson list.
- Homepage parent settings opened; refresh and motion controls remained available. An unprepared subject showed its preparation state rather than a course link.
- Rest returned to unlock. The existing local test PIN unlocked successfully, triggered the schoolbag entrance and landed on the real homepage.
- Return-home displayed the closing-book transition and reached the schoolbag homepage. Existing reduced-motion/fallback behavior is covered by the suite.
- QR waiting state and verification text rendered. The alternate pairing-code disclosure opened with its submit button disabled until complete. No parent approval or new real device binding was performed.
- Final guide browser warning/error log was empty. Temporary reference/QR tab was closed and viewport overrides were reset. The homepage remains open as the deliverable.

## Validation

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm test`: 51 files, 249 tests passed (15:24 local run).
- Managed production build: Next.js 16.3.0 webpack build and TypeScript passed; existing Student Web restarted on port 3000 after the final CSS-only tablet correction.
- `git diff --check`: passed.

## Follow-up polish and limits

- P3: The original implementation illustration and locally licensed brush heading font are stylistic interpretations of the chosen concept, not identical raster characters or exact glyph outlines. Decorative painted underlines were omitted; functional playback progress remains.
- This pass verifies the student visual redesign and existing interactions. It does not constitute new course publication, a parent-device pairing acceptance test, cross-browser certification, or whole-repository backend/mobile acceptance.
- Existing published art and synthetic voice remain the content source for other scenes. No runtime course generation was added.

## Follow-up: book covers and fixed header

Three original picture-book covers now use textured cloth spines, page edges, headbands and bookmarks in the v3 GLB. Verified at 1487×1058 and 390×844; no horizontal overflow, WebGL ready, no browser errors. The directory header stays at y=0 after scrolling and the sidebar starts at y=120. Both extraction and returning to the bag continue working. Evidence: `docs/design-assets/book-covers-v3/qa/`. Student lint/typecheck, 249 tests and managed production build passed.


## 2026-09-28 家长端孩子资料与教材选择

本轮用户选择 Product Design 第 2 张资料表设计。生产 Flutter 实现和归一化对照检查、迭代记录、验证范围见 [`mobile/design-qa.md`](mobile/design-qa.md)。实际渲染证据：`output/parent-profile-redesign-20260928/design-comparison.png`。本次家长端 final result: passed；实体手机与读屏软件未做人工验收。本节不改变上文 Student Web 的验证结论。
