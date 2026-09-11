import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { practiceResponseSchema } from "@/lib/contracts/learning-practice";

export async function GET(request: NextRequest, context: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await context.params;
  if (!/^practice_[a-f0-9]{32}$/.test(sessionId)) return NextResponse.json({ ok: false, message: "没有找到这次练习" }, { status: 404 });
  try {
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/practice/sessions/${sessionId}`);
    return applyRefreshedStudentSession(NextResponse.json(practiceResponseSchema.parse(payload)), refreshed);
  } catch (error) { return studentRouteError(error, "暂时无法恢复这次练习"); }
}
