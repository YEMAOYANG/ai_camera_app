"use client";

import { ArrowRight, BookOpenText, Check, Clock3, CloudSun, LoaderCircle, LockKeyhole, RotateCcw, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { MiraMark } from "@/components/student/mira-mark";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { assignTodayLearning, getTodayLearning } from "@/features/learning/learning-client";
import { gradeLabel, masteryLabel, stateLabel, subjectPresentation } from "@/features/learning/learning-presenters";
import type { LearningTodayItem, LearningTodayResponse } from "@/lib/contracts/learning";
import { openMaicLessonPath } from "@/lib/routing/classroom";
import type { Student } from "@/lib/contracts/student-session";

export function StudentDashboard({
  student,
  pollIntervalMs = 10_000,
}: {
  student: Student;
  pollIntervalMs?: number;
}) {
  const router = useRouter();
  const [today, setToday] = useState<LearningTodayResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const [locking, setLocking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setToday(await getTodayLearning());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "今天的课程暂时没有准备好");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getTodayLearning()
      .then((value) => { if (active) setToday(value); })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "今天的课程暂时没有准备好");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (loading || today?.catalogStatus !== "preparing") return;
    let active = true;
    let timer: number | undefined;
    let failures = 0;
    const delay = (paused = today?.courseSupply?.paused || today?.courseSupply?.delayed) => Math.max(pollIntervalMs, paused ? 30_000 : 0) * Math.min(3, 1 + failures) + Math.random() * Math.min(1500, pollIntervalMs * 0.15);
    const poll = async () => {
      if (document.hidden) {
        timer = window.setTimeout(() => void poll(), 30_000);
        return;
      }
      try {
        const value = await getTodayLearning();
        failures = 0;
        if (active) {
          setToday(value);
          setError("");
        }
        if (active && value.catalogStatus === "preparing") {
          timer = window.setTimeout(() => void poll(), delay(value.courseSupply?.paused || value.courseSupply?.delayed));
        }
      } catch {
        // Keep already-ready lessons stable while generation continues.
        failures += 1;
        if (active) timer = window.setTimeout(() => void poll(), delay());
      }
    };
    timer = window.setTimeout(() => void poll(), delay());
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [loading, pollIntervalMs, today?.catalogStatus, today?.courseSupply?.paused, today?.courseSupply?.delayed]);

  async function prepareCourses() {
    setAssigning(true);
    setError("");
    try {
      setToday(await assignTodayLearning());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "课程准备失败，请稍后再试");
    } finally {
      setAssigning(false);
    }
  }

  async function lock() {
    setLocking(true);
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    router.replace("/unlock");
    router.refresh();
  }

  const itemCount = today?.itemCount ?? 0;
  const completedCount = today?.completedCount ?? 0;
  const carryoverCount = today?.carryoverCount ?? 0;
  const dailyTargetCount = 3;
  const preparingSlotCount = today?.catalogStatus === "preparing"
    ? Math.max(0, dailyTargetCount - itemCount)
    : 0;
  const dailySummary = itemCount >= dailyTargetCount
    ? `今天有 ${dailyTargetCount} 节小课。${carryoverCount
      ? `先补上 ${carryoverCount} 节没学完的课，再学习今天的新内容。`
      : "老师会先讲清楚，再陪你一起练。"}`
    : itemCount > 0
      ? `今天已有 ${itemCount} 节小课可以学，新的课程完成一节就会自动出现一节。`
      : "今天的第一节小课正在准备，完成后会自动出现在这里。";

  return (
    <div className="mira-doodle-grid relative min-h-screen overflow-hidden px-4 pb-12 pt-5 sm:px-7 sm:pt-7">
      <div className="pointer-events-none absolute -left-24 top-24 size-72 rounded-full bg-[var(--mira-sky)]/70 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -right-24 top-[38%] size-80 rounded-full bg-[var(--mira-sun-soft)]/55 blur-3xl" aria-hidden="true" />
      <header className="relative mx-auto flex w-full max-w-6xl items-center justify-between">
        <MiraMark compact />
        <div className="flex items-center gap-2">
          <Button asChild variant="secondary" size="compact"><Link href="/learning"><BookOpenText className="size-4" />我的学习</Link></Button>
          <Button variant="quiet" size="compact" onClick={lock} disabled={locking}>
            <LockKeyhole className="size-4" aria-hidden="true" />
            {locking ? "正在锁定" : "休息一下"}
          </Button>
        </div>
      </header>

      <main id="main-content" className="relative mx-auto mt-7 w-full max-w-6xl sm:mt-10">
        <section className="relative overflow-hidden rounded-[32px] border-2 border-white bg-[linear-gradient(125deg,#e8f2ff_0%,#fff8dd_100%)] px-5 py-7 shadow-[var(--mira-shadow-card)] sm:px-9 sm:py-9">
          <div className="absolute right-[-40px] top-[-40px] size-48 rounded-full border-[24px] border-white/35" aria-hidden="true" />
          <div className="relative grid items-center gap-5 md:grid-cols-[1fr_210px]">
            <div>
              <p className="flex items-center gap-2 text-sm font-extrabold text-[var(--mira-brand-deep)]">
                <CloudSun className="size-5" aria-hidden="true" /> 今天也一起进步一点点
              </p>
              <h1 className="mt-3 text-[clamp(34px,6vw,58px)] font-black leading-[1.08] tracking-[-.055em]">
                {student.displayName}，<span className="text-[var(--mira-brand-deep)]">欢迎回来！</span>
              </h1>
              <p className="mt-4 max-w-2xl text-[17px] leading-8 text-[var(--mira-muted)]">
                {gradeLabel(student.gradeCode)} · {dailySummary}
              </p>
              <div className="mt-6 flex max-w-md items-center gap-3 rounded-[20px] bg-white/75 p-3 pr-5 shadow-sm">
                <span className="grid size-11 shrink-0 place-items-center rounded-[15px] bg-[var(--mira-mint)] text-[var(--mira-mint-deep)]">
                  <Sparkles className="size-5" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3 text-sm font-extrabold">
                    <span>今日进度</span><span>{completedCount}/{dailyTargetCount}</span>
                  </div>
                  <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-[var(--mira-border-soft)]">
                    <div className="h-full rounded-full bg-[var(--mira-brand)] transition-[width] duration-500" style={{ width: `${(completedCount / dailyTargetCount) * 100}%` }} />
                  </div>
                </div>
              </div>
            </div>
            <MiraBuddy mood={completedCount === itemCount && itemCount > 0 ? "celebrate" : "hello"} className="mx-auto w-[170px] md:w-[205px]" label={completedCount === itemCount ? "为你庆祝的小伙伴" : "陪你学习的小伙伴"} />
          </div>
        </section>

        <section className="mt-8" aria-labelledby="today-courses-title" aria-live="polite">
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm font-extrabold text-[var(--mira-brand-deep)]">我的小课堂</p>
              <h2 id="today-courses-title" className="mt-1 text-[30px] font-black tracking-[-.045em]">今天学什么？</h2>
            </div>
            {today ? <p className="text-sm font-semibold text-[var(--mira-muted)]">课程会自动保存，随时可以回来继续</p> : null}
          </div>

          {!loading && !error && carryoverCount ? (
            <div className="mb-5 flex items-center gap-3 rounded-[20px] border-2 border-white bg-[var(--mira-sun-soft)]/75 px-4 py-3 text-sm font-bold text-[var(--mira-muted)] shadow-sm">
              <RotateCcw className="size-5 shrink-0 text-[var(--mira-brand-deep)]" aria-hidden="true" />
              <span>昨天没学完没关系：今天只顺延一节，先接着学，其他课程会留在“待补课”。</span>
            </div>
          ) : null}

          {!loading && !error && today?.catalogStatus === "preparing" && today.availableCourseCount === 0 ? (
            <PreparationProgress today={today} />
          ) : null}
          {!loading && !error && today?.catalogStatus === "failed" && today.items.length ? (
            <div className="mb-5 flex items-center gap-3 rounded-[20px] border-2 border-white bg-[var(--mira-sun-soft)]/75 px-4 py-3 text-sm font-bold text-[var(--mira-muted)] shadow-sm">
              <RotateCcw className="size-5 shrink-0 text-[var(--mira-brand-deep)]" aria-hidden="true" />
              <span>这次新课更新没有全部完成，下面已经准备好的课程仍然可以正常学习。</span>
            </div>
          ) : null}

          {loading ? <TodayLoading /> : null}
          {!loading && error ? <TodayError message={error} onRetry={load} /> : null}
          {!loading && !error && today ? (
            <div className="grid gap-5 md:grid-cols-2">
              {today.items.map((item, index) => (
                <CourseCard key={item.slot} item={item} index={index} onPrepare={prepareCourses} preparing={assigning} />
              ))}
              {Array.from({ length: preparingSlotCount }, (_, index) => (
                <PreparingCourseCard key={`preparing-${index}`} index={itemCount + index} paused={today?.courseSupply?.paused} />
              ))}
            </div>
          ) : null}
          {!loading && !error && today && today.items.length === 0 && today.catalogStatus !== "preparing" ? (
            <TodayError message="今天还没有排好课程" onRetry={prepareCourses} />
          ) : null}
        </section>
      </main>
    </div>
  );
}

