import { NextRequest, NextResponse } from "next/server";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningTodayResponseSchema } from "@/lib/contracts/learning";

export async function GET(request: NextRequest) {
  const date = request.nextUrl.searchParams.get("date");
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/today${query}`,
    );
    const response = NextResponse.json(learningTodayResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "今天的课程暂时没有准备好");
  }
}
