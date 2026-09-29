"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { studentMeResponseSchema, type Student } from "@/lib/contracts/student-session";
import { ClassroomEntry } from "@/features/classroom/classroom-entry";
import { LearningCourseDetail } from "@/features/learning/learning-course-detail";
import { LearningTextbooks } from "@/features/learning/learning-textbooks";
import { LearningTextbookClassroom } from "@/features/learning/learning-textbook-classroom";
import { LearningSchoolbag } from "@/features/learning/learning-schoolbag";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import type { TextbookLocation } from "@/features/learning/textbook-navigation";

export function StudentSessionGate({
  lessonTaskId,
  classroomMode = "discover",
  learningView,
  courseId,
  courseVersion,
  textbookLocation,
  textbookCourseKey,
}: {
  lessonTaskId?: string;
  classroomMode?: "discover" | "openmaic";
  learningView?: "library" | "course" | "practice" | "path" | "textbooks" | "schoolbag";
  courseId?: string;
  courseVersion?: string;
  textbookLocation?: TextbookLocation;
  textbookCourseKey?: string;
}) {
  const router = useRouter();
  const [student, setStudent] = useState<Student | null>(null);
  const [error, setError] = useState("");

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
  }, [router]);

  if (!lessonTaskId && (error || !student)) {
    return (
      <SchoolbagShell
        className="space-session-shell"
      >
        <section className="space-session-state" role={error ? "alert" : "status"}>
          <p className="space-eyebrow">暖瞳 · 学习空间</p>
          <h1>{error ? "暂时没有连接上" : "正在打开学习空间"}</h1>
          {error ? (
            <>
              <p className="space-session-message">{error}</p>
              <Button className="space-session-retry" onClick={() => location.reload()}>再试一次</Button>
            </>
          ) : (
            <>
              <p className="space-session-message">马上就好。</p>
              <div className="space-session-progress" aria-hidden="true"><i /></div>
              <div className="space-session-skeleton" aria-hidden="true"><span /><span /></div>
            </>
          )}
        </section>
      </SchoolbagShell>
    );
  }

  if (error) {
    return (
      <main id="main-content" className="grid min-h-screen place-items-center px-5">
        <div className="max-w-md rounded-[24px] bg-[var(--mira-surface)] p-7 text-center shadow-[var(--mira-shadow-card)]">
          <h1 className="text-2xl font-black">暂时没有连接上</h1>
          <p className="mt-3 leading-7 text-[var(--mira-muted)]">{error}</p>
          <button className="focus-ring mt-6 h-12 rounded-[15px] bg-[var(--mira-brand-deep)] px-6 font-bold text-[var(--mira-on-brand)]" onClick={() => location.reload()}>
            再试一次
          </button>
        </div>
      </main>
    );
  }

  if (!student) {
    return (
      <main id="main-content" className="grid min-h-screen place-items-center" aria-live="polite">
        <div className="flex items-center gap-3 rounded-full bg-[var(--mira-surface)] px-5 py-3 font-bold text-[var(--mira-muted)] shadow-sm">
          <LoaderCircle className="size-5 animate-spin text-[var(--mira-brand)]" aria-hidden="true" />
          正在打开学习空间
        </div>
      </main>
    );
  }

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