function PreparationProgress({ today }: { today: LearningTodayResponse }) {
  const percent = today.preparationProgressPercent;
  return (
    <div className="mb-5 rounded-[20px] border-2 border-white bg-[var(--mira-sky)]/65 px-5 py-4 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 font-extrabold text-[var(--mira-ink)]">
        <span>{today.courseSupply?.paused ? "新课还需要一点调整" : today.courseSupply?.delayed ? "准备时间有点长" : "新课准备进度"}</span>
        <span className="text-xl tabular-nums text-[var(--mira-brand-deep)]">{percent == null ? "正在获取进度" : `${percent}%`}</span>
      </div>
      <div role="progressbar" aria-label="新课准备进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}
        className="mt-3 h-3 overflow-hidden rounded-full bg-white">
        {percent != null ? <div className="h-full origin-left rounded-full bg-[var(--mira-brand)] transition-transform duration-300 motion-reduce:transition-none" style={{ transform: `scaleX(${percent / 100})` }} /> : null}
      </div>
      <p className="mt-3 text-sm font-semibold leading-6 text-[var(--mira-ink)]">
        {today.courseSupply && (today.courseSupply.paused || today.courseSupply.delayed) ? today.courseSupply.message
          : "老师正在为你准备小课堂，第一节准备好就会出现在这里。可以先休息一下，再回来看看。"}
      </p>
      <p className="mt-1 text-xs leading-5 text-[var(--mira-muted)]">这是整批新课的准备进度，第一节课准备好就能先学。</p>
    </div>
  );
}

