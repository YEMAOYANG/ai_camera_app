import { StudentSessionGate } from "@/features/auth/student-session-gate";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { textbookIdSchema, textbookSubjectSchema } from "@/lib/contracts/textbooks";

export const metadata: Metadata = { title: "教材课程库" };

export default async function TextbooksPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const location = Object.fromEntries(["editionId", "revisionId", "unitId"].flatMap(key => {
    const parsed = textbookIdSchema.safeParse(query[key]);
    return parsed.success ? [[key, parsed.data]] : [];
  }));
  const hasDirectoryQuery = ["editionId", "revisionId", "unitId"].some(key => query[key] !== undefined);
  if (hasDirectoryQuery && (!location.editionId || !location.revisionId)) redirect("/learning");
  const subject = textbookSubjectSchema.safeParse(query.subject);
  if (query.subject !== undefined && !subject.success) redirect("/learning");
  return <StudentSessionGate learningView="textbooks" textbookLocation={{ ...location, ...(subject.success ? { subject: subject.data } : {}) }} />;
}
