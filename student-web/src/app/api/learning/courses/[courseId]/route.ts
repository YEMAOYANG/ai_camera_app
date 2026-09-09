import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { loadLearningCourse } from "@/features/learning/server/library-service";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession } from "@/lib/auth/student-backend-session";

const paramsSchema = z.object({ courseId: z.string().trim().min(1).max(160) });
const querySchema = z.object({ version: z.string().trim().min(1).max(80).optional() });

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ courseId: string }> },
) {
  const params = paramsSchema.safeParse(await context.params);
  const query = querySchema.safeParse(Object.fromEntries(request.nextUrl.searchParams));
  if (!params.success || !query.success) {
    return NextResponse.json(
      { ok: false, error: "invalid_learning_course", message: "课程地址不正确" },
      { status: 400 },
    );
  }
  try {
    const { data, refreshed } = await loadLearningCourse(
      request,
      params.data.courseId,
      query.data.version,
    );
    return applyRefreshedStudentSession(NextResponse.json(data), refreshed);
  } catch (error) {
    return studentRouteError(error, "课程详情暂时没有加载成功");
  }
}
