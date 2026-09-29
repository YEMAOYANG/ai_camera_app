import { StudentSessionGate } from "@/features/auth/student-session-gate";
import { redirect } from "next/navigation";
import type { Metadata } from "next";
import { textbookIdSchema } from "@/lib/contracts/textbooks";

export const metadata: Metadata = { title: "教材课程库" };

export default async function TextbooksPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const location = Object.fromEntries(["editionId", "revisionId", "unitId"].flatMap(key => {
    const parsed = textbookIdSchema.safeParse(query[key]);
    return parsed.success ? [[key, parsed.data]] : [];
  }));
  if (!location.editionId || !location.revisionId) redirect("/learning");
  return <StudentSessionGate learningView="textbooks" textbookLocation={location} />;
}
