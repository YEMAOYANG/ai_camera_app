"use client";

import {
  ArrowRight,
  BookMarked,
  CheckCircle2,
  Clock3,
  Heart,
  LoaderCircle,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";

import { SpaceShell, SpacePageHeading } from "@/components/student/space-shell";
import { SpaceCourseArt } from "@/components/student/space-course-art";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";
import {
  getLearningLibrary,
  setLearningFavorite,
} from "@/features/learning/learning-client";
import type {
  LearningLibraryBucket,
  LearningLibraryItem,
  LearningLibraryResponse,
  LearningSubject,
} from "@/lib/contracts/learning";
import { openMaicLessonPath } from "@/lib/routing/classroom";
import type { Student } from "@/lib/contracts/student-session";

const buckets: Array<{ id: LearningLibraryBucket; label: string }> = [
  { id: "all", label: "全部课程" },
  { id: "continue", label: "继续学习" },
  { id: "makeup", label: "待补课" },
  { id: "completed", label: "已经学完" },
  { id: "favorites", label: "我的收藏" },
];

const subjects: Array<{ id?: LearningSubject; label: string }> = [
  { label: "全部学科" },
  { id: "chinese", label: "语文" },
  { id: "math", label: "数学" },
  { id: "english", label: "英语" },
];

export function LearningLibrary({
  student,
  pollIntervalMs = 10_000,
}: {
  student: Student;
  pollIntervalMs?: number;
}) {
  const filterId = useId();
  const reducedMotion = useReducedMotion();
  const [bucket, setBucket] = useState<LearningLibraryBucket>("all");
  const [subject, setSubject] = useState<LearningSubject | undefined>();
  const [data, setData] = useState<LearningLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [favoriteBusy, setFavoriteBusy] = useState("");
  const [favoritePulse, setFavoritePulse] = useState<{ courseId: string; sequence: number } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await getLearningLibrary({ bucket, subject }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "我的课程暂时没有加载成功");
    } finally {
      setLoading(false);
    }
  }, [bucket, subject]);

  useEffect(() => {
    let active = true;
    getLearningLibrary({ bucket, subject })
      .then((value) => { if (active) setData(value); })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "我的课程暂时没有加载成功");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [bucket, subject]);

  const hasPreparingClassroom = libraryHasPreparingClassroom(data);
  const shouldPoll = !loading && (Boolean(error) || !data || hasPreparingClassroom);

  useEffect(() => {
    if (!shouldPoll) return;
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      let keepPolling = true;
      try {
        const value = await getLearningLibrary({ bucket, subject });
        keepPolling = libraryHasPreparingClassroom(value);
        if (active) {
          setData(value);
          setError("");
        }
      } catch {
        // Keep the current screen stable and retry silently on the next tick.
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
  }, [bucket, pollIntervalMs, shouldPoll, subject]);

  useEffect(() => {
    let active = true;
    let pending = false;
    const refreshVisibleLibrary = () => {
      if (document.hidden || pending) return;
      pending = true;
      void getLearningLibrary({ bucket, subject })
        .then((value) => { if (active) { setData(value); setError(""); } })
        .catch(() => undefined)
        .finally(() => { pending = false; });
    };
    window.addEventListener("focus", refreshVisibleLibrary);
    document.addEventListener("visibilitychange", refreshVisibleLibrary);
    return () => {
      active = false;
      window.removeEventListener("focus", refreshVisibleLibrary);
      document.removeEventListener("visibilitychange", refreshVisibleLibrary);
    };
  }, [bucket, subject]);

  async function toggleFavorite(item: LearningLibraryItem) {
    if (favoriteBusy) return;
    setFavoriteBusy(item.course.id);
    setError("");
    try {
      const result = await setLearningFavorite(item.course.id, item.course.version, !item.favorite);
      if (result.favorite) setFavoritePulse(current => ({ courseId: item.course.id, sequence: (current?.sequence ?? 0) + 1 }));
      setData((current) => current ? {
        ...current,
        continueItem: current.continueItem?.course.id === item.course.id
          ? { ...current.continueItem, favorite: result.favorite }
          : current.continueItem,
        items: bucket === "favorites" && !result.favorite
          ? current.items.filter((candidate) => candidate.course.id !== item.course.id)
          : current.items.map((candidate) => candidate.course.id === item.course.id
            ? { ...candidate, favorite: result.favorite }
            : candidate),
      } : current);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "收藏状态暂时没有保存成功");
    } finally {
      setFavoriteBusy("");
    }
  }

  const continuation = data?.continueItem;
  const visibleItems = data?.items || [];

  return (
    <SpaceShell student={student} active="learning" className="space-library-page space-explore-library">
      <SpacePageHeading title="我的学习">
        <Button asChild variant="secondary"><Link href="/learning/practice">学过的内容，练一练<ArrowRight className="size-5" aria-hidden="true" /></Link></Button>
      </SpacePageHeading>

      {continuation ? (
        <ContinueLesson item={continuation} onFavorite={() => void toggleFavorite(continuation)} favoriteBusy={favoriteBusy === continuation.course.id} favoritePulse={favoritePulse?.courseId === continuation.course.id ? favoritePulse.sequence : 0} />
      ) : null}

      <section className="space-library-section" aria-labelledby="course-list-title">
        <div className="space-section-heading">
          <h2 id="course-list-title">选择一节想学的课</h2>
          {data ? <p>
            {(data.learningState?.availabilityStatus ?? data.courseSupply?.availabilityStatus) === "empty"
              ? "课程准备好后就会出现在这里"
              : data.catalogStatus === "preparing"
                ? `已有 ${data.availableCourseCount} 门可用，新课完成一门就会自动加入`
                : data.catalogStatus === "failed"
                  ? `本轮更新未全部完成，现有 ${data.availableCourseCount} 门仍可学习`
                  : `共 ${data.availableCourseCount} 门课程`}
          </p> : null}
        </div>
        <div className="space-filter-tabs space-segmented" role="group" aria-label="课程状态筛选">
          {buckets.map((item) => (
            <button key={item.id} type="button" className={`focus-ring space-segment ${bucket === item.id ? "is-active" : ""}`} aria-pressed={bucket === item.id} onClick={() => { if (bucket === item.id) return; setLoading(true); setError(""); setBucket(item.id); }}>
              {bucket === item.id ? <motion.span className="space-segment-indicator" layoutId={`${filterId}-course-state`} transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 440, damping: 38 }} aria-hidden="true" /> : null}
              <span className="space-segment-label">{item.label}</span>
            </button>
          ))}
        </div>
        <div className="space-subject-tabs space-subject-chips" role="group" aria-label="学科筛选">
          {subjects.map((item) => (
            <button key={item.id || "all"} type="button" data-subject={item.id || "all"} className={`focus-ring ${subject === item.id ? "is-active" : ""}`} aria-pressed={subject === item.id} onClick={() => { if (subject === item.id) return; setLoading(true); setError(""); setSubject(item.id); }}>
              <span className="space-subject-chip-dot" aria-hidden="true" /><span>{item.label}</span>
            </button>
          ))}
        </div>
        {loading ? <LearningListLoading /> : null}
        {!loading && error ? <LearningLibraryError message={error} onRetry={load} /> : null}
        {!loading && !error && visibleItems.length ? (
          <div className="space-course-grid">
            {visibleItems.map((item) => <CourseRow key={`${item.taskId || item.course.id}:${item.course.version}`} item={item} makeup={bucket === "makeup"} favoriteBusy={favoriteBusy === item.course.id} favoritePulse={favoritePulse?.courseId === item.course.id ? favoritePulse.sequence : 0} onFavorite={() => void toggleFavorite(item)} />)}
          </div>
        ) : null}
        {!loading && !error && !visibleItems.length ? <LearningEmpty bucket={bucket} catalogStatus={data?.catalogStatus} availability={data?.learningState?.availabilityStatus ?? data?.courseSupply?.availabilityStatus} /> : null}
      </section>
    </SpaceShell>
  );
}

