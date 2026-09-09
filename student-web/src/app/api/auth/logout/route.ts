import { NextRequest, NextResponse } from "next/server";

import { backendRequest } from "@/lib/api/server";
import { STUDENT_ACCESS_COOKIE, STUDENT_REFRESH_COOKIE, clearStudentSessionCookies } from "@/lib/auth/cookies";

export async function POST(request: NextRequest) {
  const accessToken = request.cookies.get(STUDENT_ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(STUDENT_REFRESH_COOKIE)?.value;
  if (accessToken || refreshToken) {
    await backendRequest("/api/v2/student/auth/logout", {
      method: "POST",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      body: JSON.stringify({ refreshToken }),
    }).catch(() => undefined);
  }
  const response = NextResponse.json({ ok: true });
  clearStudentSessionCookies(response);
  return response;
}
