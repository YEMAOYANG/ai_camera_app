"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { studentMeResponseSchema, type Student } from "@/lib/contracts/student-session";
import { StudentDashboard } from "@/features/today/student-dashboard";
import { ClassroomEntry } from "@/features/classroom/classroom-entry";
import { LearningCourseDetail } from "@/features/learning/learning-course-detail";
import { LearningLibrary } from "@/features/learning/learning-library";

export function StudentSessionGate({
  lessonTaskId,
  classroomMode = "discover",
  learningView,
  courseId,
  courseVersion,
}: {
  lessonTaskId?: string;
  classroomMode?: "discover" | "openmaic";
  learningView?: "library" | "course";
  courseId?: string;
  courseVersion?: string;
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
        setStudent(studentMeResponseSchema.parse(payload).student);
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(caught instanceof Error ? caught.message : "暂时无法读取学习身份");
      }
    }
    void load();
    return () => controller.abort();
  }, [router]);

  if (error) {
    return (
      <main id="main-content" className="grid min-h-screen place-items-center px-5">
        <div className="max-w-md rounded-[24px] bg-white p-7 text-center shadow-[var(--mira-shadow-card)]">
          <h1 className="text-2xl font-black">暂时没有连接上</h1>
          <p className="mt-3 leading-7 text-[var(--mira-muted)]">{error}</p>
          <button className="focus-ring mt-6 h-12 rounded-[15px] bg-[var(--mira-brand-deep)] px-6 font-bold text-white" onClick={() => location.reload()}>
            再试一次
          </button>
        </div>
      </main>
    );
  }

  if (!student) {
    return (
      <main id="main-content" className="grid min-h-screen place-items-center" aria-live="polite">
        <div className="flex items-center gap-3 rounded-full bg-white/80 px-5 py-3 font-bold text-[var(--mira-muted)] shadow-sm">
          <LoaderCircle className="size-5 animate-spin text-[var(--mira-brand)]" aria-hidden="true" />
          正在打开学习空间
        </div>
      </main>
    );
  }

  if (lessonTaskId) {
    return <ClassroomEntry key={`${classroomMode}:${lessonTaskId}`} student={student} taskId={lessonTaskId} mode={classroomMode} />;
  }
  if (learningView === "course" && courseId) {
    return <LearningCourseDetail student={student} courseId={courseId} version={courseVersion} />;
  }
  if (learningView === "library") return <LearningLibrary student={student} />;
  return <StudentDashboard student={student} />;
}
