import type { Metadata } from "next";

import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata: Metadata = { title: "互动课堂" };

export default async function LessonPage({ params }: { params: Promise<{ taskId: string }> }) {
  const { taskId } = await params;
  return <StudentSessionGate lessonTaskId={taskId} />;
}
