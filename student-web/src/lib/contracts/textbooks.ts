import { z } from "zod";

import { learningSubjectSchema } from "@/lib/contracts/learning";
import { progressiveGradeSchema } from "@/lib/contracts/progressive-learning";

export const textbookIdSchema = z.string().regex(/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/);
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const sourceUrl = z.string().url().refine(value => {
  const url = new URL(value);
  return url.origin === "https://basic.smartedu.cn" && url.pathname === "/tchMaterial/detail" && !url.username && !url.password;
});
const bookFields = {
  editionId: textbookIdSchema, revisionId: textbookIdSchema,
  title: z.string().min(1), publisher: z.string().min(1), editionLabel: z.string().min(1),
  gradeCode: progressiveGradeSchema, subject: learningSubjectSchema,
  volume: z.enum(["upper", "lower", "full"]), schoolSystem: z.enum(["six_year", "five_four"]),
  coverage: z.object({ status: z.enum(["index_only", "partial", "complete"]), note: z.string() }),
  sourceUrl, unitCount: z.number().int().nonnegative(), lessonCount: z.number().int().nonnegative(),
};
export const textbookBookSchema = z.object(bookFields);
export const textbookCatalogSchema = z.object({
  ok: z.literal(true), schemaVersion: z.literal("mira.learning.textbooks.v1"),
  gradeCode: progressiveGradeSchema.nullable(), schoolYearStartYear: z.number().int(), semester: z.enum(["upper", "lower"]),
  books: z.array(z.object({ ...bookFields, selected: z.boolean(), selectionRevision: z.number().int().nonnegative(), currentNodeId: textbookIdSchema.nullable() })),
});
export const textbookContentsSchema = z.object({
  ok: z.literal(true), schemaVersion: z.literal("mira.learning.textbooks.v1"), book: textbookBookSchema,
  selected: z.boolean(), selectionRevision: z.number().int().nonnegative(), currentNodeId: textbookIdSchema.nullable(),
  units: z.array(z.object({
    unitId: textbookIdSchema, title: z.string(), sequence: z.number().int().positive(),
    lessons: z.array(z.object({
      nodeId: textbookIdSchema, title: z.string(), sequence: z.number().int().positive(),
      printedPage: z.number().int().positive().nullable(), pdfPage: z.number().int().positive().nullable(),
      objectives: z.array(z.string()), status: z.enum(["ready", "preparing", "reviewing", "locked"]), message: z.string().nullable().optional(),
      course: z.object({ courseId: z.string().min(1), courseVersion: z.string().min(1), contentKey: hash }).nullable(),
    }).refine(node => (node.status === "ready") === (node.course !== null))),
  })),
}).refine(data => data.selected || data.units.every(unit => unit.lessons.every(lesson => lesson.course === null)));

export type TextbookCatalog = z.infer<typeof textbookCatalogSchema>;
export type TextbookContents = z.infer<typeof textbookContentsSchema>;
