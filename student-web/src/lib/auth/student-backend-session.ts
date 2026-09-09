import "server-only";

import type { NextRequest, NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";
import { backendRawRequest, backendRequest } from "@/lib/api/server";
import {
  STUDENT_ACCESS_COOKIE,
  STUDENT_REFRESH_COOKIE,
  setStudentSessionCookies,
} from "@/lib/auth/cookies";
import {
  backendErrorSchema,
  studentAuthResponseSchema,
  type StudentAuthResponse,
} from "@/lib/contracts/student-session";

type StudentBackendResult = {
  payload: unknown;
  refreshed?: StudentAuthResponse;
};

type StudentBackendRawResult = {
  response: Response;
  refreshed?: StudentAuthResponse;
};

export async function studentBackendRequest(
  request: NextRequest,
  path: string,
  init: RequestInit = {},
): Promise<StudentBackendResult> {
  const accessToken = request.cookies.get(STUDENT_ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(STUDENT_REFRESH_COOKIE)?.value;
  if (!accessToken && !refreshToken) {
    throw new BackendApiError(401, "student_session_required", "请重新进入学习空间");
  }

  if (accessToken) {
    try {
      return { payload: await requestWithAccess(path, accessToken, init) };
    } catch (error) {
      if (!(error instanceof BackendApiError) || error.status !== 401 || !refreshToken) throw error;
    }
  }

  const refreshed = studentAuthResponseSchema.parse(
    await backendRequest("/api/v2/student/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refreshToken }),
    }),
  );
  return {
    payload: await requestWithAccess(path, refreshed.tokens.accessToken, init),
    refreshed,
  };
}

export async function studentBackendRawRequest(
  request: NextRequest,
  path: string,
  init: RequestInit = {},
): Promise<StudentBackendRawResult> {
  const accessToken = request.cookies.get(STUDENT_ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(STUDENT_REFRESH_COOKIE)?.value;
  if (!accessToken && !refreshToken) {
    throw new BackendApiError(401, "student_session_required", "请重新进入学习空间");
  }

  if (accessToken) {
    try {
      return { response: await requestRawWithAccess(path, accessToken, init) };
    } catch (error) {
      if (!(error instanceof BackendApiError) || error.status !== 401 || !refreshToken) throw error;
    }
  }

  const refreshed = studentAuthResponseSchema.parse(
    await backendRequest("/api/v2/student/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refreshToken }),
    }),
  );
  return {
    response: await requestRawWithAccess(path, refreshed.tokens.accessToken, init),
    refreshed,
  };
}

export function applyRefreshedStudentSession(response: NextResponse, refreshed?: StudentAuthResponse) {
  if (refreshed) setStudentSessionCookies(response, refreshed);
  return response;
}

function requestWithAccess(path: string, accessToken: string, init: RequestInit) {
  return backendRequest(path, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${accessToken}`,
    },
  });
}

async function requestRawWithAccess(path: string, accessToken: string, init: RequestInit) {
  const response = await backendRawRequest(path, {
    ...init,
    headers: {
      ...init.headers,
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (response.ok) return response;
  const payload: unknown = await response.json().catch(() => ({}));
  const parsed = backendErrorSchema.safeParse(payload);
  throw new BackendApiError(
    response.status,
    parsed.success ? parsed.data.error || "backend_error" : "backend_error",
    parsed.success ? parsed.data.message || "素材暂时不可用" : "素材暂时不可用",
  );
}