function libraryHasPreparingClassroom(data: LearningLibraryResponse | null) {
  if (!data || data.catalogStatus === "failed") return false;
  const state = data.learningState;
  const availability = state?.availabilityStatus ?? data.courseSupply?.availabilityStatus;
  if (availability && ["paused", "empty", "not_open", "scope_completed"].includes(availability)) return false;
  if ((state?.availableCourseCount ?? data.availableCourseCount) > 0
    || [data.continueItem, ...data.items].some((item) => item?.fullClassroomAvailable)) return false;
  return state?.availabilityStatus === "preparing" || data.catalogStatus === "preparing"
    || [data.continueItem, ...data.items].some((item) => item && !item.fullClassroomAvailable);
}

function ContinueLesson({ item, onFavorite, favoriteBusy, favoritePulse }: { item: LearningLibraryItem; onFavorite: () => void; favoriteBusy: boolean; favoritePulse: number }) {
  const progress = courseProgress(item);
  return (
    <section className="space-continue space-explore-launch" aria-labelledby="continue-title">
      <SpaceCourseArt subject={item.course.subject} className="space-continue-art" />
      <div className="space-continue-content">
        <p className="space-eyebrow"><RotateCcw className="size-5" aria-hidden="true" />{item.course.subjectLabel} · 上次学到这里</p>
        <h2 id="continue-title">{item.course.title}</h2>
        <p className="space-continue-objective">{item.course.objective}</p>
        <div className="space-progress" role="progressbar" aria-label="课程学习进度" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div>
        <p className="space-progress-caption">已完成 {progress}%</p>
        <div className="space-inline-actions"><CourseAction item={item} label="继续上课" /><FavoriteButton item={item} busy={favoriteBusy} pulse={favoritePulse} onClick={onFavorite} /></div>
      </div>
    </section>
  );
}

