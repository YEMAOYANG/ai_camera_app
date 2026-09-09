import "server-only";

import { backendErrorSchema } from "@/lib/contracts/student-session";
import { BackendApiError } from "@/lib/api/errors";

function backendBaseUrl() {
  const value = process.env.MIRA_BACKEND_URL?.trim() || "http://127.0.0.1:8000";
  return value.replace(/\/$/, "");
}

export async function backendRawRequest(path: string, init: RequestInit = {}) {
  try {
    return await fetch(`${backendBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
    });
  } catch {
    throw new BackendApiError(503, "backend_unavailable", "学习服务暂时连不上，请稍后再试");
  }
}

export async function backendJsonRequest(path: string, init: RequestInit = {}) {
  const response = await backendRawRequest(path, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init.headers,
    },
  });

  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const parsed = backendErrorSchema.safeParse(payload);
    throw new BackendApiError(
      response.status,
      parsed.success ? parsed.data.error || "backend_error" : "backend_error",
      parsed.success ? parsed.data.message || "服务暂时不可用，请稍后重试" : "服务暂时不可用，请稍后重试",
    );
  }
  return { payload, status: response.status };
}

export async function backendRequest(path: string, init: RequestInit = {}) {
  return (await backendJsonRequest(path, init)).payload;
}
