import { type NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import {
  classroomRuntimeResponseSchema,
  completeClassroomActionRequestSchema,
} from "@/lib/contracts/lesson-package";

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string; actionId: string }> },
) {
  const parsed = completeClassroomActionRequestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "invalid_classroom_action_result", message: "这一步的完成信息不完整" },
      { status: 400 },
    );
  }
  const { sessionId, actionId } = await context.params;
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/complete`,
      { method: "POST", body: JSON.stringify(parsed.data) },
    );
    const response = NextResponse.json(classroomRuntimeResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "这一步暂时没有保存成功");
  }
}

