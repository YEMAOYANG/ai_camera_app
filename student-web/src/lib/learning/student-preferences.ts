import "server-only";

import type { NextRequest } from "next/server";

import { STUDENT_FAVORITES_COOKIE } from "@/lib/auth/cookies";

export function readStudentFavoriteIds(request: NextRequest) {
  const raw = request.cookies.get(STUDENT_FAVORITES_COOKIE)?.value;
  if (!raw) return new Set<string>();
  try {
    const value: unknown = JSON.parse(decodeURIComponent(raw));
    if (!Array.isArray(value)) return new Set<string>();
    return new Set(
      value
        .filter((courseId): courseId is string => typeof courseId === "string")
        .map((courseId) => courseId.trim())
        .filter((courseId) => courseId.length > 0 && courseId.length <= 160)
        .slice(0, 64),
    );
  } catch {
    return new Set<string>();
  }
}