function CourseRow({ item, makeup, onFavorite, favoriteBusy, favoritePulse }: { item: LearningLibraryItem; makeup: boolean; onFavorite: () => void; favoriteBusy: boolean; favoritePulse: number }) {
  const status = courseStatus(item, makeup);
  return (
    <article className={`space-library-course is-${status.kind}`}>
      <div className="space-course-cover space-explore-cover">
        <SpaceCourseArt subject={item.course.subject} className="space-course-cover-art" />
        <div className="space-course-cover-label"><span>{item.course.subjectLabel}</span><span className={`space-course-status is-${status.kind}`}>{status.kind === "completed" ? <CheckCircle2 aria-hidden="true" /> : <span className="space-status-dot" />}{status.label}</span></div>
        <FavoriteButton item={item} busy={favoriteBusy} pulse={favoritePulse} onClick={onFavorite} />
      </div>
      <div className="space-course-info">
        <h3><Link className="focus-ring" href={`/learning/${encodeURIComponent(item.course.id)}?version=${encodeURIComponent(item.course.version)}`}>{item.course.title}</Link></h3>
        <p>{item.course.objective}</p>
        <div className="space-course-meta"><Clock3 className="size-5" aria-hidden="true" />约 {item.course.estimatedMinutes} 分钟{item.scheduledStart ? ` · ${item.scheduledStart}` : ""}</div>
        {status.kind !== "completed" ? <span className="space-course-readiness">{item.fullClassroomAvailable ? "完整互动课堂已就绪" : "完整课堂准备中"}</span> : null}
        <div className="space-course-footer">{status.kind === "completed" ? <span className="space-complete-mark"><CheckCircle2 className="size-5" aria-hidden="true" />学完啦</span> : <CourseAction item={item} label={status.kind === "makeup" ? "补上这节课" : undefined} />}</div>
      </div>
    </article>
  );
}