function PreparingCourseCard({ index, paused = false }: { index: number; paused?: boolean }) {
  const titles = ["老师正在认真备课", "有趣的小挑战正在路上", "新的小知识快来报到啦"];
  const descriptions = ["老师在准备故事和练习，准备好就会邀请你来上课。", "动动脑筋的小任务正在准备，完成后会自动出现。", "可以先休息一下，也可以先学已经准备好的小课。"];

  return (
    <article className="relative min-h-72 overflow-hidden rounded-[28px] border-2 border-dashed border-white bg-white/68 p-5 shadow-sm sm:p-7" aria-label={`第 ${index + 1} 课正在准备`}>
      <div className="flex items-center gap-3">
        <span className="grid size-13 place-items-center rounded-[18px] bg-[var(--mira-sky)] text-[var(--mira-brand-deep)]">
          {paused ? <Clock3 className="size-6" aria-hidden="true" /> : <LoaderCircle className="size-6 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
        </span>
        <div>
          <p className="text-sm font-extrabold text-[var(--mira-brand-deep)]">第 {index + 1} 课</p>
          <p className="mt-0.5 text-sm font-semibold text-[var(--mira-muted)]">完成后自动出现</p>
        </div>
      </div>
      <h3 className="mt-6 text-[24px] font-black tracking-[-.035em]">{paused ? "小课堂还需要一点调整" : titles[index % titles.length]}</h3>
      <p className="mt-3 max-w-sm text-[15px] leading-7 text-[var(--mira-muted)]">{paused ? "准备好后会自动出现，可以先学已经准备好的课程。" : descriptions[index % descriptions.length]}</p>
    </article>
  );
}

function CourseCard({
  item,
  index,
  onPrepare,
  preparing,
}: {
  item: LearningTodayItem;
  index: number;
  onPrepare: () => void;
  preparing: boolean;
}) {
  const presentation = subjectPresentation(item.subject);
  const Icon = presentation.icon;
  const report = item.latestReport;
  const isCarryover = item.dayBucket === "carryover" || Boolean(item.carryover);
  const carryoverLabel = item.carryover?.daysOverdue === 1
    ? "昨天未完成 · 继续学"
    : `前 ${item.carryover?.daysOverdue || 1} 天未完成 · 继续学`;
  return (
    <article className="group relative overflow-hidden rounded-[28px] border-2 border-white bg-white p-5 shadow-[var(--mira-shadow-card)] transition-transform duration-200 hover:-translate-y-1 sm:p-7">
      <div className={`absolute inset-x-0 top-0 h-2 ${presentation.surface}`} aria-hidden="true" />
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className={`grid size-13 place-items-center rounded-[18px] ${presentation.surface} ${presentation.strong}`}>
            <Icon className="size-6" aria-hidden="true" />
          </span>
          <div>
            <p className={`text-sm font-extrabold ${presentation.strong}`}>{isCarryover ? carryoverLabel : `第 ${index + 1} 课 · ${presentation.eyebrow}`}</p>
            <p className="mt-0.5 text-sm font-semibold text-[var(--mira-muted)]">{stateLabel(item.state)}</p>
          </div>
        </div>
        {item.state === "completed" ? (
          <span className="grid size-10 place-items-center rounded-full bg-[var(--mira-mint)] text-[var(--mira-mint-deep)]" aria-label="课程已完成"><Check className="size-5" /></span>
        ) : null}
      </div>
      <h3 className="mt-6 text-[26px] font-black leading-tight tracking-[-.04em]">{item.recommendation.title}</h3>
      <p className="mt-3 min-h-14 text-[15px] leading-7 text-[var(--mira-muted)]">{item.recommendation.objective}</p>
      <div className="mt-5 flex flex-wrap gap-2 text-sm font-bold text-[var(--mira-muted)]">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--mira-bg)] px-3 py-2"><Clock3 className="size-4" />约 {item.recommendation.estimatedMinutes} 分钟</span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--mira-bg)] px-3 py-2"><RotateCcw className="size-4" />先讲再练</span>
      </div>

      {item.state === "completed" && report ? (
        <div className="mt-6 rounded-[20px] bg-[var(--mira-mint)]/70 p-4">
          <p className="font-extrabold text-[var(--mira-mint-deep)]">{masteryLabel(report.masteryLevel)} · {report.independentCorrectCount}/{report.totalQuestions} 独立答对</p>
          <p className="mt-1 text-sm leading-6 text-[var(--mira-muted)]">{report.summary}</p>
        </div>
      ) : item.task ? (
        <Button asChild className="mt-6 w-full">
          <DocumentLink href={openMaicLessonPath(item.task.id)}>
            {isCarryover ? "继续未完成的课" : item.state === "in_progress" ? "继续这节课" : "开始这节课"}<ArrowRight className="size-5" />
          </DocumentLink>
        </Button>
      ) : (
        <Button className="mt-6 w-full" onClick={onPrepare} disabled={preparing}>
          {preparing ? <LoaderCircle className="size-5 animate-spin" /> : <Sparkles className="size-5" />}
          {preparing ? "正在准备…" : "准备今天的课程"}
        </Button>
      )}
    </article>
  );
}

