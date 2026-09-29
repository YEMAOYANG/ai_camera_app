import { notFound } from "next/navigation";
import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata = { title: "教材课堂" };

export default async function TextbookClassroomPage({ params }: { params: Promise<{ contentKey: string }> }) {
  const { contentKey } = await params;
  if (!/^[a-f0-9]{64}$/.test(contentKey)) notFound();
  return <StudentSessionGate textbookCourseKey={contentKey} />;
}
