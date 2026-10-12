import { z } from "zod";

const text = z.string().trim().min(1).max(2000);
const sourceUrl = z.url().max(2000).refine(value => {
  const url = new URL(value);
  return url.protocol === "https:" && !url.username && !url.password && (!url.port || url.port === "443");
}, "A public HTTPS source is required");

const textbookFields = {
  requestedTitle: text,
  matchedTitle: text.nullable(),
  publisher: text.nullable(),
  editionStatus: z.enum(["catalog_verified", "needs_confirmation"]),
  editionNote: text,
  candidates: z.array(z.object({ title: text, publisher: text, editionNote: text, url: sourceUrl }).strict()).max(10),
  evidence: z.array(z.object({ label: text, url: sourceUrl, detail: text }).strict()).max(20),
  requiredMaterials: z.array(text).max(20),
};

const textbookSchema = z.discriminatedUnion("id", [
  z.object({ ...textbookFields, id: z.literal("hk-sfa-chinese-p5-lower"), subject: z.literal("chinese"), gradeCode: z.literal("primary_5"), semester: z.literal("lower") }).strict(),
  z.object({ ...textbookFields, id: z.literal("hk-sfa-english-p6-upper"), subject: z.literal("english"), gradeCode: z.literal("primary_6"), semester: z.literal("upper") }).strict(),
]);

export const internationalTrialsSchema = z.object({
  ok: z.literal(true),
  schemaVersion: z.literal("mira.learning.international-trials.v1"),
  checkedAt: z.iso.date(),
  school: z.object({
    requestedName: text,
    name: text,
    website: sourceUrl,
    booklistStatus: z.literal("unconfirmed"),
  }).strict(),
  textbooks: z.array(textbookSchema).max(2).refine(books => new Set(books.map(book => book.id)).size === books.length, "Duplicate textbook"),
  generation: z.object({
    status: z.literal("blocked_source"),
    canGenerate: z.literal(false),
    publishedCourseKey: z.null(),
  }).strict(),
}).strict();

export type InternationalTrials = z.infer<typeof internationalTrialsSchema>;
export type InternationalTrialTextbook = InternationalTrials["textbooks"][number];
