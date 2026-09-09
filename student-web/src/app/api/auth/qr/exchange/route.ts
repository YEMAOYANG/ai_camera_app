import { NextRequest, NextResponse } from "next/server";

import { backendJsonRequest } from "@/lib/api/server";
import {
  clearStudentQrChallengeCookies,
  setStudentSessionCookies,
  STUDENT_QR_CHALLENGE_COOKIE,
  STUDENT_QR_VERIFIER_COOKIE,
} from "@/lib/auth/cookies";
import { studentQrAuthResponseSchema } from "@/lib/contracts/student-session";
import { isBackendApiError, studentQrBackendErrorResponse } from "@/lib/auth/qr-error-response";

export async function POST(request: NextRequest) {
  const challengeId = request.cookies.get(STUDENT_QR_CHALLENGE_COOKIE)?.value;
  const verifier = request.cookies.get(STUDENT_QR_VERIFIER_COOKIE)?.value;
  if (!challengeId || !verifier) {
    const response = NextResponse.json(
      { ok: false, status: "expired", error: "qr_challenge_missing", message: "二维码已失效，请刷新后重试" },
      { status: 409, headers: { "Cache-Control": "no-store" } },
    );
    clearStudentQrChallengeCookies(response);
    return response;
  }

  try {
    const { payload, status } = await backendJsonRequest("/api/v2/student/auth/qr/exchange", {
      method: "POST",
      body: JSON.stringify({ challengeId, verifier }),
    });
    if (status === 202) {
      return NextResponse.json(
        { ok: false, status: "pending" },
        { status: 202, headers: { "Cache-Control": "no-store" } },
      );
    }

    const parsed = studentQrAuthResponseSchema.safeParse(payload);
    if (!parsed.success) {
      const response = NextResponse.json(
        { ok: false, error: "invalid_backend_response", message: "二维码登录服务返回了无法识别的数据" },
        { status: 502, headers: { "Cache-Control": "no-store" } },
      );
      clearStudentQrChallengeCookies(response);
      return response;
    }
    const auth = parsed.data;
    const response = NextResponse.json(
      { ok: true, student: auth.student },
      { headers: { "Cache-Control": "no-store" } },
    );
    setStudentSessionCookies(response, auth, { persistDevice: true });
    clearStudentQrChallengeCookies(response);
    return response;
  } catch (error) {
    if (isBackendApiError(error)) {
      return studentQrBackendErrorResponse(error);
    }
    return NextResponse.json(
      { ok: false, error: "invalid_backend_response", message: "二维码登录服务返回了无法识别的数据" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
