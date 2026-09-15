import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { BackendApiError } from "@/lib/api/errors";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningCourseStartResponseSchema } from "@/lib/contracts/learning";

const paramsSchema = z.object({
  courseId: z.string().trim().min(1).max(160),
  version: z.string().trim().min(1).max(80),
});
const bodySchema = z.object({}).strict();

export async function POST(request: NextRequest, context: { params: Promise<{ courseId: string; version: string }> }) {
  const params = paramsSchema.safeParse(await context.params);
  const body = bodySchema.safeParse(await request.json().catch(() => null));
  if (!params.success || !body.success) {
    return NextResponse.json({ ok: false, error: "invalid_learning_course", message: "课程地址不正确" }, { status: 400 });
  }
  const { courseId, version } = params.data;
  try {
    const { payload, refreshed } = await studentBackendRequest(request,
      `/api/v2/student/learning/courses/${encodeURIComponent(courseId)}/versions/${encodeURIComponent(version)}/start`,
      { method: "POST", body: JSON.stringify({}) });
    const parsed = learningCourseStartResponseSchema.parse(payload);
    if (parsed.courseId !== courseId || parsed.courseVersion !== version) {
      throw new BackendApiError(502, "learning_course_start_invalid", "暂时无法进入这节课，请再试一次");
    }
    return applyRefreshedStudentSession(NextResponse.json(parsed), refreshed);
  } catch (error) {
    return studentRouteError(error, "暂时无法进入这节课，请再试一次");
  }
}
