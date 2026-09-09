import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningStartResponseSchema } from "@/lib/contracts/learning";

const requestSchema = z.object({ taskId: z.string().min(1) });

export async function POST(request: NextRequest) {
  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "missing_task_id", message: "没有找到这节课" }, { status: 400 });
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      "/api/v2/student/learning/sessions",
      { method: "POST", body: JSON.stringify(parsed.data) },
    );
    const response = NextResponse.json(learningStartResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "暂时无法开始这节课");
  }
}
