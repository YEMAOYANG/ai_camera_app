import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { StudentSessionGate } from "@/features/auth/student-session-gate";
import { textbookIdSchema } from "@/lib/contracts/textbooks";

export const metadata: Metadata = { title: "课前探索" };

export default async function IntroductionPage({ params }: { params: Promise<{ editionId: string; revisionId: string; introductionId: string }> }) {
  const location = await params;
  if (!Object.values(location).every(value => textbookIdSchema.safeParse(value).success)) notFound();
  return <StudentSessionGate learningView="textbooks" textbookLocation={location} />;
}
