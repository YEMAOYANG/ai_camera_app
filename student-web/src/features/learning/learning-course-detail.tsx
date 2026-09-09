"use client";

import { ArrowLeft, ArrowRight, BookOpenCheck, Check, Clock3, Heart, LoaderCircle, Sparkles, Target } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { MiraMark } from "@/components/student/mira-mark";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { getLearningCourse, setLearningFavorite } from "@/features/learning/learning-client";
import { subjectPresentation } from "@/features/learning/learning-presenters";
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

  if (loading) return <CourseDetailLoading />;
  if (!data) return <CourseDetailError message={error} onRetry={load} />;

  const item = data.item;
  const presentation = subjectPresentation(item.course.subject);
  const Icon = presentation.icon;
  return (
    <div className="learning-space learning-detail-space mira-doodle-grid">
      <header className="learning-topbar">
        <Link href="/today" className="focus-ring"><MiraMark compact /></Link>
        <nav aria-label="学生学习导航"><Link href="/today">今日学习</Link><Link href="/learning" aria-current="page">我的学习</Link></nav>
        <span className="learning-detail-student">{student.displayName}的课程</span>
      </header>
      <main id="main-content" className="learning-detail-main">
        <Link href="/learning" className="focus-ring learning-detail-back"><ArrowLeft className="size-5" />返回我的学习</Link>
        <section className="learning-detail-hero">
          <div className="learning-detail-copy">
            <p className={presentation.strong}><Icon className="size-5" />{item.course.subjectLabel} · {item.course.estimatedMinutes} 分钟</p>
            <h1>{item.course.title}</h1>
            <p>{item.course.intro || item.course.objective}</p>
            <div className="learning-detail-actions">
              {completed ? (
                <span className="learning-detail-preparing"><Check className="size-5" />这节课学完啦<span>{item.report ? "学习结果已保存，可以在下方查看。" : "学习记录已保存，报告准备好后会出现在这里。"}</span></span>
              ) : item.fullClassroomAvailable && item.taskId ? (
                <Button asChild><DocumentLink href={openMaicLessonPath(item.taskId)}>{item.session?.status === "in_progress" ? "继续上课" : "开始上课"}<ArrowRight className="size-5" /></DocumentLink></Button>
              ) : (
                <span className="learning-detail-preparing"><Sparkles className="size-5" />完整课堂准备中<span>课件、声音和互动检查全部通过后就能开始</span></span>
              )}
              <button type="button" className={`focus-ring learning-detail-favorite ${item.favorite ? "is-active" : ""}`} onClick={() => void toggleFavorite()} disabled={favoriteBusy}>{favoriteBusy ? <LoaderCircle className="size-5 animate-spin" /> : <Heart className={`size-5 ${item.favorite ? "fill-current" : ""}`} />}{item.favorite ? "已收藏" : "收藏课程"}</button>
            </div>
          </div>
          <div className={`learning-detail-visual ${presentation.surface}`}><MiraBuddy mood={completed ? "celebrate" : "reading"} className="w-44" /><span>{completed ? <><Check className="size-5" />已经学完</> : <><BookOpenCheck className="size-5" />先讲再练</>}</span></div>
        </section>

        <div className="learning-detail-grid is-single">
          <section className="learning-detail-outline" aria-labelledby="course-goal-title">
            <p>这节课会学什么</p>
            <h2 id="course-goal-title"><Target className="size-6" />学习目标</h2>
            <div className="learning-goal-line"><span>01</span><p>{item.course.objective}</p></div>
            <div className="learning-goal-line"><span>02</span><p>跟着老师听讲、看示范，再进入互动练习。</p></div>
            <div className="learning-goal-line"><span>03</span><p>学习结果由服务端课程规则判断，网页不保存答案。</p></div>
            <dl><div><dt>课程版本</dt><dd>{item.course.version}</dd></div><div><dt>题目数量</dt><dd>{item.course.questionCount} 道</dd></div><div><dt>预计时间</dt><dd><Clock3 className="size-4" />{item.course.estimatedMinutes} 分钟</dd></div></dl>
          </section>
        </div>

        {item.report ? <section className="learning-detail-report"><Check className="size-6" /><div><p>上次学习结果</p><h2>{item.report.summary}</h2><span>{item.report.nextStep}</span></div><strong>{item.report.score}<small>分</small></strong></section> : null}
        {error ? <p className="learning-inline-error" role="alert">{error}</p> : null}
      </main>
    </div>
  );
}

function CourseDetailLoading() {
  return <main id="main-content" className="learning-detail-loading" aria-live="polite"><LoaderCircle className="size-6 animate-spin" />正在打开课程详情</main>;
}

function CourseDetailError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <main id="main-content" className="learning-detail-error"><MiraBuddy mood="thinking" className="w-28" /><h1>这门课暂时打不开</h1><p>{message}</p><div><Button onClick={onRetry}>再试一次</Button><Button variant="secondary" asChild><Link href="/learning">返回我的学习</Link></Button></div></main>;
}
