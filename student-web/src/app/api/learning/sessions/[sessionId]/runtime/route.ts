import { type NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { classroomRuntimeResponseSchema } from "@/lib/contracts/lesson-package";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/sessions/${encodeURIComponent(sessionId)}/runtime`,
    );
    const response = NextResponse.json(classroomRuntimeResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "暂时无法读取课堂进度");
  }
}

