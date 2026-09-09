import { NextRequest, NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { studentRouteError } from "@/lib/api/route-response";
import {
  STUDENT_DEVICE_COOKIE,
  clearStudentSessionCookies,
} from "@/lib/auth/cookies";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { studentMeResponseSchema } from "@/lib/contracts/student-session";

export async function GET(request: NextRequest) {
  const canUnlock = Boolean(request.cookies.get(STUDENT_DEVICE_COOKIE)?.value);

  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      "/api/v2/student/me",
    );
    const response = NextResponse.json(studentMeResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    if (!(error instanceof BackendApiError) || error.status !== 401) {
      return studentRouteError(error, "暂时无法读取学习身份，请稍后再试");
    }
    const response = NextResponse.json(
      {
        ok: false,
        error: error.code,
        message: "请进入学习空间",
        canUnlock,
      },
      { status: 401 },
    );
    clearStudentSessionCookies(response);
    return response;
  }
}