function CourseAction({ item, label }: { item: LearningLibraryItem; label?: string }) {
  if (!item.fullClassroomAvailable) {
    return <span className="space-making-action"><Sparkles className="size-4" />完整课堂准备中</span>;
  }
  if (!item.taskId) {
    return <LearningCourseStartButton courseId={item.course.id} version={item.course.version} label={label} />;
  }
  return <Button asChild><DocumentLink href={openMaicLessonPath(item.taskId)}>{label || "开始上课"}<ArrowRight className="size-5" /></DocumentLink></Button>;
}

function FavoriteButton({ item, busy, onClick, pulse }: { item: LearningLibraryItem; busy: boolean; onClick: () => void; pulse: number }) {
  return (
    <button type="button" className={`focus-ring space-favorite ${item.favorite ? "is-active" : ""}`} onClick={onClick} disabled={busy} aria-pressed={item.favorite} aria-label={item.favorite ? `取消收藏${item.course.title}` : `收藏${item.course.title}`}>
      {busy ? <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" /> : <Heart className={`size-5 ${item.favorite ? "fill-current" : ""}`} />}
      {pulse > 0 && item.favorite ? <span key={pulse} className="space-favorite-burst" aria-hidden="true"><Sparkles /><i /><i /></span> : null}
    </button>
  );
}

function LearningListLoading() {
  return <div className="space-course-grid space-course-loading" role="status" aria-label="正在加载课程">{[0, 1, 2].map((item) => <div key={item} aria-hidden="true"><span /><i /><i /></div>)}<span className="sr-only">正在加载课程</span></div>;
}

function LearningLibraryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="space-page-state" role="alert"><BookMarked aria-hidden="true" /><h3>课程暂时没有连上</h3><p>{message}</p><Button onClick={onRetry}>再试一次</Button></div>;
}

function LearningEmpty({
  bucket,
  catalogStatus,
  availability,
}: {
  bucket: LearningLibraryBucket;
  catalogStatus?: LearningLibraryResponse["catalogStatus"];
  availability?: NonNullable<LearningLibraryResponse["learningState"]>["availabilityStatus"];
}) {
  const copy = availability === "empty"
    ? ["这里还没有课程", "课程准备好后就会出现。"]
    : bucket === "all" && catalogStatus === "preparing"
    ? ["第一门课程正在准备", "完成一门就会自动放到这里，不需要等全部课程生成。"]
    : bucket === "favorites"
    ? ["还没有收藏课程", "看到喜欢的课，点一下小爱心就能放到这里。"]
    : bucket === "completed"
      ? ["还没有学完的课程", "完成一节互动课堂后，它会出现在这里。"]
      : bucket === "continue"
        ? ["没有上到一半的课程", "可以从全部课程里开始一节新课。"]
        : bucket === "makeup"
          ? ["没有待补的课程", "之前没学完的课会保留在这里，不会悄悄消失。"]
        : ["这里还没有课程", "家长安排或系统生成课程后，会自动出现在这里。"];
  return <div className="space-page-state"><BookMarked className="size-10" /><h3>{copy[0]}</h3><p>{copy[1]}</p></div>;
}

function courseStatus(item: LearningLibraryItem, forceMakeup = false) {
  if (item.report || item.session?.status === "completed" || item.taskStatus === "completed") return { kind: "completed", label: "已经学完" } as const;
  if (forceMakeup || item.taskStatus === "missed") return { kind: "makeup", label: "未完成，待补课" } as const;
  if (item.session?.status === "in_progress" || item.taskStatus === "in_progress") return { kind: "continue", label: "可以继续" } as const;
  return { kind: "scheduled", label: "等待开课" } as const;
}

function courseProgress(item: LearningLibraryItem) {
  if (courseStatus(item).kind === "completed") return 100;
  const total = Math.max(1, item.course.questionCount || 1);
  return Math.min(95, Math.round(((item.session?.attemptedCount || item.session?.currentQuestionIndex || 0) / total) * 100));
}
