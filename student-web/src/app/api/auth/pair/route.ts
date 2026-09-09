import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { backendRequest } from "@/lib/api/server";
import { BackendApiError } from "@/lib/api/errors";
import { studentBrowserFingerprint, studentClientDevice } from "@/lib/auth/client-device";
import {
  clearStudentQrChallengeCookies,
  setStudentBrowserFingerprintCookie,
  setStudentSessionCookies,
} from "@/lib/auth/cookies";
import { studentAuthResponseSchema } from "@/lib/contracts/student-session";

const requestSchema = z.object({ code: z.string().trim().min(6).max(16) });

export async function POST(request: NextRequest) {
  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "invalid_pairing_code", message: "请输入家长 App 中的配对码" }, { status: 400 });
  }

  try {
    const fingerprint = studentBrowserFingerprint(request);
    const payload = await backendRequest("/api/v2/student/auth/pair", {
      method: "POST",
      body: JSON.stringify({
        pairingCode: parsed.data.code,
        clientDevice: studentClientDevice(request, fingerprint.value),
      }),
    });
    const auth = studentAuthResponseSchema.parse(payload);
    const response = NextResponse.json({ ok: true, student: auth.student });
    setStudentSessionCookies(response, auth, { persistDevice: true });
    clearStudentQrChallengeCookies(response);
    if (fingerprint.isNew) setStudentBrowserFingerprintCookie(response, fingerprint.value);
    return response;
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json({ ok: false, error: error.code, message: error.message }, { status: error.status });
    }
    return NextResponse.json({ ok: false, error: "invalid_backend_response", message: "登录服务返回了无法识别的数据" }, { status: 502 });
  }
}
