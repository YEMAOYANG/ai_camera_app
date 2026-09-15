"use client";

import { ArrowRight, Check, ChevronLeft, ChevronRight, Clock3, LoaderCircle, Orbit, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { SpaceShell } from "@/components/student/space-shell";
import { SpaceCourseArt } from "@/components/student/space-course-art";
import { SpaceClickSpark, SpaceTilt } from "@/components/student/space-motion";
import { DocumentLink } from "@/components/navigation/document-link";
import { Button } from "@/components/ui/button";
import { assignTodayLearning, getTodayLearning } from "@/features/learning/learning-client";
import { gradeLabel, masteryLabel, stateLabel, subjectPresentation } from "@/features/learning/learning-presenters";
import type { LearningTodayResponse } from "@/lib/contracts/learning";
import { openMaicLessonPath } from "@/lib/routing/classroom";
import type { Student } from "@/lib/contracts/student-session";

export function StudentDashboard({
  student,
  pollIntervalMs = 10_000,
}: {
  student: Student;
  pollIntervalMs?: number;
}) {
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [today, setToday] = useState<LearningTodayResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [assigning, setAssigning] = useState(false);
  const availability = today?.learningState?.availabilityStatus ?? today?.courseSupply?.availabilityStatus;

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
    if (loading || availability === "empty" || availability === "not_open" || availability === "scope_completed"
      || today?.catalogStatus !== "preparing" || today.availableCourseCount > 0) return;
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
        const nextAvailability = value.learningState?.availabilityStatus ?? value.courseSupply?.availabilityStatus;
        if (active && !["empty", "not_open", "scope_completed"].includes(nextAvailability ?? "")
          && value.catalogStatus === "preparing" && value.availableCourseCount === 0) {
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
  }, [loading, availability, pollIntervalMs, today?.catalogStatus, today?.availableCourseCount, today?.courseSupply?.paused, today?.courseSupply?.delayed]);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      if (document.hidden) return;
      void getTodayLearning().then(value => { if (active) setToday(value); }).catch(() => undefined);
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      active = false;
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);

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

  const items = today?.items ?? [];
  const completedCount = today?.completedCount ?? 0;
  const carryoverCount = today?.carryoverCount ?? 0;
  const selected = items.find(item => item.slot === selectedSlot)
    ?? items.find(item => item.state === "in_progress" || item.dayBucket === "carryover")
    ?? items.find(item => item.state !== "completed") ?? items[0];
  const selectedIndex = selected ? items.indexOf(selected) : -1;
  const scopeFinished = ["scope_completed", "not_open", "empty"].includes(availability ?? "");
  const preparing = today?.catalogStatus === "preparing" && today.availableCourseCount === 0 && !scopeFinished;
  const availabilityMessage = today?.learningState?.message ?? today?.courseSupply?.message;
  const dailySummary = items.length >= 3
    ? `今天有 3 节小课。${carryoverCount ? `先补上 ${carryoverCount} 节没学完的课，再学习今天的新内容。` : "老师会先讲清楚，再陪你一起练。"}`
    : items.length ? `今天已有 ${items.length} 节小课可以学，课程会自动保存。` : "";
  const isCarryover = selected?.dayBucket === "carryover" || Boolean(selected?.carryover);
  const activeLabel = selected ? subjectPresentation(selected.subject).label : "学习空间";
  const title = loading ? "准备出发" : error ? "刚刚没连上" : selected?.recommendation.title
    ?? (availability === "scope_completed" ? "本单元已完成" : availability === "not_open" ? "课程尚未开放" : availability === "empty" ? "这里还没有课程" : preparing ? "新的探索，正在准备" : "今天还没有排好课程");
  function changeSelection(direction: number) {
    if (items.length > 1) setSelectedSlot(items[(selectedIndex + direction + items.length) % items.length].slot);
  }
  return <SpaceShell student={student} active="today" scenic className="space-today">
    <section className="space-today-hero" aria-labelledby="today-course-title" aria-busy={loading}>
      <div className="space-today-copy" key={selected?.slot ?? "empty"}>
        <p className={`space-hero-eyebrow space-subject-${selected?.subject || "math"}`}>{activeLabel}<span>·</span>{selected ? selected.state === "in_progress" ? "正在学习" : stateLabel(selected.state) : "每一步，都有新发现"}</p>
        <h1 id="today-course-title" className={title.length > 10 ? "space-title-long" : undefined}>{title}</h1>
        <p className="space-hero-objective">{loading ? "正在读取今日课程" : error || selected?.recommendation.objective || availabilityMessage || "跟着老师，发现更多有趣的知识。"}</p>
        {selected && <p className="space-hero-duration"><Clock3 size={25} strokeWidth={1.6} />约 {selected.recommendation.estimatedMinutes} 分钟</p>}
        {loading ? <span className="space-loading-label" role="status"><LoaderCircle className="animate-spin motion-reduce:animate-none" size={22} />正在读取今日课程</span> : error ? <Button className="space-hero-action" onClick={() => void load()}>再试一次<RotateCcw size={23} /></Button> : selected ? <>
          {selected.state === "completed" && selected.latestReport ? <div className="space-hero-report"><p><Check size={20} />{masteryLabel(selected.latestReport.masteryLevel)} · {selected.latestReport.independentCorrectCount}/{selected.latestReport.totalQuestions} 独立答对</p><p>{selected.latestReport.summary}</p><Button asChild className="space-hero-action"><Link href="/learning">查看学习记录<ArrowRight size={24} /></Link></Button></div>
            : selected.task ? <Button asChild className="space-hero-action"><DocumentLink href={openMaicLessonPath(selected.task.id)} aria-label={isCarryover ? "继续未完成的课" : selected.state === "in_progress" ? "继续这节课" : "开始这节课"}>{isCarryover || selected.state === "in_progress" ? "继续学习" : "开始学习"}<ChevronRight size={28} /></DocumentLink></Button>
              : <Button className="space-hero-action" onClick={() => void prepareCourses()} disabled={assigning}>{assigning ? "正在准备…" : "准备今天的课程"}<ArrowRight size={24} /></Button>}
        </> : scopeFinished ? (today?.learningState?.reviewCourseCount ?? 0) > 0 && <Button asChild className="space-hero-action"><Link href="/learning">去复习学过的课程<ArrowRight size={23} /></Link></Button>
          : !preparing && <Button className="space-hero-action" onClick={() => void prepareCourses()} disabled={assigning}>{assigning ? "正在准备…" : "准备今天的课程"}<ArrowRight size={23} /></Button>}
      </div>
    </section>
    <section className="space-today-courses" aria-label="今天的课程">
      <div className="space-course-strip-heading"><h2>今日已完成 <strong>{completedCount} / {Math.max(items.length, completedCount, 3)}</strong><span> 节</span></h2><div className="space-course-arrows"><button className="focus-ring" aria-label="上一节课程" onClick={() => changeSelection(-1)} disabled={items.length < 2}><ChevronLeft size={22} /></button><button className="focus-ring" aria-label="下一节课程" onClick={() => changeSelection(1)} disabled={items.length < 2}><ChevronRight size={22} /></button></div></div>
      {carryoverCount > 0 && <p className="space-today-notice"><RotateCcw size={18} />昨天没学完没关系：今天只顺延一节，先接着学，其他课程会留在“待补课”。</p>}
      {preparing && today && <PreparationProgress today={today} />}
      {today?.catalogStatus === "failed" && items.length > 0 && <p className="space-today-notice">这次新课更新没有全部完成，下面已经准备好的课程仍然可以正常学习。</p>}
      <SpaceClickSpark><div className="space-course-strip">
        {!loading && !error && items.map((item, index) => <SpaceTilt key={item.slot} className="space-course-tile-wrap"><button className="focus-ring space-course-tile" aria-pressed={selected?.slot === item.slot} onClick={() => setSelectedSlot(item.slot)} aria-label={`选择${subjectPresentation(item.subject).label}课程：${item.recommendation.title}`}>
          <SpaceCourseArt subject={item.subject} priority={index < 3} /><span className="space-course-tile__shade" aria-hidden="true" /><span className="space-course-tile__copy"><strong>{subjectPresentation(item.subject).label}</strong><span>{item.recommendation.title}</span></span>
          <span className={`space-course-status space-course-status--${item.state}`}>{item.state === "completed" ? <Check size={18} /> : item.state === "in_progress" ? <i /> : <Clock3 size={18} />}{item.dayBucket === "carryover" || item.carryover ? item.carryover?.daysOverdue === 1 ? "昨天未完成 · 继续学" : `前 ${item.carryover?.daysOverdue || 1} 天未完成 · 继续学` : item.state === "in_progress" ? "学习中" : item.state === "completed" ? "已完成" : "稍后学习"}</span>
        </button></SpaceTilt>)}
        {loading && [0,1,2].map(index => <div key={index} className="space-course-skeleton" aria-hidden="true" />)}
        {preparing && items.length === 0 && <div className="space-course-waiting"><Orbit size={36} /><div><h3>{today?.courseSupply?.paused ? "小课堂还需要一点调整" : "老师正在认真备课"}</h3><p>第一节准备好，就会出现在这里。</p></div></div>}
      </div></SpaceClickSpark>
      {dailySummary && <p className="space-today-summary">{gradeLabel(student.gradeCode)} · {dailySummary}</p>}
    </section>
  </SpaceShell>;
}

function PreparationProgress({ today }: { today: LearningTodayResponse }) {
  const percent = today.preparationProgressPercent;
  return <div className="space-preparation" role="status"><div><strong>{today.courseSupply?.paused ? "新课还需要一点调整" : today.courseSupply?.delayed ? "准备时间有点长" : "新课准备进度"}</strong><span>{percent == null ? "正在获取进度" : `${percent}%`}</span></div><div className="space-preparation-track" role="progressbar" aria-label="新课准备进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent ?? undefined}>{percent != null && <i style={{ transform: `scaleX(${percent / 100})` }} />}</div><p>{today.courseSupply?.paused || today.courseSupply?.delayed ? today.courseSupply.message : "老师正在为你准备小课堂，第一节准备好就会出现在这里。可以先休息一下，再回来看看。"}</p></div>;
}
