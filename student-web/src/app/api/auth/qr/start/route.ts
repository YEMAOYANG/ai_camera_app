import { NextRequest, NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { backendRequest } from "@/lib/api/server";
import { studentBrowserFingerprint, studentClientDevice } from "@/lib/auth/client-device";
import {
  setStudentBrowserFingerprintCookie,
  setStudentQrChallengeCookies,
  STUDENT_QR_CHALLENGE_COOKIE,
  STUDENT_QR_DISPLAY_CODE_COOKIE,
  STUDENT_QR_EXPIRES_AT_COOKIE,
  STUDENT_QR_POLLING_INTERVAL_COOKIE,
  STUDENT_QR_VERIFIER_COOKIE,
} from "@/lib/auth/cookies";
import { StudentWebPublicUrlError, studentWebPublicOrigin } from "@/lib/auth/student-web-public-url";
import {
  studentQrChallengeIdSchema,
  studentQrChallengeSchema,
  studentQrDisplayCodeSchema,
  studentQrPollingIntervalSchema,
  studentQrVerifierSchema,
} from "@/lib/contracts/student-session";

export async function POST(request: NextRequest) {
  try {
    const publicOrigin = studentWebPublicOrigin();
    const existing = existingChallenge(request);
    if (existing) return challengeResponse(publicOrigin, existing);

    const fingerprint = studentBrowserFingerprint(request);
    const payload = await backendRequest("/api/v2/student/auth/qr/challenges", {
      method: "POST",
      body: JSON.stringify({ clientDevice: studentClientDevice(request, fingerprint.value) }),
    });
    const challenge = studentQrChallengeSchema.parse(payload);
    const response = challengeResponse(publicOrigin, challenge);
    setStudentQrChallengeCookies(response, challenge);
    if (fingerprint.isNew) setStudentBrowserFingerprintCookie(response, fingerprint.value);
    return response;
  } catch (error) {
    if (error instanceof StudentWebPublicUrlError) {
      return NextResponse.json(
        { ok: false, error: "student_web_public_url_invalid", message: error.message },
        { status: 503, headers: { "Cache-Control": "no-store" } },
      );
    }
    if (error instanceof BackendApiError) {
      return NextResponse.json(
        { ok: false, error: error.code, message: error.message },
        { status: error.status, headers: { "Cache-Control": "no-store" } },
      );
    }
    return NextResponse.json(
      { ok: false, error: "invalid_backend_response", message: "二维码登录服务返回了无法识别的数据" },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}

function existingChallenge(request: NextRequest) {
  const challengeId = studentQrChallengeIdSchema.safeParse(
    request.cookies.get(STUDENT_QR_CHALLENGE_COOKIE)?.value,
  );
  const displayCode = studentQrDisplayCodeSchema.safeParse(
    request.cookies.get(STUDENT_QR_DISPLAY_CODE_COOKIE)?.value,
  );
  const verifier = studentQrVerifierSchema.safeParse(
    request.cookies.get(STUDENT_QR_VERIFIER_COOKIE)?.value,
  );
  const expiresAt = Number(request.cookies.get(STUDENT_QR_EXPIRES_AT_COOKIE)?.value);
  const pollingIntervalMs = studentQrPollingIntervalSchema.safeParse(
    Number(request.cookies.get(STUDENT_QR_POLLING_INTERVAL_COOKIE)?.value),
  );
  if (
    !challengeId.success ||
    !displayCode.success ||
    !verifier.success ||
    !Number.isSafeInteger(expiresAt) ||
    expiresAt <= Date.now() ||
    !pollingIntervalMs.success
  ) {
    return null;
  }
  return {
    challengeId: challengeId.data,
    displayCode: displayCode.data,
    expiresAt,
    pollingIntervalMs: pollingIntervalMs.data,
  };
}

function challengeResponse(
  publicOrigin: string,
  challenge: {
    challengeId: string;
    displayCode: string;
    expiresAt: number;
    pollingIntervalMs: number;
  },
) {
  const qrUrl = new URL("/pair/qr", publicOrigin);
  qrUrl.searchParams.set("challengeId", challenge.challengeId);
  return NextResponse.json(
    {
      ok: true,
      qrValue: qrUrl.toString(),
      displayCode: challenge.displayCode,
      expiresAt: challenge.expiresAt,
      pollingIntervalMs: challenge.pollingIntervalMs,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
