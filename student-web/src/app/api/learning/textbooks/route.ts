import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { textbookCatalogSchema } from "@/lib/contracts/textbooks";

export async function GET(request: NextRequest) {
  if (request.nextUrl.searchParams.size) {
    return NextResponse.json({ ok: false, error: "textbook_query_invalid", message: "教材查询参数无效" }, { status: 400 });
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(request, "/api/v2/student/learning/textbooks", { cache: "no-store" });
    return applyRefreshedStudentSession(NextResponse.json(textbookCatalogSchema.parse(payload), { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) {
    return studentRouteError(error, "教材目录暂时没有加载成功，请再试一次");
  }
}
