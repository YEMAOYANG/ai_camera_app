# Original picture-book covers — 2026-09-24

Tool: OpenAI `image_gen`, text-to-image, one call per distinct asset, no textbook cover reference. The resulting raster art was resized/encoded as WebP; subject titles, rules and fabric spines are rendered in code. No Chinese lettering was generated into the image.

Shared brief: portrait 4:5 premium children's picture-book illustration; warm ivory watercolor paper, fine pencil and gentle gouache; quiet upper quarter for a later title; original, tactile and restrained; no text, numbers, logo, border or physical book mockup.

- Chinese: a coral bird on an open book growing a peach/sage tree, tiny listening child, warm clouds and winding path. Source `exec-e7d1b4e9-3d81-4813-a593-e1fd888c8068.png`; copied to `chinese-source.png`.
- Mathematics: sky-blue wooden arches and counting blocks, apricot spheres, a child moving a ball and a golden sun. Source `exec-365b969d-714c-4fbc-861b-517c7e073f7c.png`; copied to `math-source.png`.
- English: sage balloon over a garden village, fox carrying an unmarked envelope, little red mailbox, flowers and birds. Source `exec-69d449b6-34a6-4ba2-b889-54e4942d4f20.png`; copied to `english-source.png`.

Source directory: `/Users/sqcopenclaw/.codex/generated_images/01a0cd8e-df23-7cf3-b520-8068c9a6b875/`.

The lesson's separate original image is `exec-662746d2-86b6-4327-9b72-78b46a30af3b.png`: a wide 2:1 watercolor school garden, visible sky and ground, coral-clothed girl at left, teal-clothed speaking boy at center, mustard-clothed boy at right; no text or textbook content. The encoded file and digest are archived under `backend/content/textbooks/lesson-media-v1/`.

Actual UI screenshots are in `qa/`, including desktop, mobile and scrolled fixed navigation. These are browser captures, not generated mockups.

## Science addition — 2026-09-28

Original science cover created with OpenAI `image_gen`: warm ivory watercolor paper, a fox naturalist examining a fern with a magnifying glass, a butterfly and small observatory; restrained teal and ochre, quiet upper quarter, no lettering, logos or reference textbook cover. Subject title and spine are rendered in code, consistent with the other three subjects.

Source: `/Users/sqcopenclaw/.codex/generated_images/01a0e5f4-fe13-7291-8467-3aa89fe5dd98/exec-897bfa0a-f50c-41bb-9e04-6ad04ca3856a.png`. Runtime asset: `student-web/public/images/schoolbag/covers-v3/science.webp`, resized with Sharp to width 768 and WebP quality 86. This artwork is an original subject illustration, not the cover of any particular publisher's textbook.

Procedural model v4 adds `Book_science` and `CoverHinge_science`. Four resting poses are shared by rendering and motion; the model build uses matching positions. The generated GLB is 2,924,884 bytes, with 84 meshes and 85,018 vertices.

## Four-book overlap correction — 2026-09-28

Model v5 separates the middle books into different depth lanes and lowers the front pair so all four subject titles remain visible. `student-web/src/components/schoolbag/book-layout.json` now supplies both the model builder and the live renderer, including the blue mathematics (`#2863b4`) and green English (`#418448`) cloth colors. The generated GLB retains 84 meshes and 85,018 vertices. Original raster illustrations are unchanged; title paper, lettering, spine and cover board colors are drawn in code.

Extraction clears the neighboring books vertically before moving forward or opening the cover. Return follows the same path in reverse, and the camera follows the lift to keep the whole selected book visible. Geometry regression checks use the actual GLB, including the hover offset and sampled opening/return paths. Visual checks cover the real renderer and the student app navigation with synthetic browser-only identity.
