import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { practiceStartSchema, practiceResponseSchema } from "@/lib/contracts/learning-practice";

export async function POST(request: NextRequest) {
  const parsed = practiceStartSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ ok: false, message: "请选择学科，每次最多练习五题" }, { status: 400 });
  try {
    const { payload, refreshed } = await studentBackendRequest(request, "/api/v2/student/practice/sessions", {
      method: "POST", body: JSON.stringify(parsed.data),
    });
    return applyRefreshedStudentSession(NextResponse.json(practiceResponseSchema.parse(payload)), refreshed);
  } catch (error) { return studentRouteError(error, "复习题暂时没准备好，请先回学习书架"); }
}
