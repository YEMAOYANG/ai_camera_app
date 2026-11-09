import { notFound } from "next/navigation";
import { StudentSessionGate } from "@/features/auth/student-session-gate";
import { textbookIdSchema } from "@/lib/contracts/textbooks";

export const metadata = { title: "教材课堂" };

export default async function TextbookClassroomPage({ params, searchParams }: {
  params: Promise<{ contentKey: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ contentKey }, query] = await Promise.all([params, searchParams]);
  if (!/^[a-f0-9]{64}$/.test(contentKey)) notFound();
  const entry = textbookIdSchema.optional().safeParse(query.entry);
  if (!entry.success) notFound();
  return <StudentSessionGate textbookCourseKey={contentKey} textbookCourseEntry={entry.data} />;
}
