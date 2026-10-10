import { NextRequest, NextResponse } from "next/server";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { homeworkActionSchema, homeworkAnswerSchema, homeworkDetailSchema, homeworkIdSchema, homeworkItemIdSchema, homeworkListSchema } from "@/lib/contracts/homework";
export async function homeworkRoute(request: NextRequest, id?: string, itemId?: string, operation?: "actions" | "answers") {
  if (request.nextUrl.searchParams.size || (id && !homeworkIdSchema.safeParse(id).success) || (itemId && !homeworkItemIdSchema.safeParse(itemId).success)) return NextResponse.json({ ok: false, message: "作业请求无效" }, { status: 400 });
  let body;
  if (operation) {
    const parsed = (operation === "answers" ? homeworkAnswerSchema : homeworkActionSchema).safeParse(await request.json().catch(() => null));
    if (!parsed.success) return NextResponse.json({ ok: false, message: "请重新打开这道题" }, { status: 400 });
    body = JSON.stringify(parsed.data);
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/learning/homework${id ? `/${id}` : ""}${itemId ? `/items/${itemId}/${operation}` : ""}`, { method: operation ? "POST" : "GET", ...(body ? { body } : {}), cache: "no-store" });
    return applyRefreshedStudentSession(NextResponse.json((id ? homeworkDetailSchema : homeworkListSchema).parse(payload), { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) { return studentRouteError(error, "小任务暂时没连接上，请再试一次"); }
}
