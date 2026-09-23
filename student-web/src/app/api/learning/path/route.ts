import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession, studentBackendRequest } from "@/lib/auth/student-backend-session";
import { learningSubjectSchema } from "@/lib/contracts/learning";
import { progressiveGradeSchema, progressivePathSchema } from "@/lib/contracts/progressive-learning";

const querySchema = z.object({
  subject: learningSubjectSchema.default("chinese"),
  gradeCode: progressiveGradeSchema.optional(),
}).strict();

export async function GET(request: NextRequest) {
  const parsed = querySchema.safeParse(Object.fromEntries(request.nextUrl.searchParams));
  if (!parsed.success) {
    return NextResponse.json({ ok: false, error: "invalid_learning_path_query", message: "请选择一至六年级及对应学科" }, { status: 400 });
  }
  const search = new URLSearchParams({ subject: parsed.data.subject });
  if (parsed.data.gradeCode) search.set("gradeCode", parsed.data.gradeCode);
  try {
    const { payload, refreshed } = await studentBackendRequest(request, `/api/v2/student/learning/path?${search}`, { cache: "no-store" });
    const data = progressivePathSchema.parse(payload);
    if (data.subject !== parsed.data.subject || parsed.data.gradeCode && data.gradeCode !== parsed.data.gradeCode) {
      throw new Error("Path response scope mismatch");
    }
    return applyRefreshedStudentSession(NextResponse.json(data, { headers: { "Cache-Control": "private, no-store" } }), refreshed);
  } catch (error) {
    return studentRouteError(error, "学习路线暂时没有加载成功，请再试一次");
  }
}
