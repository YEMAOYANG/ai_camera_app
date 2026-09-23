import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { placementQuerySchema, placementResponseSchema, placementStartSchema } from "@/lib/contracts/learning-placement";

const headers = { "Cache-Control": "private, no-store" };

export async function GET(request: NextRequest) {
  const parsed = placementQuerySchema.safeParse(Object.fromEntries(request.nextUrl.searchParams));
  if (!parsed.success) return NextResponse.json({ ok: false, message: "请选择要衔接的学科" }, { status: 400, headers });
  try {
    const { payload, refreshed } = await studentBackendRequest(request,
      `/api/v2/student/learning/placement?${new URLSearchParams(parsed.data)}`, { cache: "no-store" });
    const data = placementResponseSchema.parse(payload);
    if (data.subject !== parsed.data.subject) throw new Error("Placement subject mismatch");
    return applyRefreshedStudentSession(NextResponse.json(data, { headers }), refreshed);
  } catch (error) { return studentRouteError(error, "基础摸底暂时没有加载好，请再试一次"); }
}

export async function POST(request: NextRequest) {
  const parsed = placementStartSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ ok: false, message: "请从当前需要的基础开始" }, { status: 400, headers });
  try {
    const { payload, refreshed } = await studentBackendRequest(request, "/api/v2/student/learning/placement", {
      method: "POST", body: JSON.stringify(parsed.data),
    });
    const data = placementResponseSchema.parse(payload);
    if (data.lesson?.lessonId !== parsed.data.lessonId) throw new Error("Placement lesson mismatch");
    return applyRefreshedStudentSession(NextResponse.json(data, { headers }), refreshed);
  } catch (error) { return studentRouteError(error, "基础摸底暂时没有准备好，请再试一次"); }
}
