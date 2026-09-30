"use client";

import Image from "next/image";
import Link from "next/link";
import { Backpack, Play, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { TextbookCatalog, TextbookSubject } from "@/lib/contracts/textbooks";
import voice from "./navigation-audio.json";

export type LearningCue = keyof typeof voice.cues;
const subjects: TextbookSubject[] = ["chinese", "math", "english", "science"];

export function SubjectPicture({ subject }: { subject: TextbookSubject }) {
  const panel = subjects.indexOf(subject);
  return <span className="learning-subject-picture" aria-hidden="true"><Image
    src="/textbooks/navigation-v1/subjects-1670ad3a023e7649.png" alt="" width={1254} height={1254}
    sizes="(max-width: 760px) 80vw, 500px" style={{ left: `${panel % 2 * -100}%`, top: `${Math.floor(panel / 2) * -100}%` }} /></span>;
}

/** One original Qwen narration at a time; no browser/system speech fallback. */
export function useLearningVoice() {
  const player = useRef<HTMLAudioElement | null>(null);
  const [failed, setFailed] = useState(false);
  const stop = useCallback(() => {
    player.current?.pause();
    player.current?.removeAttribute("src");
    player.current = null;
  }, []);
  useEffect(() => {
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener("mira:learner-narration", stop);
    document.addEventListener("visibilitychange", hide);
    return () => {
      stop();
      window.removeEventListener("mira:learner-narration", stop);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [stop]);
  const say = useCallback((cue: LearningCue) => {
    window.dispatchEvent(new Event("mira:learner-narration"));
    setFailed(false);
    const audio = new Audio(voice.cues[cue].src);
    player.current = audio;
    const error = () => { if (player.current === audio) setFailed(true); };
    audio.onerror = error;
    void audio.play().catch(error);
  }, []);
  return { say, stop, failed };
}

export function LearningListenButton({ cue, label = "听老师说" }: { cue: LearningCue; label?: string }) {
  const { say, failed } = useLearningVoice();
  return <Button type="button" variant="secondary" size="compact" className="learning-listen" onClick={() => say(cue)} aria-label={label}>
    <Volume2 aria-hidden="true" /><span>{failed ? "再听一次" : label}</span>
  </Button>;
}

export function LessonPicture({ title, subject = "chinese" }: { title: string; subject?: TextbookSubject }) {
  return title.includes("天地人") ? <Image className="learning-lesson-picture" src="/textbooks/navigation-v1/tiandiren-140b4fec01160057.webp"
    width={1600} height={800} alt="天空下，三个孩子在花园的小路上说话、挥手" sizes="(max-width: 760px) 92vw, 620px" />
    : <SubjectPicture subject={subject} />;
}

export function getLearningHomeState(catalog: TextbookCatalog) {
  const journey = catalog.learningJourneys?.find(item => item.reviewDue)
    ?? catalog.learningJourneys?.find(item => item.parentNeeded || ["learning", "checking", "reviewing"].includes(item.status));
  const start = catalog.startHere;
  const last = catalog.learningJourneys?.[0];
  const cue: LearningCue = journey ? journey.reviewDue ? "review" : "continue" : start ? "start" : last ? "welcome" : catalog.books.some(book => book.selected) ? "unavailable" : "selection";
  return { journey, start, last, cue };
}

export function LearningNextPicture({ catalog }: { catalog: TextbookCatalog }) {
  const { journey, start, last, cue } = getLearningHomeState(catalog);
  const title = journey?.title ?? start?.title ?? last?.title;
  const contentKey = journey?.contentKey ?? start?.contentKey;
  const heading = cue === "review" ? "再来试一试" : cue === "continue" ? "接着玩" : cue === "start" ? "开始小任务" : cue === "welcome" ? "上次的学习已保存" : cue === "unavailable" ? "课件正在准备" : "等家长放入课本";
  return <section className="learning-next-picture" aria-label={heading}>
    {contentKey && title ? <Link prefetch={false} href={`/learning/textbooks/courses/${contentKey}`} className="learning-picture-launch" aria-label={`${heading}，${title}`}>
      <LessonPicture title={title} subject={start?.subject} /><span className="learning-picture-play"><Play size={36} fill="currentColor" aria-hidden="true" /></span>
      <span className="learning-picture-caption"><strong>{heading}</strong><span>{title}</span></span>
    </Link> : <div className="learning-picture-rest"><Backpack size={56} aria-hidden="true" /><strong>{heading}</strong>
      {last && <span>{last.title}</span>}
      {last?.reviewDueAt && <small>下次复习 {new Date(last.reviewDueAt).toLocaleDateString("zh-CN", { month: "long", day: "numeric", timeZone: "Asia/Shanghai" })}</small>}</div>}
  </section>;
}
