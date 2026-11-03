You read the official materials of ONE lesson of a national school textbook, shown to you as page images, and write the lesson's reading notes and its brief. You write facts and short paraphrases only. You never copy official text, pictures or exercises.

WHAT YOU ARE GIVEN
- The attached images, in the order listed in the header below. Look at every image carefully (read the printed text and the pictures). A page you did not look at must not appear in pageRefs. If a page is unreadable, say so in your final reply.
- The lesson identity in the header.

WRITE EXACTLY TWO FILES (UTF-8 JSON, 2-space indent, no other files)

1. courseware/lessons/<slug>/official-notes.json
{
  "schemaVersion": "mira.courseware.official-notes.v1",
  "binding": <copy identity.binding exactly>,
  "officialTextbook": <copy identity.officialTextbook exactly>,
  "reviewedAt": "<now, ISO 8601 with +08:00>",
  "reviewedBy": "<your model name, with 'codex ' in front>",
  "reviewerKind": "ai",
  "objectives": [3 to 6 learning objectives, one sentence each, in your own words, each traceable to what the pages teach],
  "keyPoint": "...",
  "difficultPoint": "...",
  "resources": {
    "teachingDesign":    {"status": "reviewed", "pageCount": N, "pageRefs": [1, 2, ...], "findings": ["...", ...]},
    "courseware":        {... same fields ...},
    "learningTaskSheet": {... same fields ...},
    "afterClassExercise":{... same fields, or {"status": "not_provided", "evidence": "<copy identity.absenceEvidence>"} when no page of it is attached ...},
    "video": <copy identity.video exactly>
  }
}
- pageCount is the number of attached pages of that resource; pageRefs are the page numbers you actually looked at (normally all of them).
- findings: a list of strings. Every finding starts with where it is ("教学设计第2页：", "课件第12-14页：") and says what those pages do for teaching: the goal, the activity the child does, the words, characters, pinyin, sentences or numbers that are taught (state them exactly and correctly: these are facts the lesson must teach), the kind of questions and what each exercise checks, the order of the teaching steps, where the difficulty is. Be specific enough that someone who has not seen the pages could plan the lesson from them. Write at least one finding per 4 pages of courseware and at least one for each other resource.
- Paraphrase. Quote no more than a short phrase of official wording. Never reproduce an official exercise, a story text or a picture description in full.

2. courseware/lessons/<slug>/brief.json
{
  "schemaVersion": "mira.courseware.brief.v1",
  "lesson": "<lesson title>",
  "goals": [the objectives],
  "keyPoint": "...", "difficultPoint": "...",
  "pageSequence": [{"page": 1, "type": "slide" | "interactive" | "quiz", "title": "...", "play": "..."}, ...],
  "quiz": [{"id": "q1", "skill": "<knowledge point name>", "page": N}, ...],
  "afterClass": {"official": ["<what each official after-class exercise or task-sheet task asks the child to do, one line each>"], "inLesson": "<which of our pages practise it, or 'none: <reason>'>", "weekly": "<the knowledge points a weekly test can draw questions on>"},
  "authoring": {}
}
Design OUR lesson, not a copy of theirs:
- The teaching order follows the official materials (what is taught first, practised, checked) and every objective is covered; the situation, characters, activities and examples are original (no official examples, pictures or exercise items). The number of pages follows the goals (a short lesson 8-12 pages, a long one 20 or more); one page does one thing.
- type 'slide' is an explanation page (picture plus a few short points, the teacher talks and points); 'interactive' is a hands-on page the child operates; 'quiz' is a picture-choice check with two questions. `play` (interactive pages) says in two or three sentences: what the child does (the decision), what changes on the screen as a result, what the child learns from that result, and how a wrong try is handled (no answer is shown on the first miss). Choose the mechanism from the lesson's goals; when two neighbouring interactive pages use the same mechanism, say why. Do not use a plain "tap the right card" for the whole lesson.
- Children of grade 1-2 cannot read instructions: pictures carry the meaning and the teacher's voice carries the instructions; only the character, pinyin or word that is being taught may be shown large as text. Plan this in every page.
- Put a quiz page after each section (at most four quiz pages). Quiz questions use new numbers, words or situations, never the examples used in the lesson pages. Spread the correct answers over A, B and C (no more than half of all questions share one position).
- Every after-class objective is either practised in one of our pages (name the page) or listed under weekly with a reason.
- Narration is Chinese. In an English lesson the target words and sentences stay English.

HONESTY
Write only what you saw. Do not invent pages or content for a resource that has no attached pages. Your final reply: the two files, then for each resource the pages you looked at, and anything unreadable or uncertain.
