import { NextRequest, NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { internationalTrialsSchema } from "@/lib/contracts/international-trials";

const headers = { "Cache-Control": "private, no-store" };

export async function GET(request: NextRequest) {
  if (request.nextUrl.searchParams.size) {
    return NextResponse.json({ ok: false, error: "invalid_international_trial_request", message: "请重新打开国际教材测试" }, { status: 400, headers });
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(request, "/api/v2/student/learning/international-trials", { cache: "no-store" });
    const data = internationalTrialsSchema.parse(payload);
    return applyRefreshedStudentSession(NextResponse.json(data, { headers }), refreshed);
  } catch (error) {
    if (error instanceof BackendApiError && error.status === 401) {
      return NextResponse.json({ ok: false, error: "student_session_required", message: "请重新进入学习空间" }, { status: 401, headers });
    }
    if (error instanceof BackendApiError && error.status === 403) {
      return NextResponse.json({ ok: false, error: "international_trial_unavailable", message: "当前学习身份暂时无法查看教材测试" }, { status: 403, headers });
    }
    return NextResponse.json({ ok: false, error: "international_trial_load_failed", message: "教材测试暂时没有加载成功，请再试一次" }, { status: 502, headers });
  }
}
