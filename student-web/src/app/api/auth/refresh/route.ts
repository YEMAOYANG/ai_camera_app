import { NextRequest, NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { backendRequest } from "@/lib/api/server";
import { STUDENT_REFRESH_COOKIE, clearStudentSessionCookies, setStudentSessionCookies } from "@/lib/auth/cookies";
import { studentAuthResponseSchema } from "@/lib/contracts/student-session";

export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get(STUDENT_REFRESH_COOKIE)?.value;
  if (!refreshToken) {
    return NextResponse.json({ ok: false, error: "student_session_required", message: "请重新解锁学习空间" }, { status: 401 });
  }
  try {
    const payload = await backendRequest("/api/v2/student/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refreshToken }),
    });
    const auth = studentAuthResponseSchema.parse(payload);
    const response = NextResponse.json({ ok: true, student: auth.student });
    setStudentSessionCookies(response, auth);
    return response;
  } catch (error) {
    const response = NextResponse.json(
      {
        ok: false,
        error: error instanceof BackendApiError ? error.code : "student_refresh_failed",
        message: error instanceof BackendApiError ? error.message : "请重新解锁学习空间",
      },
      { status: error instanceof BackendApiError ? error.status : 502 },
    );
    clearStudentSessionCookies(response);
    return response;
  }
}
