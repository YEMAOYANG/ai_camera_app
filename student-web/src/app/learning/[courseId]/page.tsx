import type { Metadata } from "next";

import { StudentSessionGate } from "@/features/auth/student-session-gate";

export const metadata: Metadata = { title: "课程详情" };

export default async function LearningCoursePage({
  params,
  searchParams,
}: {
  params: Promise<{ courseId: string }>;
  searchParams: Promise<{ version?: string | string[] }>;
}) {
  const { courseId } = await params;
  const query = await searchParams;
  const version = typeof query.version === "string" ? query.version : undefined;
  return <StudentSessionGate learningView="course" courseId={courseId} courseVersion={version} />;
}
