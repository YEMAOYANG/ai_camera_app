import type { Metadata } from "next";
import { StudentSessionGate } from "@/features/auth/student-session-gate";
export const metadata: Metadata = { title: "学过的内容，练一练" };
export default async function PracticePage({ searchParams }: { searchParams: Promise<{ session?: string }> }) {
  const { session } = await searchParams;
  return <StudentSessionGate learningView="practice" practiceSessionId={session} />;
}
