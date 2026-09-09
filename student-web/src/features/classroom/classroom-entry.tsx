"use client";

import { CircleAlert, Clock3, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { ClassroomBooting, ClassroomPlayer } from "@/features/classroom/classroom-player";
import { FullOpenMaicClassroom } from "@/features/classroom/full-openmaic-classroom";
import {
  launchFullOpenMaicRuntime,
  LearningClientError,
  startLearningSession,
} from "@/features/learning/learning-client";
import { StudentLessonExperience } from "@/features/lesson-player/student-lesson-experience";
import type { LearningStartResponse } from "@/lib/contracts/learning";
import type { OpenMaicFormalRuntimeLaunch } from "@/lib/contracts/openmaic-runtime";
import { openMaicLessonPath } from "@/lib/routing/classroom";
import type { Student } from "@/lib/contracts/student-session";

export type ClassroomEntryMode = "discover" | "openmaic";

type RuntimePhase =
  | "checking"
  | "redirecting"
  | "ready"
  | "fallback"
  | "preparing"
  | "error"
  | "start_error";

type ClassroomBootstrapResult = {
  start: LearningStartResponse;
  launch: OpenMaicFormalRuntimeLaunch;
};

type ClassroomBootstrapFailure =
  | { phase: "start"; error: unknown }
  | { phase: "launch"; error: unknown; start: LearningStartResponse };

type ClassroomBootstrapFlight = {
  key: string;
  promise: Promise<ClassroomBootstrapResult>;
};

const runtimePreparingCodes = new Set([
  "openmaic_runtime_preparing",
  "openmaic_runtime_review_pending",
]);

const runtimeCompatibilityFallbackCodes = new Set([
  "openmaic_runtime_disabled",
  "openmaic_runtime_not_available",
]);

function replaceWithRuntimeDocument(path: string) {
  window.location.replace(path);
}

export function ClassroomEntry({
  student,
  taskId,
  mode = "discover",
  startSession = startLearningSession,
  launchRuntime = launchFullOpenMaicRuntime,
  navigateToRuntime = replaceWithRuntimeDocument,
  preparingRetryMs = 10_000,
}: {
  student: Student;
  taskId: string;
  mode?: ClassroomEntryMode;
  startSession?: typeof startLearningSession;
  launchRuntime?: typeof launchFullOpenMaicRuntime;
  navigateToRuntime?: (path: string) => void;
  preparingRetryMs?: number;
}) {
  const [start, setStart] = useState<LearningStartResponse | null>(null);
  const [runtimeLaunch, setRuntimeLaunch] = useState<OpenMaicFormalRuntimeLaunch | null>(null);
  const [runtimePhase, setRuntimePhase] = useState<RuntimePhase>("checking");
  const [message, setMessage] = useState("");
  const [retryRevision, setRetryRevision] = useState(0);
  const bootstrapFlightRef = useRef<ClassroomBootstrapFlight | null>(null);

  const retryRuntime = useCallback(() => {
    bootstrapFlightRef.current = null;
    setStart(null);
    setRuntimeLaunch(null);
    setMessage("");
    setRuntimePhase("checking");
    setRetryRevision((revision) => revision + 1);
  }, []);

  useEffect(() => {
    let active = true;

    const key = `${mode}:${taskId}:${retryRevision}`;
    let flight = bootstrapFlightRef.current;
    if (!flight || flight.key !== key) {
      const promise = (async (): Promise<ClassroomBootstrapResult> => {
        let nextStart: LearningStartResponse;
        try {
          nextStart = await startSession(taskId);
        } catch (error) {
          throw { phase: "start", error } satisfies ClassroomBootstrapFailure;
        }

        try {
          return { start: nextStart, launch: await launchRuntime(nextStart.session.id) };
        } catch (error) {
          throw { phase: "launch", error, start: nextStart } satisfies ClassroomBootstrapFailure;
        }
      })();
      flight = { key, promise };
      bootstrapFlightRef.current = flight;
    }

    void flight.promise.then(({ start: nextStart, launch }) => {
      if (!active) return;
      setStart(nextStart);
      if (mode === "discover") {
        // Permissions-Policy is a top-level document response header. A
        // client-side Next navigation cannot replace it, so discovery must
        // perform a document navigation to the dedicated trusted route.
        setRuntimePhase("redirecting");
        navigateToRuntime(openMaicLessonPath(taskId));
        return;
      }
      setRuntimeLaunch(launch);
      setRuntimePhase("ready");
    }).catch((failure: ClassroomBootstrapFailure) => {
      if (!active) return;
      const caught = failure.error;
      if (failure.phase === "launch") {
        setStart(failure.start);
        const errorMessage = caught instanceof Error
          ? caught.message
          : "完整互动课堂暂时没有连接上";
        if (caught instanceof LearningClientError && runtimePreparingCodes.has(caught.code)) {
          setMessage(errorMessage);
          setRuntimePhase("preparing");
        } else if (mode === "openmaic") {
          setMessage(errorMessage);
          setRuntimePhase("error");
        } else if (
          caught instanceof LearningClientError
          && runtimeCompatibilityFallbackCodes.has(caught.code)
        ) {
          // Only the discovery route may retain compatibility with an
          // already-released Mira package. The dedicated runtime route never
          // reaches this branch and therefore never silently falls back.
          setRuntimePhase("fallback");
        } else {
          setMessage(errorMessage);
          setRuntimePhase("error");
        }
        return;
      }

      const errorMessage = caught instanceof Error ? caught.message : "这节课暂时打不开";
      setMessage(errorMessage);
      if (caught instanceof LearningClientError && caught.code === "learning_classroom_preparing") {
        setRuntimePhase("preparing");
      } else {
        setRuntimePhase(mode === "openmaic" ? "error" : "start_error");
      }
    });

    return () => { active = false; };
  }, [launchRuntime, mode, navigateToRuntime, retryRevision, startSession, taskId]);

  useEffect(() => {
    if (runtimePhase !== "preparing") return;
    const timer = window.setTimeout(retryRuntime, preparingRetryMs);
    return () => window.clearTimeout(timer);
  }, [preparingRetryMs, retryRuntime, runtimePhase]);

  if (runtimePhase === "preparing") return <ClassroomPreparing message={message} onRetry={retryRuntime} />;
  if (runtimePhase === "error") return <OpenMaicRuntimeError message={message} onRetry={retryRuntime} />;
  if (runtimePhase === "checking" || runtimePhase === "redirecting") return <ClassroomBooting />;
  if (!start) {
    return <StudentLessonExperience student={student} taskId={taskId} initialError={message} />;
  }
  if (runtimePhase === "ready" && runtimeLaunch) {
    return <FullOpenMaicClassroom start={start} launch={runtimeLaunch} />;
  }
  if (start.classroom && start.cursor && start.package) {
    return <ClassroomPlayer student={student} start={start} />;
  }
  if (start.classroomRelease?.mode === "package_required" && start.classroomRelease.status !== "ready") {
    return <ClassroomPreparing message="这节课还在完成课件与声音制作，请稍后再来" onRetry={retryRuntime} />;
  }
  return <StudentLessonExperience student={student} taskId={taskId} initialStart={start} />;
}

function ClassroomPreparing({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main id="main-content" className="classroom-preparing-state">
      <div className="classroom-preparing-visual"><MiraBuddy mood="reading" className="w-40" label="Mira 正在制作课程" /><Sparkles className="classroom-preparing-sparkle size-8" /></div>
      <p><Clock3 className="size-5" />课程制作中</p>
      <h1>老师正在把课件和声音准备好</h1>
      <span>{message || "通过内容、语音和课堂运行检查后，这节课就会自动开放。"}</span>
      <div><Button asChild><DocumentLink href="/learning">看看其他课程</DocumentLink></Button><Button variant="secondary" onClick={onRetry}>重新检查</Button></div>
    </main>
  );
}

function OpenMaicRuntimeError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main id="main-content" className="classroom-preparing-state" role="alert">
      <CircleAlert className="size-12 text-[var(--mira-danger)]" aria-hidden="true" />
      <p>完整课堂未就绪</p>
      <h1>完整互动课堂暂时打不开</h1>
      <span>{message || "课堂运行服务暂时不可用。请重新检查；如果仍未恢复，请让家长检查课堂运行、语音服务和麦克风安全域名配置。"}</span>
      <div><Button onClick={onRetry}>重新检查</Button><Button variant="secondary" asChild><DocumentLink href="/learning">返回课程列表</DocumentLink></Button></div>
    </main>
  );
}
