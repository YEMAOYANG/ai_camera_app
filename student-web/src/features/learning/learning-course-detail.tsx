"use client";

import { ArrowRight, Check, Clock3, Heart, LoaderCircle, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { SpaceShell, SpacePageHeading } from "@/components/student/space-shell";
import { SpaceCourseArt } from "@/components/student/space-course-art";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { getLearningCourse, setLearningFavorite } from "@/features/learning/learning-client";
import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";
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
  const [favoritePulse, setFavoritePulse] = useState(0);
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
      if (result.favorite) setFavoritePulse(current => current + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "收藏状态暂时没有保存成功");
    } finally {
      setFavoriteBusy(false);
    }
  }

  if (loading) return <SpaceShell student={student} active="learning"><CourseDetailLoading /></SpaceShell>;
  if (!data) return <SpaceShell student={student} active="learning"><CourseDetailError message={error} onRetry={load} /></SpaceShell>;

  const item = data.item;
  return (
    <SpaceShell student={student} active="learning" className="space-detail-page space-explore-detail">
      <SpacePageHeading title="课程详情" backHref="/learning" backLabel="返回我的学习" />
      <section className="space-detail-hero">
        <SpaceCourseArt subject={item.course.subject} className="space-detail-art" priority />
        <div className="space-detail-copy">
          <p className="space-eyebrow">{item.course.subjectLabel} · {completed ? "已经学完" : "探索下一站"}</p>
          <h2>{item.course.title}</h2>
          <p className="space-detail-intro">{item.course.objective}</p>
          <p className="space-course-meta"><Clock3 className="size-5" aria-hidden="true" />约 {item.course.estimatedMinutes} 分钟</p>
          <div className="space-detail-actions">
            {completed ? (
              <div className="space-detail-status is-complete"><p><Check className="size-5" aria-hidden="true" />这节课学完啦</p><span>{item.report ? "学习结果已保存，可以在下方查看。" : "学习记录已保存，报告准备好后会出现在这里。"}</span></div>
            ) : item.fullClassroomAvailable && item.taskId ? (
              <Button asChild><DocumentLink href={openMaicLessonPath(item.taskId)}>{item.session?.status === "in_progress" ? "继续上课" : "开始上课"}<ArrowRight className="size-5" aria-hidden="true" /></DocumentLink></Button>
            ) : item.fullClassroomAvailable ? (
              <LearningCourseStartButton key={`${item.course.id}:${item.course.version}`} courseId={item.course.id} version={item.course.version} />
            ) : (
              <div className="space-detail-status"><p><Sparkles className="size-5" aria-hidden="true" />完整课堂准备中</p><span>准备好后就能和老师一起开始。</span></div>
            )}
            <button type="button" className={`focus-ring space-detail-favorite ${item.favorite ? "is-active" : ""}`} aria-pressed={item.favorite} onClick={() => void toggleFavorite()} disabled={favoriteBusy}>{favoriteBusy ? <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Heart className={`size-5 ${item.favorite ? "fill-current" : ""}`} aria-hidden="true" />}{item.favorite ? "已收藏" : "收藏课程"}{favoritePulse > 0 && item.favorite ? <span key={favoritePulse} className="space-favorite-burst" aria-hidden="true"><Sparkles /><i /><i /></span> : null}</button>
          </div>
        </div>
      </section>

      <section className="space-detail-outline" aria-labelledby="course-goal-title">
        <div className="space-section-heading"><h2 id="course-goal-title"><Target className="size-6" aria-hidden="true" />学习目标</h2><p>这节课会学什么</p></div>
        <ol className="space-learning-goals space-goal-orbit">
          <li><span className="space-goal-node">01</span><div><h3>发现新知识</h3><p>{item.course.objective}</p></div></li>
          <li><span className="space-goal-node">02</span><div><h3>跟着老师试一试</h3><p>听讲解、看示范，再亲手完成互动练习。</p></div></li>
          <li><span className="space-goal-node">03</span><div><h3>把学会的记住</h3><p>看看自己的学习结果，找到下次进步的方向。</p></div></li>
        </ol>
        <div className="space-detail-facts"><span><Clock3 aria-hidden="true" />{item.course.estimatedMinutes} 分钟</span><span>{item.course.questionCount} 道互动练习</span></div>
        {item.course.intro && item.course.intro !== item.course.objective ? <details className="space-course-introduction"><summary className="focus-ring">课程介绍</summary><p>{item.course.intro}</p></details> : null}
      </section>
      {item.report ? <section className="space-detail-report"><span className="space-result-icon"><Check aria-hidden="true" /></span><div><p className="space-eyebrow">上次学习结果</p><h2>{item.report.summary}</h2><p>{item.report.nextStep}</p></div><strong>{item.report.score}<small>分</small></strong></section> : null}
      {error ? <p className="space-inline-error" role="alert">{error}</p> : null}
    </SpaceShell>
  );
}

function CourseDetailLoading() {
  return <div className="space-page-state" role="status"><LoaderCircle className="animate-spin motion-reduce:animate-none" aria-hidden="true" /><h1>正在打开课程详情</h1></div>;
}

function CourseDetailError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="space-page-state"><Target aria-hidden="true" /><h1>这门课暂时打不开</h1><p>{message}</p><div className="space-inline-actions"><Button onClick={onRetry}>再试一次</Button><Button variant="secondary" asChild><Link href="/learning">返回我的学习</Link></Button></div></div>;
}