function TodayLoading() {
  return (
    <div className="grid gap-5 md:grid-cols-2" aria-label="正在读取今日课程">
      {[0, 1, 2].map((item) => (
        <div key={item} className="min-h-80 animate-pulse rounded-[28px] border-2 border-white bg-white/72 p-7 shadow-sm">
          <div className="size-13 rounded-[18px] bg-[var(--mira-border-soft)]" />
          <div className="mt-7 h-7 w-2/3 rounded-full bg-[var(--mira-border-soft)]" />
          <div className="mt-4 h-4 w-full rounded-full bg-[var(--mira-border-soft)]" />
          <div className="mt-2 h-4 w-4/5 rounded-full bg-[var(--mira-border-soft)]" />
        </div>
      ))}
    </div>
  );
}

function TodayError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-[28px] border-2 border-white bg-white p-7 text-center shadow-[var(--mira-shadow-card)]">
      <MiraBuddy mood="thinking" className="mx-auto w-28" label="Mira 正在想办法" />
      <h3 className="mt-3 text-2xl font-black">刚刚没连上</h3>
      <p className="mx-auto mt-2 max-w-lg leading-7 text-[var(--mira-muted)]">{message}</p>
      <Button className="mt-5" onClick={onRetry}>再试一次</Button>
    </div>
  );
}
