import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { isCompatibilityMiss, loadLearningCourse } from "@/features/learning/server/library-service";
import { studentRouteError } from "@/lib/api/route-response";
import { BackendApiError } from "@/lib/api/errors";
import {
  applyRefreshedStudentSession,
  studentBackendRequest,
} from "@/lib/auth/student-backend-session";
import { setStudentFavoritesCookie } from "@/lib/auth/cookies";
import { learningFavoriteResponseSchema } from "@/lib/contracts/learning";
import { readStudentFavoriteIds } from "@/lib/learning/student-preferences";

const paramsSchema = z.object({
  courseId: z.string().trim().min(1).max(160),
  version: z.string().trim().min(1).max(80),
});

export async function PUT(request: NextRequest, context: { params: Promise<{ courseId: string; version: string }> }) {
  return updateFavorite(request, context, true);
}

export async function DELETE(request: NextRequest, context: { params: Promise<{ courseId: string; version: string }> }) {
  return updateFavorite(request, context, false);
}

async function updateFavorite(
  request: NextRequest,
  context: { params: Promise<{ courseId: string; version: string }> },
  favorite: boolean,
) {
  const parsed = paramsSchema.safeParse(await context.params);
  if (!parsed.success) {
    return NextResponse.json(
      { ok: false, error: "invalid_learning_course", message: "课程地址不正确" },
      { status: 400 },
    );
  }
  const { courseId, version } = parsed.data;
  try {
    try {
      const { refreshed } = await studentBackendRequest(
        request,
        `/api/v2/student/learning/courses/${encodeURIComponent(courseId)}/versions/${encodeURIComponent(version)}/favorite`,
        { method: favorite ? "PUT" : "DELETE", body: JSON.stringify({}) },
      );
      const payload = learningFavoriteResponseSchema.parse({
        ok: true,
        courseId,
        courseVersion: version,
        favorite,
        storage: "backend",
      });
      return applyRefreshedStudentSession(NextResponse.json(payload), refreshed);
    } catch (error) {
      if (!isMissingFavoriteRoute(error)) throw error;
    }

    const course = await loadLearningCourse(request, courseId, version);
    const favoriteIds = readStudentFavoriteIds(request);
    if (favorite) favoriteIds.add(courseId);
    else favoriteIds.delete(courseId);
    const response = NextResponse.json(learningFavoriteResponseSchema.parse({
      ok: true,
      courseId,
      courseVersion: version,
      favorite,
      storage: "web_preference",
    }));
    setStudentFavoritesCookie(response, [...favoriteIds]);
    return applyRefreshedStudentSession(response, course.refreshed);
  } catch (error) {
    return studentRouteError(error, favorite ? "暂时没有收藏成功" : "暂时没有取消收藏");
  }
}

function isMissingFavoriteRoute(error: unknown) {
  return isCompatibilityMiss(error)
    && (!(error instanceof BackendApiError) || error.code !== "learning_course_not_found");
}
