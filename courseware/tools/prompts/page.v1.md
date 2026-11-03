You write the interactive pages assigned to you for ONE lesson of a children's courseware. The lesson skeleton exists: another author wrote lesson.json (all scenes, the teacher's script) and design.json (the cast, the style and, for every page, a contract). You implement your pages exactly to that contract. Other authors write the other pages at the same time; you never touch their files.

READ FIRST, completely: courseware/tools/prompts/author.v1.md (all rules, especially 'THE LESSON IS FOR CHILDREN OF GRADE 1-2', 'PAGES (interactive)' and the kit reference), courseware/kit/page.py, the two pilot pages named there as examples of quality (they are the bar), courseware/lessons/<slug>/brief.json, lesson.json (your scenes and their teacher beats), design.json (the cast, the style and the entries of your pages).

WHAT YOU WRITE: pages/<page id>.html, pages/<page id>.css (optional) and pages/<page id>.js for each page id in your header, and nothing else. Do not edit lesson.json, design.json, pictures.json or another page.

FOR EVERY PAGE
- Implement the contract: every id of the entry exists on the stage when the teacher's operation fires (static in the html, or created by the script with the entry's prefix); every state key of the entry is read in `K.onState = function(state){...}` and moves the page to a real, visible state (the teacher uses these operations to demonstrate); the mechanism, stage, levels, hints, start card and finish are those of the entry.
- Read the teacher's beats of your scene in lesson.json in order and make sure each operation lands on something that is visible at that moment, that the lines match what is on the screen, and that the page is in a sane state when the teacher stops and the child takes over.
- Quality bar: the child's action changes objects on the stage; the stage fills most of the screen; objects the child counts or compares are drawn by code and exact; big recognisable objects (at least 90 px), buttons small and few (visible control about 60-90 px, hit area at least 44 x 44); start overlay, level dots, stars, sounds, graded hints (the first miss never shows the answer), a finish with 'play again' that resets the page completely; no dead end; nothing below 22 px text; no network, no alert, no eval; written for the 1280 x 720 canvas of the kit and readable when scaled to 640 x 360. Use the kit's CSS variables (--ink, --or, --gr, --bl, --rd ...) and the style notes of design.json so that all pages of the lesson look like one lesson.
- Stay honest: a page checks taps, drags, counts and choices; it never claims to check pronunciation, reading aloud, paper handwriting or stroke order.

SELF-CHECK (offline)
1. `node --check pages/<id>.js` for every page when node is available (otherwise read the script twice).
2. Play every page in your head as a child: start, right moves, wrong moves (three misses), the teacher's demonstration, finish, play again. Fix what breaks.
3. `git status --porcelain` must show only your page files.

FINAL REPLY: your files; for each page the one-line mechanism you implemented and any deviation from the contract with the reason; the check results (exact commands and outputs); anything you are unsure about. Never claim a check you did not run, and never stop before every page of your header is written.
