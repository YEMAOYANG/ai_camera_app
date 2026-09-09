import type { Metadata } from "next";

import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata: Metadata = { title: "Mira 互动课堂" };

export default async function ClassroomLessonPage({
  params,
}: {
  params: Promise<{ taskId: string }>;
}) {
  const { taskId } = await params;
  return <StudentSessionGate lessonTaskId={taskId} classroomMode="openmaic" />;
}
