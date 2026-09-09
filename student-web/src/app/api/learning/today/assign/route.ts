import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningTodayResponseSchema } from "@/lib/contracts/learning";

export async function POST(request: NextRequest) {
  const body: unknown = await request.json().catch(() => ({}));
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      "/api/v2/student/learning/today/assign",
      { method: "POST", body: JSON.stringify(body) },
    );
    const response = NextResponse.json(learningTodayResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "课程安排失败，请稍后再试");
  }
}
