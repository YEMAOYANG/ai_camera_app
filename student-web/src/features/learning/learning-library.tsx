"use client";

import {
  ArrowRight,
  BookMarked,
  CheckCircle2,
  Clock3,
  Heart,
  LibraryBig,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { MiraMark } from "@/components/student/mira-mark";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import {
  getLearningLibrary,
  setLearningFavorite,
} from "@/features/learning/learning-client";
import { gradeLabel, subjectPresentation } from "@/features/learning/learning-presenters";
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
  const router = useRouter();
  const [bucket, setBucket] = useState<LearningLibraryBucket>("all");
  const [subject, setSubject] = useState<LearningSubject | undefined>();
  const [data, setData] = useState<LearningLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [locking, setLocking] = useState(false);
  const [error, setError] = useState("");
  const [favoriteBusy, setFavoriteBusy] = useState("");

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

  async function lock() {
    setLocking(true);
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/unlock");
    router.refresh();
  }

  async function toggleFavorite(item: LearningLibraryItem) {
    if (favoriteBusy) return;
    setFavoriteBusy(item.course.id);
    setError("");
    try {
      const result = await setLearningFavorite(item.course.id, item.course.version, !item.favorite);
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
    <div className="learning-space mira-doodle-grid">
      <header className="learning-topbar">
        <Link href="/today" className="focus-ring" aria-label="回到今日学习"><MiraMark compact /></Link>
        <nav aria-label="学生学习导航">
          <Link href="/today">今日学习</Link>
          <Link href="/learning" aria-current="page">我的学习</Link>
        </nav>
        <Button variant="quiet" size="compact" onClick={lock} disabled={locking}>
          <LockKeyhole className="size-4" />{locking ? "正在锁定" : "休息一下"}
        </Button>
      </header>

      <main id="main-content" className="learning-main">
        <section className="learning-library-hero" aria-labelledby="learning-library-title">
          <div>
            <p className="learning-eyebrow"><LibraryBig className="size-5" />{gradeLabel(student.gradeCode)}学习书架</p>
            <h1 id="learning-library-title">{student.displayName}的<br /><span>我的学习</span></h1>
            <p>今天的课、学过的课和喜欢的课，都在这里。每次回来都能接着学。</p>
          </div>
          <MiraBuddy mood="reading" className="learning-library-buddy" label="Mira 在整理课程书架" />
        </section>

        {continuation && bucket === "all" ? (
          <ContinueLesson item={continuation} onFavorite={() => void toggleFavorite(continuation)} favoriteBusy={favoriteBusy === continuation.course.id} />
        ) : null}

        <section className="learning-library-section" aria-labelledby="course-list-title">
          <div className="learning-library-heading">
            <div>
              <p>课程目录</p>
              <h2 id="course-list-title">选择一节想学的课</h2>
            </div>
            {data ? (
              <span>
                {data.catalogStatus === "preparing"
                  ? `已有 ${data.availableCourseCount} 门可用，新课完成一门就会自动加入`
                  : data.catalogStatus === "failed"
                    ? `本轮更新未全部完成，现有 ${data.availableCourseCount} 门仍可学习`
                    : `共 ${data.availableCourseCount} 门课程`}
              </span>
            ) : null}
          </div>

          <div className="learning-filter-row" role="group" aria-label="课程状态筛选">
            {buckets.map((item) => <button key={item.id} type="button" className={`focus-ring ${bucket === item.id ? "is-active" : ""}`} aria-pressed={bucket === item.id} onClick={() => { if (bucket === item.id) return; setLoading(true); setError(""); setBucket(item.id); }}>{item.label}</button>)}
          </div>
          <div className="learning-subject-row" role="group" aria-label="学科筛选">
            {subjects.map((item) => <button key={item.id || "all"} type="button" className={`focus-ring ${subject === item.id ? "is-active" : ""}`} aria-pressed={subject === item.id} onClick={() => { if (subject === item.id) return; setLoading(true); setError(""); setSubject(item.id); }}>{item.label}</button>)}
          </div>

          {loading ? <LearningListLoading /> : null}
          {!loading && error ? <LearningLibraryError message={error} onRetry={load} /> : null}
          {!loading && !error && visibleItems.length ? (
            <div className="learning-course-list">
              {visibleItems.map((item) => (
                <CourseRow
                  key={`${item.taskId || item.course.id}:${item.course.version}`}
                  item={item}
                  makeup={bucket === "makeup"}
                  favoriteBusy={favoriteBusy === item.course.id}
                  onFavorite={() => void toggleFavorite(item)}
                />
              ))}
            </div>
          ) : null}
          {!loading && !error && !visibleItems.length ? <LearningEmpty bucket={bucket} catalogStatus={data?.catalogStatus} /> : null}
        </section>
      </main>
    </div>
  );
}

function libraryHasPreparingClassroom(data: LearningLibraryResponse | null) {
  return Boolean(data && (
    data.catalogStatus !== "failed"
    && (
      data.catalogStatus === "preparing"
      || [data.continueItem, ...data.items]
        .some((item) => item && !item.fullClassroomAvailable)
    )
  ));
}

function ContinueLesson({ item, onFavorite, favoriteBusy }: { item: LearningLibraryItem; onFavorite: () => void; favoriteBusy: boolean }) {
  const presentation = subjectPresentation(item.course.subject);
  const Icon = presentation.icon;
  const progress = courseProgress(item);
  return (
    <section className="learning-continue" aria-labelledby="continue-title">
      <div className={`learning-continue-rail ${presentation.surface}`} aria-hidden="true" />
      <div className="learning-continue-copy">
        <p><RotateCcw className="size-5" />上次学到这里</p>
        <h2 id="continue-title">{item.course.title}</h2>
        <span>{item.course.objective}</span>
        <div className="learning-progress-line"><i style={{ width: `${progress}%` }} /><small>{progress}%</small></div>
      </div>
      <div className="learning-continue-actions">
        <span className={`learning-subject-seal ${presentation.surface} ${presentation.strong}`}><Icon className="size-6" />{item.course.subjectLabel}</span>
        <FavoriteButton item={item} busy={favoriteBusy} onClick={onFavorite} />
        <CourseAction item={item} label="继续上课" />
      </div>
    </section>
  );
}

function CourseRow({ item, makeup, onFavorite, favoriteBusy }: { item: LearningLibraryItem; makeup: boolean; onFavorite: () => void; favoriteBusy: boolean }) {
  const presentation = subjectPresentation(item.course.subject);
  const Icon = presentation.icon;
  const status = courseStatus(item, makeup);
  return (
    <article className="learning-course-row">
      <span className={`learning-course-icon ${presentation.surface} ${presentation.strong}`}><Icon className="size-6" /></span>
      <div className="learning-course-copy">
        <div><span>{item.course.subjectLabel}</span><i>·</i><span>{status.label}</span>{status.kind !== "completed" && (item.fullClassroomAvailable ? <em>完整互动课堂已就绪</em> : <em className="is-preparing">完整课堂准备中</em>)}</div>
        <h3><Link href={`/learning/${encodeURIComponent(item.course.id)}?version=${encodeURIComponent(item.course.version)}`}>{item.course.title}</Link></h3>
        <p>{item.course.objective}</p>
        <small><Clock3 className="size-4" />约 {item.course.estimatedMinutes} 分钟{item.scheduledStart ? ` · ${item.scheduledStart}` : ""}</small>
      </div>
      <div className="learning-course-actions">
        <FavoriteButton item={item} busy={favoriteBusy} onClick={onFavorite} />
        {status.kind === "completed" ? <span className="learning-complete-mark"><CheckCircle2 className="size-5" />学完啦</span> : <CourseAction item={item} label={status.kind === "makeup" ? "补上这节课" : undefined} />}
      </div>
    </article>
  );
}

function CourseAction({ item, label }: { item: LearningLibraryItem; label?: string }) {
  if (!item.fullClassroomAvailable) {
    return <span className="learning-making-action"><Sparkles className="size-4" />完整课堂准备中</span>;
  }
  if (!item.taskId) {
    return <span className="learning-making-action"><Clock3 className="size-4" />等待安排</span>;
  }
  return <Button asChild><DocumentLink href={openMaicLessonPath(item.taskId)}>{label || "开始上课"}<ArrowRight className="size-5" /></DocumentLink></Button>;
}

function FavoriteButton({ item, busy, onClick }: { item: LearningLibraryItem; busy: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`focus-ring learning-favorite ${item.favorite ? "is-active" : ""}`} onClick={onClick} disabled={busy} aria-label={item.favorite ? `取消收藏${item.course.title}` : `收藏${item.course.title}`}>
      {busy ? <LoaderCircle className="size-5 animate-spin" /> : <Heart className={`size-5 ${item.favorite ? "fill-current" : ""}`} />}
    </button>
  );
}

function LearningListLoading() {
  return <div className="learning-course-list is-loading" aria-label="正在加载课程">{[0, 1, 2].map((item) => <div key={item}><i /><span><b /><small /></span></div>)}</div>;
}

function LearningLibraryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="learning-library-state" role="alert"><MiraBuddy mood="thinking" className="w-24" /><h3>课程书架刚刚走神了</h3><p>{message}</p><Button onClick={onRetry}>再试一次</Button></div>;
}

function LearningEmpty({
  bucket,
  catalogStatus,
}: {
  bucket: LearningLibraryBucket;
  catalogStatus?: LearningLibraryResponse["catalogStatus"];
}) {
  const copy = bucket === "all" && catalogStatus === "preparing"
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
  return <div className="learning-library-state"><BookMarked className="size-10" /><h3>{copy[0]}</h3><p>{copy[1]}</p></div>;
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
