import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { practiceAnswerSchema, practiceResponseSchema } from "@/lib/contracts/learning-practice";

export async function POST(request: NextRequest, context: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await context.params;
  const parsed = practiceAnswerSchema.safeParse(await request.json().catch(() => null));
  if (!/^practice_[a-f0-9]{32}$/.test(sessionId) || !parsed.success) return NextResponse.json({ ok: false, message: "请填写当前这道题的答案" }, { status: 400 });
  try {
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/practice/sessions/${sessionId}/answers`, {
      method: "POST", body: JSON.stringify(parsed.data),
    });
    return applyRefreshedStudentSession(NextResponse.json(practiceResponseSchema.parse(payload)), refreshed);
  } catch (error) { return studentRouteError(error, "答案还没保存好，请再试一次"); }
}
