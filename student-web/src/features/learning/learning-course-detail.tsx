"use client";

import { ArrowRight, BookOpen, Check, Clock3, Heart, LoaderCircle, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { getLearningCourse, setLearningFavorite } from "@/features/learning/learning-client";
import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";
import { LearningProgressionNote, learningProgressionCanResume, learningProgressionLocked } from "@/features/learning/learning-progression";
import type { LearningCourseDetailResponse } from "@/lib/contracts/learning";
import { openMaicLessonPath } from "@/lib/routing/classroom";
import type { Student } from "@/lib/contracts/student-session";

export function LearningCourseDetail({
  student,
  courseId,
  version,
  pollIntervalMs = 10_000,
}: {
  student: Student;
  courseId: string;
  version?: string;
  pollIntervalMs?: number;
}) {
  const [data, setData] = useState<LearningCourseDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getLearningCourse(courseId, version));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "课程详情暂时没有加载成功");
    } finally {
      setLoading(false);
    }
  }, [courseId, version]);

  useEffect(() => {
    let active = true;
    getLearningCourse(courseId, version)
      .then((value) => { if (active) setData(value); })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "课程详情暂时没有加载成功");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [courseId, version]);

  const completed = Boolean(data && (
    data.item.report || data.item.session?.status === "completed" || data.item.taskStatus === "completed"
  ));
  const shouldPoll = !loading && !completed && (
    Boolean(error) || !data || !data.item.fullClassroomAvailable
  );

  useEffect(() => {
    if (!shouldPoll) return;
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      let keepPolling = true;
      try {
        const value = await getLearningCourse(courseId, version);
        keepPolling = !value.item.fullClassroomAvailable && !(
          value.item.report || value.item.session?.status === "completed" || value.item.taskStatus === "completed"
        );
        if (active) {
          setData(value);
          setError("");
        }
      } catch {
        // Keep the current detail visible and retry silently on the next tick.
      } finally {
        if (active && keepPolling) {
          timer = window.setTimeout(() => void poll(), pollIntervalMs);
        }
      }
    };
    timer = window.setTimeout(() => void poll(), pollIntervalMs);
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [courseId, pollIntervalMs, shouldPoll, version]);

  async function toggleFavorite() {
    if (!data || favoriteBusy) return;
    setFavoriteBusy(true);
    setError("");
    try {
      const result = await setLearningFavorite(data.item.course.id, data.item.course.version, !data.item.favorite);
      setData({ ...data, item: { ...data.item, favorite: result.favorite } });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "收藏状态暂时没有保存成功");
    } finally {
      setFavoriteBusy(false);
    }
  }

  if (loading) return <SchoolbagShell student={student}><CourseDetailLoading /></SchoolbagShell>;
  if (!data) return <SchoolbagShell student={student}><CourseDetailError message={error} onRetry={load} /></SchoolbagShell>;

  const item = data.item;
  return (
    <SchoolbagShell student={student} className="course-detail">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">课程详情</h1>
        <Button size="compact" variant="quiet" asChild><Link href="/learning">回到书包</Link></Button>
      </div>
      <section className="course-detail-hero">
        <div className="course-detail-copy">
          <p className="course-detail-caption">{item.course.subjectLabel} · {completed ? "已经学完" : "课程介绍"}</p>
          <h2>{item.course.title}</h2>
          <p className="course-detail-intro">{item.course.objective}</p>
          <LearningProgressionNote progression={item.progression} />
          <p className="course-detail-facts"><Clock3 className="size-5" aria-hidden="true" />约 {item.course.estimatedMinutes} 分钟</p>
          <div className="course-detail-actions">
            {completed ? (
              <div className="course-detail-status is-complete"><p><Check className="size-5" aria-hidden="true" />这节课学完啦</p><span>{item.report ? "学习结果已保存，可以在下方查看。" : "学习记录已保存，报告准备好后会出现在这里。"}</span></div>
            ) : learningProgressionLocked(item.progression) && !learningProgressionCanResume(item) ? (
              <LearningCourseStartButton courseId={item.course.id} version={item.course.version} progression={item.progression} />
            ) : item.fullClassroomAvailable && item.taskId ? (
              <Button asChild><DocumentLink href={openMaicLessonPath(item.taskId)}>{item.session?.status === "in_progress" ? "继续上课" : "开始上课"}<ArrowRight className="size-5" aria-hidden="true" /></DocumentLink></Button>
            ) : item.fullClassroomAvailable ? (
              <LearningCourseStartButton key={`${item.course.id}:${item.course.version}`} courseId={item.course.id} version={item.course.version} progression={item.progression} />
            ) : (
              <div className="course-detail-status"><p><Sparkles className="size-5" aria-hidden="true" />完整课堂准备中</p><span>准备好后就能和老师一起开始。</span></div>
            )}
            <Button type="button" variant="secondary" aria-pressed={item.favorite} onClick={() => void toggleFavorite()} disabled={favoriteBusy}>
              {favoriteBusy ? <LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Heart className={item.favorite ? "fill-current" : undefined} aria-hidden="true" />}
              {item.favorite ? "已收藏" : "收藏课程"}
            </Button>
          </div>
        </div>
      </section>

      <section className="course-detail-outline" aria-labelledby="course-goal-title">
        <div className="course-detail-heading"><h2 id="course-goal-title"><Target className="size-6" aria-hidden="true" />学习目标</h2><p>这节课会学什么</p></div>
        <ol className="course-detail-goals">
          <li><span className="course-detail-step">01</span><div><h3>发现新知识</h3><p>{item.course.objective}</p></div></li>
          <li><span className="course-detail-step">02</span><div><h3>跟着老师试一试</h3><p>听讲解、看示范，再亲手完成互动练习。</p></div></li>
          <li><span className="course-detail-step">03</span><div><h3>把学会的记住</h3><p>看看自己的学习结果，找到下次进步的方向。</p></div></li>
        </ol>
        <div className="course-detail-facts"><span><Clock3 aria-hidden="true" />{item.course.estimatedMinutes} 分钟</span><span>{item.course.questionCount} 道互动练习</span></div>
        {item.course.intro && item.course.intro !== item.course.objective ? <details className="course-detail-intro-disclosure"><summary className="focus-ring">课程介绍</summary><p>{item.course.intro}</p></details> : null}
      </section>
      {item.report ? <section className="course-detail-report"><span className="course-detail-result-icon"><Check aria-hidden="true" /></span><div><p className="course-detail-caption">上次学习结果</p><h2>{item.report.summary}</h2><p>{item.report.nextStep}</p></div><strong>{item.report.score}<small>分</small></strong></section> : null}
      {error ? <p className="course-action-error" role="alert">{error}</p> : null}
    </SchoolbagShell>
  );
}

function CourseDetailLoading() {
  return <div className="course-detail-state" role="status"><LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" /><h1>正在打开课程详情</h1></div>;
}

function CourseDetailError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="course-detail-state"><BookOpen aria-hidden="true" /><h1>这门课暂时打不开</h1><p>{message}</p><div className="course-detail-actions"><Button onClick={onRetry}>再试一次</Button><Button variant="secondary" asChild><Link href="/learning">回到书包</Link></Button></div></div>;
}
