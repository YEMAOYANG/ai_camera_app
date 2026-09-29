# Textbook schoolbag delivery

## Scope

Student Web homepage, textbook directory, picture introduction, pairing and unlock presentation. Parent mobile already has the School Textbooks screen with family-management authorization and compare-and-swap selection writes, so no Flutter edit or schema migration was required.

`/`, `/today`, former path/practice entries, successful pairing and successful unlock now enter `/learning`. `/learning/textbooks` without a complete edition/revision redirects to the bag. Valid directory and guide links preserve immutable identity.

## API change

`GET /api/v2/student/learning/textbooks` retains `mira.learning.textbooks.v1`, returns only the student's currently confirmed books, and adds `subjects`: an ordered Chinese/math/English array whose status is `confirmed`, `selection_required` or `unavailable`. Availability derives from actual catalog entries in the child's grade and current semester. Parent catalog responses continue to expose the available versions for confirmation.

`GET /api/v2/student/learning/textbooks/{editionId}/contents?alignmentRevisionId=...` additionally requires a matching parent selection for the current child, grade revision, school year and semester. Otherwise it returns HTTP 409 `textbook_selection_required`. This also applies to stale/deep guide links. The browser has no selection write endpoint or fallback edition picker.

No DDL, catalog import, course publication or model call occurs while opening the bag or a book. The existing shared textbook/course store and individual learning records remain in place.

## Local demo data

The existing synthetic child named 一年级教材体验 was initially unconfirmed. A single local `ai_camera_app_dev` selection was added for `pep-chinese-g1-upper-2022-standard / 20260924-directory-3`, with explicit actor `local-fixture:schoolbag-20260924`. The operation checked loopback/database identity, exact child ID/nickname/grade revision, manifest hash and empty selection before using the repository's transactional selection/event method. It neither impersonates a parent audit actor nor automatically selects books for real children.

Chinese supplies nine sections, 45 directory entries and ten original introductory guides. Formal textbook course publication is still separate. Mathematics and English have visible subject slots but no invented catalog entries or lessons.

## Assets

Original transparent backpack generated with the built-in ImageGen tool, copied to `student-web/public/images/schoolbag/backpack-v1.png`. Two copies of the same asset form the bag rear and front; CSS clipping creates the opening, and HTML/CSS book covers remain interactive. Next Image supplies optimized derivatives. Existing picture-guide illustration atlases and prerecorded TTS remain unchanged.

Generation prompt:

```text
Use case: stylized-concept. Asset type: transparent PNG foreground layer for a child's interactive schoolbag web app. Primary request: one beautifully crafted open school backpack, straight-on front view, a little camera elevation to see inside its wide open top. Original premium soft 3D illustration, warm tactile woven nylon canvas, precise stitched seams, softly rounded sturdy structure, delightful but sophisticated, like a handcrafted miniature product. Main bag soft sunshine mustard yellow, dark burnt ochre interior, understated blue-gray zipper trim, cream tiny blank fabric label on the front pocket, one tiny coral red zip pull. Backpack is empty, NO BOOKS, no stationery, NO TEXT or logo, no face. The open mouth is a broad shallow horizontal ellipse near the top edge so interactive book objects can later appear behind it. Avoid tall handles or shoulder straps projecting above the opening: shoulder straps hidden behind bag. Wide roughly square body, smaller rounded rectangular front zip pocket. Center the entire single backpack in square image, backpack occupies 88% of width and 88% of height. Actual transparent background and subtle contact shadow only, no room, no floor plane, no scenery. High quality physically plausible materials, soft daylight from upper left, very clean silhouette, no glossy plastic, no extraneous objects.
```

## Validation

- Backend textbook/catalog/access, picture-guide and preview suites: 35 tests passed.
- Student Web full suite: 50 files, 238 tests passed; lint, typecheck and production build passed.
- Focused extraction tests cover exact selected version, no writes, unavailable subjects, parent refresh, reduced motion, double clicks and unmount cancellation.
- Local browser checks cover the real bag-to-directory-to-picture-guide route and prerecorded audio playback. Responsive and final return checks are recorded with the acceptance artifact after the final build.
