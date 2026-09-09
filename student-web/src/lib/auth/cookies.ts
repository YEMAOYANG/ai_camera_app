import type { NextResponse } from "next/server";

import type { StudentAuthResponse } from "@/lib/contracts/student-session";
import { studentCookiesUseSecureTransport } from "@/lib/security/local-lan-production";

export const STUDENT_ACCESS_COOKIE = "mira_student_access";
export const STUDENT_REFRESH_COOKIE = "mira_student_refresh";
export const STUDENT_DEVICE_COOKIE = "mira_student_device";
export const STUDENT_QR_CHALLENGE_COOKIE = "mira_student_qr_challenge";
export const STUDENT_QR_VERIFIER_COOKIE = "mira_student_qr_verifier";
export const STUDENT_QR_DISPLAY_CODE_COOKIE = "mira_student_qr_display_code";
export const STUDENT_QR_EXPIRES_AT_COOKIE = "mira_student_qr_expires_at";
export const STUDENT_QR_POLLING_INTERVAL_COOKIE = "mira_student_qr_polling_interval";
export const STUDENT_BROWSER_FINGERPRINT_COOKIE = "mira_student_browser_fingerprint";
export const STUDENT_FAVORITES_COOKIE = "mira_student_favorites";

function cookieBase() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: studentCookiesUseSecureTransport(),
    path: "/",
  };
}

function qrCookieBase() {
  return {
    ...cookieBase(),
    path: "/api/auth/qr",
    priority: "high" as const,
  };
}

export function setStudentSessionCookies(
  response: NextResponse,
  auth: StudentAuthResponse,
  options: { persistDevice?: boolean } = {},
) {
  const now = Date.now();
  response.cookies.set(STUDENT_ACCESS_COOKIE, auth.tokens.accessToken, {
    ...cookieBase(),
    maxAge: Math.max(1, Math.floor((auth.tokens.accessTokenExpiresAt - now) / 1000)),
  });
  response.cookies.set(STUDENT_REFRESH_COOKIE, auth.tokens.refreshToken, {
    ...cookieBase(),
    maxAge: Math.max(1, Math.floor((auth.tokens.refreshTokenExpiresAt - now) / 1000)),
  });
  if (options.persistDevice && auth.deviceToken) {
    const trustedUntil = auth.device.trustedUntil ?? now + 60 * 60 * 24 * 180 * 1000;
    response.cookies.set(STUDENT_DEVICE_COOKIE, auth.deviceToken, {
      ...cookieBase(),
      maxAge: Math.max(1, Math.floor((trustedUntil - now) / 1000)),
    });
  }
}

export function clearStudentSessionCookies(response: NextResponse, options: { forgetDevice?: boolean } = {}) {
  response.cookies.set(STUDENT_ACCESS_COOKIE, "", { ...cookieBase(), maxAge: 0 });
  response.cookies.set(STUDENT_REFRESH_COOKIE, "", { ...cookieBase(), maxAge: 0 });
  if (options.forgetDevice) {
    response.cookies.set(STUDENT_DEVICE_COOKIE, "", { ...cookieBase(), maxAge: 0 });
  }
}

export function setStudentQrChallengeCookies(
  response: NextResponse,
  challenge: {
    challengeId: string;
    verifier: string;
    displayCode: string;
    expiresAt: number;
    pollingIntervalMs: number;
  },
) {
  const maxAge = Math.max(1, Math.floor((challenge.expiresAt - Date.now()) / 1000));
  response.cookies.set(STUDENT_QR_CHALLENGE_COOKIE, challenge.challengeId, {
    ...qrCookieBase(),
    maxAge,
  });
  response.cookies.set(STUDENT_QR_VERIFIER_COOKIE, challenge.verifier, {
    ...qrCookieBase(),
    maxAge,
  });
  // Persist only the public presentation metadata needed to restore the same
  // pending challenge after a page reload or a brief backend outage. These
  // remain HttpOnly alongside the verifier and are never exposed separately.
  response.cookies.set(STUDENT_QR_DISPLAY_CODE_COOKIE, challenge.displayCode, {
    ...qrCookieBase(),
    maxAge,
  });
  response.cookies.set(STUDENT_QR_EXPIRES_AT_COOKIE, String(challenge.expiresAt), {
    ...qrCookieBase(),
    maxAge,
  });
  response.cookies.set(STUDENT_QR_POLLING_INTERVAL_COOKIE, String(challenge.pollingIntervalMs), {
    ...qrCookieBase(),
    maxAge,
  });
}

export function clearStudentQrChallengeCookies(response: NextResponse) {
  response.cookies.set(STUDENT_QR_CHALLENGE_COOKIE, "", { ...qrCookieBase(), maxAge: 0 });
  response.cookies.set(STUDENT_QR_VERIFIER_COOKIE, "", { ...qrCookieBase(), maxAge: 0 });
  response.cookies.set(STUDENT_QR_DISPLAY_CODE_COOKIE, "", { ...qrCookieBase(), maxAge: 0 });
  response.cookies.set(STUDENT_QR_EXPIRES_AT_COOKIE, "", { ...qrCookieBase(), maxAge: 0 });
  response.cookies.set(STUDENT_QR_POLLING_INTERVAL_COOKIE, "", { ...qrCookieBase(), maxAge: 0 });
}

export function setStudentBrowserFingerprintCookie(response: NextResponse, fingerprint: string) {
  response.cookies.set(STUDENT_BROWSER_FINGERPRINT_COOKIE, fingerprint, {
    ...cookieBase(),
    maxAge: 60 * 60 * 24 * 180,
    priority: "high",
  });
}

export function setStudentFavoritesCookie(response: NextResponse, courseIds: string[]) {
  response.cookies.set(
    STUDENT_FAVORITES_COOKIE,
    encodeURIComponent(JSON.stringify(courseIds.slice(0, 64))),
    {
      ...cookieBase(),
      maxAge: 60 * 60 * 24 * 180,
      priority: "medium",
    },
  );
}
