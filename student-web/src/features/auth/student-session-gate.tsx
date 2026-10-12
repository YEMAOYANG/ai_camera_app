"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { studentMeResponseSchema, type Student } from "@/lib/contracts/student-session";
import { ClassroomEntry } from "@/features/classroom/classroom-entry";
import { LearningCourseDetail } from "@/features/learning/learning-course-detail";
import { LearningTextbooks } from "@/features/learning/learning-textbooks";
import { LearningTextbookClassroom } from "@/features/learning/learning-textbook-classroom";
import { LearningSchoolbag } from "@/features/learning/learning-schoolbag";
import { LearningReviews } from "@/features/learning/learning-reviews";
import { LearningHomework } from "@/features/learning/learning-homework";
import { LearningInternationalTrials } from "@/features/learning/learning-international-trials";
import { StudentSessionState } from "./student-session-state";
import type { TextbookLocation } from "@/features/learning/textbook-navigation";

export function StudentSessionGate({
  lessonTaskId,
  classroomMode = "discover",
  learningView,
  courseId,
  courseVersion,
  textbookLocation,
  textbookCourseKey,
  reviewId,
  submissionId,
}: {
  lessonTaskId?: string;
  classroomMode?: "discover" | "openmaic";
  learningView?: "library" | "course" | "practice" | "path" | "textbooks" | "schoolbag" | "reviews" | "homework" | "international";
  courseId?: string;
  courseVersion?: string;
  textbookLocation?: TextbookLocation;
  textbookCourseKey?: string;
  reviewId?: string;
  submissionId?: string;
}) {
  const router = useRouter();
  const [student, setStudent] = useState<Student | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch("/api/auth/me", { signal: controller.signal });
        const payload: unknown = await response.json();
        if (!response.ok) {
          const state = payload as { canUnlock?: boolean; message?: string };
          if (response.status === 401) {
            router.replace(state.canUnlock ? "/unlock" : "/pair");
            return;
          }
          throw new Error(state.message || "暂时无法读取学习身份，请稍后再试");
        }
        const nextStudent = studentMeResponseSchema.parse(payload).student;
        setStudent(nextStudent);
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(caught instanceof Error ? caught.message : "暂时无法读取学习身份");
      }
    }
    void load();
    return () => controller.abort();
  }, [router, attempt]);

  if (error || !student) return <StudentSessionState error={error} onRetry={() => {
    setError("");
    setAttempt(value => value + 1);
  }} />;

  if (learningView === "reviews") return <LearningReviews student={student} reviewId={reviewId} />;
  if (learningView === "homework") return <LearningHomework student={student} submissionId={submissionId} />;
  if (learningView === "international") return <LearningInternationalTrials student={student} />;
  if (textbookCourseKey) return <LearningTextbookClassroom key={textbookCourseKey} student={student} contentKey={textbookCourseKey} />;
  if (lessonTaskId) {
    return <ClassroomEntry key={`${classroomMode}:${lessonTaskId}`} student={student} taskId={lessonTaskId} mode={classroomMode} />;
  }
  if (learningView === "course" && courseId) {
    return <LearningCourseDetail student={student} courseId={courseId} version={courseVersion} />;
  }
  if (learningView === "textbooks") return <LearningTextbooks student={student} location={textbookLocation} />;
  return <LearningSchoolbag student={student} />;
}
