"use client";

import { ArrowRight, LoaderCircle } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { startLearningCourse } from "@/features/learning/learning-client";
import { openMaicLessonPath } from "@/lib/routing/classroom";

function navigateToDocument(path: string) {
  // Classroom response headers must be loaded by a full document navigation.
  window.location.assign(path);
}

export function LearningCourseStartButton({ courseId, version, label = "开始上课", navigate = navigateToDocument }: {
  courseId: string;
  version: string;
  label?: string;
  navigate?: (path: string) => void;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const errorId = useId();
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function start() {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(true);
    setError("");
    try {
      const result = await startLearningCourse(courseId, version);
      if (mounted.current) navigate(openMaicLessonPath(result.taskId));
    } catch (caught) {
      if (!mounted.current) return;
      if (caught instanceof Error && "status" in caught && caught.status === 401) {
        navigate("/unlock");
        return;
      }
      const code = caught instanceof Error && "code" in caught ? caught.code : undefined;
      setError(code === "learning_classroom_release_changed"
        ? "这节课刚刚更新，请刷新后再试。"
        : code === "learning_course_not_found"
          ? "这节课暂时不能开始，请刷新课程后再试。"
          : caught instanceof Error ? caught.message : "暂时无法进入这节课，请再试一次");
      inFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="flex min-w-0 flex-col items-start gap-2">
      <Button type="button" onClick={() => void start()} disabled={pending} aria-busy={pending} aria-describedby={error ? errorId : undefined}>
        {pending ? "正在进入…" : label}
        {pending ? <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <ArrowRight className="size-5" aria-hidden="true" />}
      </Button>
      {error ? <p id={errorId} className="space-inline-error text-sm" role="alert">{error}</p> : null}
    </div>
  );
}
