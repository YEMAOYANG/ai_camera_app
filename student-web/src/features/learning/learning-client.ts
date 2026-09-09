import {
  learningAnswerResponseSchema,
  learningCourseDetailResponseSchema,
  learningFavoriteResponseSchema,
  learningLibraryResponseSchema,
  learningReportSchema,
  learningStartResponseSchema,
  learningTeacherPreferenceResponseSchema,
  learningTeachersResponseSchema,
  learningTodayResponseSchema,
  type LearningAnswerResponse,
  type LearningLibraryBucket,
  type LearningSubject,
  type LearningTodayResponse,
} from "@/lib/contracts/learning";
import {
  classroomRuntimeResponseSchema,
  type ClassroomRuntimeResponse,
} from "@/lib/contracts/lesson-package";
import {
  openMaicFormalRuntimeLaunchSchema,
  type OpenMaicFormalRuntimeLaunch,
} from "@/lib/contracts/openmaic-runtime";

type ApiErrorPayload = { error?: string; message?: string };

export class LearningClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "LearningClientError";
  }
}

export async function getTodayLearning(): Promise<LearningTodayResponse> {
  return learningTodayResponseSchema.parse(await requestJson("/api/learning/today"));
}

export async function assignTodayLearning(): Promise<LearningTodayResponse> {
  return learningTodayResponseSchema.parse(
    await requestJson("/api/learning/today/assign", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  );
}

export async function getLearningLibrary(options: {
  bucket: LearningLibraryBucket;
  subject?: LearningSubject;
  cursor?: string;
  limit?: number;
}) {
  const search = new URLSearchParams({
    bucket: options.bucket,
    limit: String(options.limit || 20),
  });
  if (options.subject) search.set("subject", options.subject);
  if (options.cursor) search.set("cursor", options.cursor);
  return learningLibraryResponseSchema.parse(
    await requestJson(`/api/learning/library?${search.toString()}`),
  );
}

export async function getLearningCourse(courseId: string, version?: string) {
  const search = version ? `?version=${encodeURIComponent(version)}` : "";
  return learningCourseDetailResponseSchema.parse(
    await requestJson(`/api/learning/courses/${encodeURIComponent(courseId)}${search}`),
  );
}

export async function setLearningFavorite(courseId: string, version: string, favorite: boolean) {
  return learningFavoriteResponseSchema.parse(
    await requestJson(
      `/api/learning/courses/${encodeURIComponent(courseId)}/versions/${encodeURIComponent(version)}/favorite`,
      { method: favorite ? "PUT" : "DELETE", body: JSON.stringify({}) },
    ),
  );
}

export async function getLearningTeachers(subject?: LearningSubject) {
  const search = subject ? `?subject=${encodeURIComponent(subject)}` : "";
  return learningTeachersResponseSchema.parse(await requestJson(`/api/learning/teachers${search}`));
}

export async function setLearningTeacher(
  subject: LearningSubject,
  teacherProfileId: string,
  teacherProfileVersion: number,
) {
  return learningTeacherPreferenceResponseSchema.parse(
    await requestJson("/api/learning/teachers", {
      method: "PUT",
      body: JSON.stringify({ subject, teacherProfileId, teacherProfileVersion }),
    }),
  );
}

export async function startLearningSession(taskId: string) {
  return learningStartResponseSchema.parse(
    await requestJson("/api/learning/sessions", {
      method: "POST",
      body: JSON.stringify({ taskId }),
    }),
  );
}

export async function launchFullOpenMaicRuntime(
  sessionId: string,
): Promise<OpenMaicFormalRuntimeLaunch> {
  const parsed = openMaicFormalRuntimeLaunchSchema.safeParse(
    await requestJson(
      `/api/learning/sessions/${encodeURIComponent(sessionId)}/openmaic-launch`,
      { method: "POST", body: JSON.stringify({}) },
    ),
  );
  if (!parsed.success) {
    throw new LearningClientError(
      502,
      "openmaic_runtime_contract_invalid",
      "课堂暂时无法打开，请稍后重试；若仍无法打开，请联系管理员。",
    );
  }
  return parsed.data;
}

export async function submitLearningAnswer(
  sessionId: string,
  body: { answer?: string | string[]; response?: unknown },
): Promise<LearningAnswerResponse> {
  return learningAnswerResponseSchema.parse(
    await requestJson(`/api/learning/sessions/${encodeURIComponent(sessionId)}/answer`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  );
}

export async function getLatestLearningReport(subject: string) {
  const payload = await requestJson(`/api/learning/reports/latest?subject=${encodeURIComponent(subject)}`);
  const report = (payload as { report?: unknown }).report;
  return report == null ? null : learningReportSchema.parse(report);
}

export async function getClassroomRuntime(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ClassroomRuntimeResponse> {
  return classroomRuntimeResponseSchema.parse(
    await requestJson(`/api/learning/sessions/${encodeURIComponent(sessionId)}/runtime`, { signal }),
  );
}

export async function completeClassroomAction(
  sessionId: string,
  actionId: string,
  body: { cursorRevision: number; idempotencyKey: string; result?: Record<string, unknown> },
  signal?: AbortSignal,
): Promise<ClassroomRuntimeResponse> {
  return classroomRuntimeResponseSchema.parse(
    await requestJson(
      `/api/learning/sessions/${encodeURIComponent(sessionId)}/actions/${encodeURIComponent(actionId)}/complete`,
      { method: "POST", body: JSON.stringify(body), signal },
    ),
  );
}

async function requestJson(path: string, init: RequestInit = {}) {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    const apiError = payload as ApiErrorPayload;
    throw new LearningClientError(
      response.status,
      apiError.error || "student_learning_failed",
      apiError.message || "学习服务暂时不可用，请稍后再试",
    );
  }
  return payload;
}
