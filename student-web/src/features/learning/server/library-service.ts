import "server-only";

import type { NextRequest } from "next/server";

import { studentBackendRequest } from "@/lib/auth/student-backend-session";
import {
  learningCourseDetailResponseSchema,
  learningLibraryResponseSchema,
  type LearningCourseDetailResponse,
  type LearningLibraryBucket,
  type LearningLibraryResponse,
  type LearningSubject,
} from "@/lib/contracts/learning";
import type { StudentAuthResponse } from "@/lib/contracts/student-session";

type LibraryServiceResult<T> = {
  data: T;
  refreshed?: StudentAuthResponse;
};

export function isCompatibilityMiss(error: unknown): error is { status: number } {
  return typeof error === "object"
    && error !== null
    && "status" in error
    && (error.status === 404 || error.status === 501);
}

export type LearningLibraryQuery = {
  bucket: LearningLibraryBucket;
  subject?: LearningSubject;
  cursor?: string;
  limit: number;
};

export async function loadLearningLibrary(
  request: NextRequest,
  query: LearningLibraryQuery,
): Promise<LibraryServiceResult<LearningLibraryResponse>> {
  const search = new URLSearchParams({ bucket: query.bucket, limit: String(query.limit) });
  if (query.subject) search.set("subject", query.subject);
  if (query.cursor) search.set("cursor", query.cursor);
  const { payload, refreshed } = await studentBackendRequest(
    request,
    `/api/v2/student/learning/library?${search.toString()}`,
  );
  return { data: learningLibraryResponseSchema.parse(payload), refreshed };
}

export async function loadLearningCourse(
  request: NextRequest,
  courseId: string,
  version?: string,
): Promise<LibraryServiceResult<LearningCourseDetailResponse>> {
  const search = version ? `?version=${encodeURIComponent(version)}` : "";
  const { payload, refreshed } = await studentBackendRequest(
    request,
    `/api/v2/student/learning/courses/${encodeURIComponent(courseId)}${search}`,
  );
  return { data: learningCourseDetailResponseSchema.parse(payload), refreshed };
}
