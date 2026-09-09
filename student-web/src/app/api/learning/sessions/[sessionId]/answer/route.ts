import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningAnswerResponseSchema } from "@/lib/contracts/learning";

const requestSchema = z.object({
  answer: z.union([z.string(), z.array(z.string())]).optional(),
  response: z.unknown().optional(),
}).refine((value) => value.answer !== undefined || value.response !== undefined);

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "missing_answer", message: "请先回答这道题" }, { status: 400 });
  }
  const { sessionId } = await context.params;
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/sessions/${encodeURIComponent(sessionId)}/answer`,
      { method: "POST", body: JSON.stringify(parsed.data) },
    );
    const response = NextResponse.json(learningAnswerResponseSchema.parse(payload));
    return applyRefreshedStudentSession(response, refreshed);
  } catch (error) {
    return studentRouteError(error, "答案暂时没有提交成功");
  }
}
