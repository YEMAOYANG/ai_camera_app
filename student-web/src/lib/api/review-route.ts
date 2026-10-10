import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { reviewActionSchema, reviewAnswerSchema, reviewId, reviewListSchema, reviewResponseSchema } from "@/lib/contracts/learning-review";

export async function reviewRoute(request: NextRequest, id?: string, operation?: "actions" | "answers") {
  if (request.nextUrl.searchParams.size || (id !== undefined && !reviewId.safeParse(id).success)) {
    return NextResponse.json({ ok: false, message: "复习请求无效" }, { status: 400 });
  }
  let body;
  if (operation) {
    const parsed = (operation === "answers" ? reviewAnswerSchema : reviewActionSchema).safeParse(await request.json().catch(() => null));
    if (!parsed.success) return NextResponse.json({ ok: false, message: "请重新打开当前小任务" }, { status: 400 });
    body = JSON.stringify(parsed.data);
  }
  try {
    const path = `/api/v2/student/learning/reviews${id ? `/${encodeURIComponent(id)}` : ""}${operation ? `/${operation}` : ""}`;
    const { payload, refreshed } = await studentBackendRequest(request, path, { method: operation ? "POST" : "GET", ...(body ? { body } : {}), cache: "no-store" });
    return applyRefreshedStudentSession(NextResponse.json((id ? reviewResponseSchema : reviewListSchema).parse(payload), { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) { return studentRouteError(error, "复习暂时没有连接上，请再试一次"); }
}
