import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { placementAttemptIdSchema, placementResponseSchema } from "@/lib/contracts/learning-placement";

export async function GET(request: NextRequest, context: { params: Promise<{ attemptId: string }> }) {
  const { attemptId } = await context.params;
  if (!placementAttemptIdSchema.safeParse(attemptId).success) return NextResponse.json({ ok: false, message: "这次摸底暂时无法恢复" }, { status: 400 });
  try {
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/learning/placement/${attemptId}`, { cache: "no-store" });
    const data = placementResponseSchema.parse(payload);
    if (data.attempt?.id !== attemptId) throw new Error("Placement attempt mismatch");
    return applyRefreshedStudentSession(NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) { return studentRouteError(error, "这次摸底暂时没有恢复好，请再试一次"); }
}
