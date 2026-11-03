You are the designer of ONE lesson of a children's courseware. You write the lesson's skeleton so that several page authors can write the interactive pages in parallel afterwards, and so that the finished lesson hangs together as one lesson with one cast and one look.

READ FIRST, completely: the list and all rules of courseware/tools/prompts/author.v1.md (every rule there binds the lesson you design: grade 1-2 low-reading rule, teacher lines, teacher operations, quiz format, honesty about what a page can verify, Simplified Chinese, original content, always deliver the whole lesson). Then courseware/lessons/<slug>/official-notes.json and brief.json.

WHAT YOU WRITE (under courseware/lessons/<slug>/, new files only; no pages, no other file)
1. lesson.json: the COMPLETE lesson: roster (the single teacher given in the header), images, and ALL scenes in the brief's order (you may split, merge or add a page when the goals need it; say so in your final reply). Slides: template and data. Quiz scenes: all questions in the exact format of build.py. Interactive scenes: page id, widgetType, startImage, and the full teacher script (at least three {"say"} lines and at least three operations each, lines at most 25 characters) written against the page contract below.
2. pictures.json: the illustrations for slides, start pages and quiz questions/options (at most 8 plus 16 quiz pictures, see author.v1.md). Every quiz option whose meaning an emoji arrangement cannot show unmistakably gets its own picture ({"kind": "asset"} visual, see the Quiz rule of author.v1.md).
3. design.json, the contract between you and the page authors:
{
  "cast": [{"name": "...", "look": "how the recurring character looks and acts, in one sentence"}],   // one to three characters, used by the pictures, the slides and the pages
  "style": {"notes": "the common look of the pages: colours from the kit's CSS variables, shape language, how the stage objects are drawn"},
  "pages": [
    {
      "id": "p02",
      "title": "...",
      "mechanism": "one or two sentences: what the child decides and does, what changes on the stage, what the child learns from the result, what a wrong try does",
      "stage": "what is on the stage: the objects, how many, where, and how each is drawn: as inline SVG of at least 120 px (anything counted or compared) or as a lesson picture; never emoji as the main objects",
      "levels": ["level 1: ...", "level 2: ..."],
      "ids": ["basket", "item-1", "item-2"],            // every element id any teacher operation of this page targets; ids created by the script are written with a prefix: "item-1" stands for item-1, item-2 ...
      "stateKeys": {"phase": "'count' or 'order': the page switches to that phase", "count": "number: show this count and mark that many objects"},  // every key of the page's setState operations and what the page must do on receiving it
      "hints": ["first hint: what to look at", "second hint: a bigger clue", "third: a demonstration"],
      "start": {"emoji": "🍎", "title": "the start card's title", "sub": "one short phrase"},
      "finish": {"title": "...", "sub": "..."}
    }
  ]
}
Rules for the contract: (a) every page gets its own entry; (b) neighbouring pages must not share a mechanism unless the entry says what is new in the decision, the condition or the situation; the whole lesson must not be 'tap the right card'; (c) the teacher script in lesson.json uses only ids and state keys that are in the entry of that page, in the order that makes sense while the page runs (the teacher demonstrates one example first, then the child plays); (d) the pages stay completable by a child with taps or drags, with graded hints, a visible progress and a finish; (e) anything that needs verified data you do not have (stroke order, pronunciation) is replaced by an activity the page can really do; (f) the mechanism is the knowledge itself, not a reward gesture (see VISUAL QUALITY in author.v1.md): say in the entry what the child's hands do that a child who does not know the lesson could not do; (g) each page's teacher script has 5-8 lines and 4-6 operations, written for the whole page including its demonstration.

SELF-CHECK (offline)
1. Make placeholder pictures for your own test only: for each key of pictures.json an assets/<key>.png (a plain 1024 x 576 gray PNG via Pillow); delete the assets folder at the end.
2. Check that lesson.json, pictures.json and design.json are valid JSON, that every interactive scene's page id has an entry in design.json (and the reverse), and that every id and state key used by a teacher operation is listed in the entry of its page. Write this check inline with Python (no new files).
3. You cannot build the lesson yet (the page files do not exist), so also read lesson.json once as the child would hear it: lines, order, operations, quiz.
4. `git status --porcelain` must show only lesson.json, pictures.json and design.json of your lesson.

FINAL REPLY: the three files; the list of pages with one line of mechanism each; what you changed against the brief and why; the results of the self-checks (exact commands and outputs); anything you are unsure about. Never claim a check you did not run.
