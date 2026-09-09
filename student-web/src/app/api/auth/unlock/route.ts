import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { BackendApiError } from "@/lib/api/errors";
import { backendRequest } from "@/lib/api/server";
import { STUDENT_DEVICE_COOKIE, setStudentSessionCookies } from "@/lib/auth/cookies";
import { studentAuthResponseSchema } from "@/lib/contracts/student-session";

const requestSchema = z.object({ pin: z.string().regex(/^\d{4}$/, "请输入4位数字PIN") });

export async function POST(request: NextRequest) {
  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  const deviceToken = request.cookies.get(STUDENT_DEVICE_COOKIE)?.value;
  if (!deviceToken) {
    return NextResponse.json({ ok: false, error: "device_not_paired", message: "这台设备还没有经过家长授权" }, { status: 401 });
  }
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "invalid_pin", message: "请输入4位数字PIN" }, { status: 400 });
  }

  try {
    const payload = await backendRequest("/api/v2/student/auth/unlock", {
      method: "POST",
      body: JSON.stringify({ deviceToken, pin: parsed.data.pin }),
    });
    const auth = studentAuthResponseSchema.parse(payload);
    const response = NextResponse.json({ ok: true, student: auth.student });
    setStudentSessionCookies(response, auth);
    return response;
  } catch (error) {
    if (error instanceof BackendApiError) {
      return NextResponse.json({ ok: false, error: error.code, message: error.message }, { status: error.status });
    }
    return NextResponse.json({ ok: false, error: "invalid_backend_response", message: "解锁服务返回了无法识别的数据" }, { status: 502 });
  }
}
