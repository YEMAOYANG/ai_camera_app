import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { studentRouteError } from "@/lib/api/route-response";
import {
  applyRefreshedStudentSession,
  studentBackendRequest,
} from "@/lib/auth/student-backend-session";
import {
  learningTeacherPreferenceRequestSchema,
  learningTeacherPreferenceResponseSchema,
  learningSubjectSchema,
  learningTeachersResponseSchema,
} from "@/lib/contracts/learning";

const querySchema = z.object({ subject: learningSubjectSchema.optional() }).strict();

export async function GET(request: NextRequest) {
  const query = querySchema.safeParse(Object.fromEntries(request.nextUrl.searchParams));
  if (!query.success) {
    return NextResponse.json(
      { ok: false, error: "invalid_teacher_subject", message: "老师的学科不正确" },
      { status: 400 },
    );
  }
  const search = query.data.subject ? `?subject=${encodeURIComponent(query.data.subject)}` : "";
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      `/api/v2/student/learning/teachers${search}`,
    );
    const data = learningTeachersResponseSchema.parse(payload);
    return applyRefreshedStudentSession(NextResponse.json(data), refreshed);
  } catch (error) {
    return studentRouteError(error, "老师列表暂时没有加载成功");
  }
}

export async function PUT(request: NextRequest) {
  const parsed = learningTeacherPreferenceRequestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "invalid_teacher_preference", message: "老师选择不正确" },
      { status: 400 },
    );
  }
  try {
    const { payload, refreshed } = await studentBackendRequest(
      request,
      "/api/v2/student/learning/preferences/teacher",
      { method: "PUT", body: JSON.stringify(parsed.data) },
    );
    const data = learningTeacherPreferenceResponseSchema.parse(payload);
    return applyRefreshedStudentSession(NextResponse.json(data), refreshed);
  } catch (error) {
    return studentRouteError(error, "老师偏好暂时没有保存成功");
  }
}
