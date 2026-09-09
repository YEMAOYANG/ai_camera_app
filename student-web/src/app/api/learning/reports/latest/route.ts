import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningReportSchema } from "@/lib/contracts/learning";

const responseSchema = z.object({ ok: z.literal(true), report: learningReportSchema.nullable() });

export async function GET(request: NextRequest) {
  const subject = request.nextUrl.searchParams.get("subject");
  const query = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/reports/latest${query}`,
    );
    const response = NextResponse.json(responseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "暂时无法读取学习记录");
  }
}
