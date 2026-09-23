import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { placementAnswerSchema, placementAttemptIdSchema, placementResponseSchema } from "@/lib/contracts/learning-placement";

export async function POST(request: NextRequest, context: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await context.params;
  const parsed = placementAnswerSchema.safeParse(await request.json().catch(() => null));
  if (!placementAttemptIdSchema.safeParse(attemptId).success || !parsed.success) {
    return NextResponse.json({ ok: false, message: "请填写当前这道题的答案" }, { status: 400 });
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/learning/placement/${attemptId}/answers`, {
      method: "POST", body: JSON.stringify(parsed.data),
    });
    const data = placementResponseSchema.parse(payload);
    if (data.attempt?.id !== attemptId) throw new Error("Placement attempt mismatch");
    return applyRefreshedStudentSession(NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) { return studentRouteError(error, "答案还没保存好，请再试一次"); }
}
