import { NextResponse } from "next/server";

import { BackendApiError } from "@/lib/api/errors";

export function studentRouteError(error: unknown, fallbackMessage = "学习服务暂时不可用，请稍后再试") {
  if (error instanceof BackendApiError) {
    return NextResponse.json(
      { ok: false, error: error.code, message: error.message },
      { status: error.status },
    );
  }
  return NextResponse.json(
    { ok: false, error: "student_learning_failed", message: fallbackMessage },
    { status: 502 },
  );
}
