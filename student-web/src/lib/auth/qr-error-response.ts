import { NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { clearStudentQrChallengeCookies } from "@/lib/auth/cookies";

type QrTerminalStatus = "expired" | "rejected" | "consumed";
type BackendErrorShape = Pick<BackendApiError, "status" | "code" | "message">;

const terminalStatusByError: Partial<Record<string, QrTerminalStatus>> = {
  student_qr_challenge_expired: "expired",
  student_qr_challenge_rejected: "rejected",
  student_qr_challenge_consumed: "consumed",
};

const terminalErrorCodes = new Set([
  "invalid_student_qr_challenge",
  "student_qr_challenge_expired",
  "student_qr_challenge_rejected",
  "student_qr_challenge_consumed",
  "student_qr_pin_required",
  "student_learning_primary_only",
  "student_access_disabled",
]);

export function studentQrBackendErrorResponse(error: BackendErrorShape) {
  const terminalStatus = terminalStatusByError[error.code];
  const response = NextResponse.json(
    {
      ok: false,
      ...(terminalStatus ? { status: terminalStatus } : {}),
      error: error.code,
      message: error.message,
    },
    { status: error.status, headers: { "Cache-Control": "no-store" } },
  );
  if (terminalErrorCodes.has(error.code)) clearStudentQrChallengeCookies(response);
  return response;
}

export function isBackendApiError(error: unknown): error is BackendApiError {
  return (
    error instanceof BackendApiError ||
    (typeof error === "object" &&
      error !== null &&
      "status" in error &&
      typeof error.status === "number" &&
      "code" in error &&
      typeof error.code === "string" &&
      "message" in error &&
      typeof error.message === "string")
  );
}
