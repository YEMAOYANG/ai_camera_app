import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { homeworkDetailSchema } from "@/lib/contracts/homework";
const captureSchema = z.object({ taskId: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/), idempotencyKey: z.string().uuid() }).strict();
export async function POST(request: NextRequest) {
  const parsed = captureSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success || request.nextUrl.searchParams.size) return NextResponse.json({ ok: false, message: "请从已授权的作业任务拍摄" }, { status: 400 });
  try {
    const { payload, refreshed } = await studentBackendRequest(request, "/api/v2/student/learning/homework-captures", { method: "POST", body: JSON.stringify(parsed.data), cache: "no-store" });
    return applyRefreshedStudentSession(NextResponse.json(homeworkDetailSchema.parse(payload), { headers: { "Cache-Control": "private, no-store" }, status: 202 }), refreshed);
  } catch (error) { return studentRouteError(error, "拍摄暂时不可用，请在家长 App 上传"); }
}
