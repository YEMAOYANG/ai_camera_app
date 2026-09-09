import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { loadLearningLibrary } from "@/features/learning/server/library-service";
import { studentRouteError } from "@/lib/api/route-response";
import { applyRefreshedStudentSession } from "@/lib/auth/student-backend-session";
import { learningLibraryBucketSchema, learningSubjectSchema } from "@/lib/contracts/learning";

const querySchema = z.object({
  bucket: learningLibraryBucketSchema.default("all"),
  subject: learningSubjectSchema.optional(),
  cursor: z.string().trim().min(1).max(500).optional(),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

export async function GET(request: NextRequest) {
  const parsed = querySchema.safeParse(Object.fromEntries(request.nextUrl.searchParams));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "invalid_learning_library_query", message: "课程筛选条件不正确" },
      { status: 400 },
    );
  }
  try {
    const { data, refreshed } = await loadLearningLibrary(request, parsed.data);
    return applyRefreshedStudentSession(NextResponse.json(data), refreshed);
  } catch (error) {
    return studentRouteError(error, "我的课程暂时没有加载成功");
  }
}
