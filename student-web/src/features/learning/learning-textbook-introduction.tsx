"use client";

import { ArrowLeft, ArrowRight, BookOpen, Captions, Check, Pause, Play, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { Button } from "@/components/ui/button";
import { TextbookPicture } from "@/features/learning/textbook-picture";
import { textbookContentsPath } from "@/features/learning/textbook-navigation";
import type { PictureGuideSegment, TextbookContents, TextbookIntroduction } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

type Props = { student: Student; contents: TextbookContents; introduction: TextbookIntroduction; unitId?: string };
const steps = ["听故事", "点点看", "试一试", "去发现"];

export function LearningTextbookIntroduction(props: Props) {
  return <PictureIntroduction key={`${props.introduction.contentSha256}:${props.introduction.presentation?.presentationSha256}`} {...props} />;
}

function PictureIntroduction({ student, contents, introduction, unitId }: Props) {
  const [index, setIndex] = useState(0);
  const [choice, setChoice] = useState<number | null>(null);
  const [tried, setTried] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const transcriptId = useId();
  const [phase, setPhase] = useState<"idle" | "loading" | "playing" | "paused" | "ended" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const audio = useRef<HTMLAudioElement | null>(null);
  const playAttempt = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const returnPath = textbookContentsPath(contents.book, unitId);
  const presentation = introduction.presentation;
  const finished = index === 4;
  const current = presentation && (index === 1 && choice !== null ? presentation.choices[choice] : presentation.scenes[Math.min(index, 3)]);

  function releaseAudio() {
    playAttempt.current += 1;
    const previous = audio.current;
    audio.current = null;
    if (previous) {
      previous.onplaying = null; previous.onwaiting = null; previous.onended = null;
      previous.onerror = null; previous.ontimeupdate = null;
      previous.pause(); previous.removeAttribute("src"); previous.load();
    }
  }

  useEffect(() => () => {
    const previous = audio.current;
    audio.current = null;
    if (previous) {
      previous.onplaying = null; previous.onwaiting = null; previous.onended = null;
      previous.onerror = null; previous.ontimeupdate = null;
      previous.pause(); previous.removeAttribute("src"); previous.load();
    }
  }, []);

  function startAudio(segment: PictureGuideSegment) {
    releaseAudio();
    const next = new Audio(segment.audio.src);
    const attempt = ++playAttempt.current;
    audio.current = next;
    setProgress(0); setPhase("loading");
    next.onplaying = () => { if (audio.current === next && !next.paused) setPhase("playing"); };
    next.onwaiting = () => { if (audio.current === next && !next.paused) setPhase("loading"); };
    next.onended = () => { if (audio.current === next) { setPhase("ended"); setProgress(1); } };
    next.onerror = () => { if (audio.current === next) setPhase("error"); };
    next.ontimeupdate = () => { if (audio.current === next) setProgress(Math.min(1, next.currentTime / (next.duration || segment.audio.durationSeconds))); };
    void next.play().catch(() => { if (audio.current === next && playAttempt.current === attempt) setPhase("error"); });
  }

  function listen() {
    if (!current) return;
    if (audio.current && (phase === "playing" || phase === "loading")) {
      playAttempt.current += 1;
      audio.current.pause(); setPhase("paused");
    } else if (audio.current && phase === "paused") {
      const active = audio.current;
      const attempt = ++playAttempt.current;
      setPhase("loading");
      void active.play().catch(() => { if (audio.current === active && playAttempt.current === attempt) setPhase("error"); });
    } else startAudio(current);
  }

  function move(next: number) {
    releaseAudio(); setPhase("idle"); setProgress(0); setIndex(next);
    if (presentation && next < 4) startAudio(next === 1 && choice !== null ? presentation.choices[choice] : presentation.scenes[next]);
    requestAnimationFrame(() => heading.current?.focus());
  }

  const playLabel = phase === "playing" || phase === "loading" ? "暂停" : phase === "paused" ? "继续听" : phase === "error" ? "重试播放" : phase === "ended" ? "再听一遍" : "听故事";
  const pagination = presentation && <div className="storybook-pagination" aria-label={`导学进度，${finished ? "已完成" : `第 ${index + 1} 幅，共 4 幅`}`}>
    <span aria-hidden="true">{finished ? "完成" : `${index + 1} / 4`}</span>
    <ol aria-label="导学环节">{steps.map((name, i) => <li key={name} aria-current={index === i ? "step" : undefined} data-past={index > i}><span className="sr-only">{name}</span></li>)}</ol>
  </div>;

  return <SchoolbagShell student={student} className="space-textbooks picture-guide-page storybook-guide"
    navigation={<Link href={returnPath}><ArrowLeft size={21} aria-hidden="true" /><span>返回目录</span></Link>}
    tools={<>{pagination}{current && <button type="button" className="storybook-caption-toggle" aria-label="字幕" aria-pressed={showTranscript} aria-controls={transcriptId} onClick={() => setShowTranscript(value => !value)}><Captions size={21} aria-hidden="true" /><span>字幕</span></button>}</>}>
    <header className="storybook-title"><p>{contents.book.title}</p><h1>{presentation?.title ?? introduction.title}</h1></header>
    {!presentation || !current ? <section className="picture-guide-unavailable"><BookOpen size={40} aria-hidden="true" /><h2>图画和配音正在准备</h2><p>准备好后，就可以一起看图听故事了。</p><Button asChild><Link href={returnPath}>返回教材目录</Link></Button></section> : <section className="storybook-lesson" aria-label="看图听故事">
      <div className="storybook-scene" data-interactive={index === 1} data-speaking={phase === "playing"}>
        <div className="storybook-illustration" key={`${index}:${choice}`}><TextbookPicture art={current.art} landscape /></div>
        {index === 1 && <div className="storybook-explore" role="group" aria-label="点图探索">{presentation.choices.map((item, i) => <button type="button" key={item.caption} aria-pressed={choice === i} onClick={() => { setChoice(i); startAudio(item); }}>
          <TextbookPicture art={item.art} thumbnail /><span>{item.caption}{choice === i && <Check size={17} aria-hidden="true" />}</span>
        </button>)}</div>}
      </div>
      <div className="storybook-player">
        {!finished && <button type="button" onClick={listen} aria-pressed={phase === "playing"} className="storybook-play"><span>{phase === "playing" || phase === "loading" ? <Pause size={26} fill="currentColor" aria-hidden="true" /> : <Play size={26} fill="currentColor" aria-hidden="true" />}</span><b>{playLabel}</b></button>}
        <h2 ref={heading} tabIndex={-1}>{finished ? "带上好奇心，出发！" : current.caption}</h2>
        {finished ? <div className="storybook-finish"><Button asChild><Link href={returnPath}>去看教材<ArrowRight size={22} aria-hidden="true" /></Link></Button><Button variant="quiet" onClick={() => { setChoice(null); setTried(false); move(0); }}><RotateCcw size={18} aria-hidden="true" />再玩一次</Button></div>
          : <div className="storybook-turns">{index > 0 && <button type="button" onClick={() => move(index - 1)} aria-label="上一幅"><ArrowLeft size={22} aria-hidden="true" /></button>}<button type="button" className="storybook-next" onClick={() => move(index + 1)}><span>{index === 3 ? "准备好啦" : "下一幅"}</span><ArrowRight size={30} strokeWidth={1.5} aria-hidden="true" /></button></div>}
      </div>
      {!finished && <div className="storybook-audio-progress" role="progressbar" aria-label="语音播放进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)}><span style={{ width: `${progress * 100}%` }} /></div>}
      {phase === "error" ? <p role="status" className="picture-guide-notice">声音暂时没连上，点“重试播放”再听一次。</p> : phase === "loading" ? <p role="status" className="picture-guide-notice">声音加载中…</p> : null}
      {index === 2 && <button type="button" className="storybook-tried" aria-pressed={tried} onClick={() => setTried(value => !value)}><Check size={22} aria-hidden="true" />{tried ? "我试过啦" : "我来试一试"}</button>}
      <p hidden={!showTranscript} id={transcriptId} className="storybook-transcript">{current.narration}</p>
    </section>}
  </SchoolbagShell>;
}
