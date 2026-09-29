import { z } from "zod";

import { progressiveGradeSchema } from "@/lib/contracts/progressive-learning";

// Fixed textbooks can add subjects independently of the legacy generated curriculum.
export const textbookSubjectSchema = z.enum(["chinese", "math", "english", "science"]);
export type TextbookSubject = z.infer<typeof textbookSubjectSchema>;
export const textbookIdSchema = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/);
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const sourceUrl = z.string().url().refine(value => {
  const url = new URL(value);
  const officialCatalogs = [
    "https://bph.com.cn/news/detail/2726.html",
    "https://edu.sh.gov.cn/cmsres/7a/7aed3909441a4c849d5d78b8d914f4fb/00e155989221056fb74efd6f967939f0.pdf",
  ];
  return !url.username && !url.password && (officialCatalogs.includes(value)
    || (url.origin === "https://basic.smartedu.cn" && (url.pathname === "/tchMaterial/detail"
      || (url.pathname === "/syncClassroom" && /^[a-z0-9-]+(?:\/[a-z0-9-]+){4}$/.test(url.searchParams.get("defaultTag") ?? "")))));
});
const bookFields = {
  editionId: textbookIdSchema, revisionId: textbookIdSchema,
  title: z.string().min(1), publisher: z.string().min(1), editionLabel: z.string().min(1),
  gradeCode: progressiveGradeSchema, subject: textbookSubjectSchema,
  volume: z.enum(["upper", "lower", "full"]), schoolSystem: z.enum(["six_year", "five_four"]),
  coverage: z.object({ status: z.enum(["index_only", "partial", "complete"]), note: z.string() }),
  sourceUrl, unitCount: z.number().int().nonnegative(), lessonCount: z.number().int().nonnegative(),
};
export const textbookBookSchema = z.object(bookFields);
const discoveryItem = z.object({ label: z.string().min(1).max(40), response: z.string().min(1).max(180) });
const stepFields = { title: z.string().min(1).max(80), body: z.string().min(1).max(220) };
const pictureSegmentSchema = z.object({
  caption: z.string().min(1).max(16), narration: z.string().min(1).max(200),
  art: z.object({ src: z.string().regex(/^\/textbooks\/picture-guide-v1\/[a-z]+-[0-9a-f]{16}\.png$/),
    panel: z.number().int().min(0).max(3), alt: z.string().min(1).max(80), sha256: hash })
    .refine(art => art.src.endsWith(`${art.sha256.slice(0, 16)}.png`)),
  audio: z.object({ src: z.string().regex(/^\/textbooks\/picture-guide-v1\/[0-9a-f]{64}\.mp3$/),
    sha256: hash, durationSeconds: z.number().gt(1).lt(120) }).refine(audio => audio.src.endsWith(`${audio.sha256}.mp3`)),
});
const picturePresentationSchema = z.object({
  schemaVersion: z.literal("mira.textbook.picture-guide.v1"), gradeCode: z.literal("primary_1"),
  sourceContentSha256: hash, presentationSha256: hash, title: z.string().min(1).max(20),
  scenes: z.array(pictureSegmentSchema).length(4), choices: z.array(pictureSegmentSchema).length(3),
});
export const textbookIntroductionSchema = z.object({
  introductionId: textbookIdSchema, title: z.string().min(1).max(120), hook: z.string().min(1).max(120),
  estimatedMinutes: z.number().int().min(2).max(10), authorship: z.literal("original"), contentSha256: hash,
  steps: z.tuple([
    z.object({ ...stepFields, kind: z.literal("discover"), cards: z.array(discoveryItem).min(2).max(4) }),
    z.object({ ...stepFields, kind: z.literal("choose"), options: z.array(discoveryItem).min(2).max(4) }),
    z.object({ ...stepFields, kind: z.literal("do"), actions: z.array(z.string().min(1).max(500)).min(1).max(4) }),
    z.object({ ...stepFields, kind: z.literal("bridge"), question: z.string().min(1).max(140) }),
  ]),
  nextNodeIds: z.array(textbookIdSchema).min(1).max(4),
  presentation: picturePresentationSchema.optional(),
}).refine(guide => !guide.presentation || guide.presentation.sourceContentSha256 === guide.contentSha256);
const journeySchema = z.object({
  contentKey: hash, title: z.string(), status: z.string(), parentNeeded: z.boolean(),
  nextStep: z.string(), independentBefore: z.number().int(), verifiedCount: z.number().int(),
  remainingSkills: z.array(z.string()), reviewDueAt: z.number().nullable(), reviewDue: z.boolean(),
  reviewLevel: z.number().int(), diagnoses: z.array(z.string()), skippedCount: z.number().int(),
  updatedAt: z.number().nullable(),
});
export const textbookCatalogSchema = z.object({
  ok: z.literal(true), schemaVersion: z.literal("mira.learning.textbooks.v1"),
  gradeCode: progressiveGradeSchema.nullable(), schoolYearStartYear: z.number().int(), semester: z.enum(["upper", "lower"]),
  termSource: z.enum(["calendar", "parent"]).optional(),
  suggestedSemester: z.enum(["upper", "lower"]).optional(),
  contextRevision: z.number().int().nonnegative().optional(),
  gradeRevision: z.number().int().nonnegative().optional(),
  subjects: z.array(z.object({ subject: textbookSubjectSchema, status: z.enum(["confirmed", "selection_required", "unavailable"]) })).optional(),
  learningJourneys: z.array(journeySchema).optional(),
  books: z.array(z.object({ ...bookFields, selected: z.boolean(), selectionRevision: z.number().int().nonnegative(), currentNodeId: textbookIdSchema.nullable(), learningStatus: z.object({status: z.enum(["ready", "unpublished", "locked"]), availableLessonCount: z.number().int().nonnegative(), completedLessonCount: z.number().int().nonnegative()}).optional() })),
});
export const textbookContentsSchema = z.object({
  ok: z.literal(true), schemaVersion: z.literal("mira.learning.textbooks.v1"), book: textbookBookSchema,
  selected: z.boolean(), selectionRevision: z.number().int().nonnegative(), currentNodeId: textbookIdSchema.nullable(),
  introduction: textbookIntroductionSchema.nullable().optional(),
  units: z.array(z.object({
    unitId: textbookIdSchema, title: z.string(), sequence: z.number().int().positive(),
    kind: z.enum(["unit", "orientation"]).default("unit"),
    introduction: textbookIntroductionSchema.nullable().optional(),
    lessons: z.array(z.object({
      nodeId: textbookIdSchema, title: z.string(), sequence: z.number().int().positive(),
      sectionTitle: z.string().min(1).max(500).optional(),
      printedPage: z.number().int().positive().nullable(), pdfPage: z.number().int().positive().nullable(),
      objectives: z.array(z.string()), status: z.enum(["ready", "preparing", "reviewing", "locked"]), message: z.string().nullable().optional(),
      course: z.object({ courseId: z.string().min(1), courseVersion: z.string().min(1), contentKey: hash,
        delivery: z.literal("fixed_textbook").optional() }).nullable(),
    }).refine(node => (node.status === "ready") === (node.course !== null))),
  })),
}).refine(data => data.selected || data.units.every(unit => unit.lessons.every(lesson => lesson.course === null)))
  .refine(data => {
    const guides = [data.introduction, ...data.units.map(unit => unit.introduction)].filter(Boolean);
    const nodes = new Set(data.units.flatMap(unit => unit.lessons.map(lesson => lesson.nodeId)));
    return new Set(guides.map(guide => guide!.introductionId)).size === guides.length
      && guides.every(guide => !guide!.presentation || guide!.presentation.gradeCode === data.book.gradeCode)
      && (!data.introduction || data.introduction.nextNodeIds.every(id => nodes.has(id)))
      && data.units.every(unit => !unit.introduction || unit.introduction.nextNodeIds.every(id => unit.lessons.some(lesson => lesson.nodeId === id)));
  });

export type TextbookCatalog = z.infer<typeof textbookCatalogSchema>;
export type TextbookContents = z.infer<typeof textbookContentsSchema>;
export type TextbookIntroduction = z.infer<typeof textbookIntroductionSchema>;
export type PictureGuideSegment = z.infer<typeof pictureSegmentSchema>;

export const textbookLaunchSchema = z.object({
  ok: z.literal(true), contentKey: hash, title: z.string().min(1),
  editionId: textbookIdSchema, revisionId: textbookIdSchema,
  unitId: textbookIdSchema, learningSessionId: z.string().min(1), launchUrl: z.string().url(),
});
