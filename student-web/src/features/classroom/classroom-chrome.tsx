"use client";

import {
  ArrowLeft,
  BookOpenText,
  Check,
  ChevronLeft,
  ChevronRight,
  CirclePause,
  LockKeyhole,
  ListTree,
  LoaderCircle,
  MessageCircleQuestion,
  Play,
  Sparkles,
  Volume2,
  X,
} from "lucide-react";
import Link from "next/link";
import Image from "next/image";

import { MiraMark } from "@/components/student/mira-mark";
import { Button } from "@/components/ui/button";
import type { ClassroomPlaybackStatus } from "@/features/classroom/classroom-runtime";
import type { NarrationPlaybackSource } from "@/features/classroom/speech-controller";
import type { ClassroomScene } from "@/lib/contracts/lesson-package";
import type { LearningTeacherProfile } from "@/lib/contracts/learning";

export function ClassroomHeader({ studentName, title, minutes }: { studentName: string; title: string; minutes: number }) {
  return (
    <header className="classroom-header">
      <Link href="/today" className="focus-ring classroom-back" aria-label="回到今天课程"><ArrowLeft className="size-5" /><span>今天课程</span></Link>
      <div className="classroom-title"><MiraMark compact /><div><p>{studentName}的互动课堂</p><h1>{title}</h1></div></div>
      <p className="classroom-duration"><Sparkles className="size-4" />约 {minutes} 分钟</p>
    </header>
  );
}

export function SceneRail({
  scenes,
  currentSceneId,
  open,
  onClose,
  onSelect,
  unlockedSceneIndex,
}: {
  scenes: ClassroomScene[];
  currentSceneId: string;
  open: boolean;
  onClose: () => void;
  onSelect: (scene: ClassroomScene) => void;
  unlockedSceneIndex: number;
}) {
  return (
    <aside className={`classroom-scene-rail ${open ? "is-open" : ""}`} aria-label="课堂场景">
      <div className="classroom-rail-heading"><div><p>学习路线</p><strong>{scenes.length} 个小场景</strong></div><button type="button" className="focus-ring classroom-rail-close" onClick={onClose} aria-label="收起学习路线"><X className="size-5" /></button></div>
      <ol>
        {scenes.map((scene, index) => {
          const active = scene.id === currentSceneId;
          const locked = index > unlockedSceneIndex;
          const completed = index < unlockedSceneIndex;
          return <li key={scene.id}><button type="button" disabled={locked} onClick={() => onSelect(scene)} className={`focus-ring classroom-scene-button phase-${scene.phaseRole || scene.type} ${active ? "is-active" : ""} ${completed ? "is-completed" : ""} ${locked ? "is-locked" : ""}`} aria-current={active ? "step" : undefined} aria-label={locked ? `${scene.title}，完成前面场景后解锁` : undefined}><span className="classroom-scene-index">{locked ? <LockKeyhole className="size-4" /> : active ? <Play className="size-4 fill-current" /> : completed ? <Check className="size-4" /> : index + 1}</span><span><strong>{scene.title}</strong><small>{locked ? "完成前面场景后解锁" : sceneTypeLabel(scene)}</small></span></button></li>;
        })}
      </ol>
      <div className="classroom-rail-tip"><BookOpenText className="size-5" /><p>跟着 Mira 一步一步来，不用赶时间。</p></div>
    </aside>
  );
}

export function TeacherDock({
  teacher,
  text,
  status,
  audioSource,
  progress,
  onReplay,
}: {
  teacher: LearningTeacherProfile;
  text: string;
  status: ClassroomPlaybackStatus;
  audioSource: NarrationPlaybackSource | "idle";
  progress: number;
  onReplay: () => void;
}) {
  return (
    <aside className="classroom-teacher" aria-label={`${teacher.displayName}讲解`}>
      <div className="classroom-teacher-heading"><div className="classroom-teacher-avatar"><Image src={teacher.avatarPath} width={112} height={112} alt={`${teacher.displayName}头像`} /></div><div><p>{teacher.displayName}</p><span><i className={status === "playing" ? "is-speaking" : ""} />{teacherStatus(status)}</span><small className={`classroom-audio-source source-${audioSource}`}>{audioSourceLabel(audioSource)}</small></div></div>
      <div className="classroom-speech-bubble" aria-live="polite"><MessageCircleQuestion className="size-5 text-[var(--mira-ai)]" /><p>{text}</p></div>
      <button type="button" className="focus-ring classroom-replay" onClick={onReplay}><Volume2 className="size-5" />再听一遍</button>
      <div className="classroom-teacher-progress"><div className="flex items-center justify-between"><span>本节进度</span><strong>{Math.round(progress * 100)}%</strong></div><div><i style={{ width: `${Math.max(4, progress * 100)}%` }} /></div></div>
    </aside>
  );
}

function audioSourceLabel(source: NarrationPlaybackSource | "idle") {
  if (source === "package_audio") return "正式课件音频";
  if (source === "browser_tts_fallback") return "设备朗读（开发降级）";
  if (source === "silent") return "音频暂不可用";
  return "等待课程音频";
}

export function PlaybackControls({
  status,
  sceneNumber,
  sceneCount,
  canPrevious,
  canNext,
  waitingLabel,
  waitingDisabled,
  onToggle,
  onPrevious,
  onNext,
  onContinue,
  onOpenRail,
}: {
  status: ClassroomPlaybackStatus;
  sceneNumber: number;
  sceneCount: number;
  canPrevious: boolean;
  canNext: boolean;
  waitingLabel?: string;
  waitingDisabled?: boolean;
  onToggle: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onContinue: () => void;
  onOpenRail: () => void;
}) {
  const busy = status === "saving";
  return (
    <nav className="classroom-controls" aria-label="课堂播放控制">
      <button type="button" className="focus-ring classroom-mobile-scenes" onClick={onOpenRail}><ListTree className="size-5" /><span>场景</span></button>
      <button type="button" className="focus-ring classroom-control-icon" onClick={onPrevious} disabled={!canPrevious || busy} aria-label="上一个场景"><ChevronLeft className="size-6" /></button>
      <button type="button" className="focus-ring classroom-play" onClick={onToggle} disabled={busy} aria-label={status === "playing" ? "暂停讲解" : "继续讲解"}>{busy ? <LoaderCircle className="size-6 animate-spin" /> : status === "playing" ? <CirclePause className="size-7" /> : <Play className="size-7 fill-current" />}</button>
      <div className="classroom-scene-count"><strong>{sceneNumber}</strong><span>/ {sceneCount}</span></div>
      {waitingLabel ? <Button className="classroom-continue" onClick={onContinue} disabled={waitingDisabled || busy}>{waitingLabel}<ChevronRight className="size-5" /></Button> : <button type="button" className="focus-ring classroom-control-icon" onClick={onNext} disabled={!canNext || busy} aria-label="下一个场景"><ChevronRight className="size-6" /></button>}
    </nav>
  );
}

export function ClassroomBackdrop({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open ? <button type="button" className="classroom-backdrop" onClick={onClose} aria-label="关闭学习路线" /> : null;
}

function sceneTypeLabel(scene: ClassroomScene) {
  if (scene.phaseRole === "teach") return "认识新知识";
  if (scene.phaseRole === "demo") return "看老师示范";
  if (scene.phaseRole === "guided") return "Mira 陪你练";
  if (scene.phaseRole === "independent") return "自己来挑战";
  if (scene.phaseRole === "recap") return "一起回顾";
  if (scene.type === "interactive") return "动手实验";
  if (scene.type === "quiz") return "练一练";
  if (scene.type === "recap") return "小总结";
  if (scene.type === "video") return "看视频";
  return "老师讲";
}

function teacherStatus(status: ClassroomPlaybackStatus) {
  if (status === "playing") return "正在讲解";
  if (status === "paused") return "等你准备好";
  if (status === "waiting") return "轮到你啦";
  if (status === "saving") return "正在保存";
  if (status === "completed") return "这节课完成啦";
  if (status === "error") return "需要再试一次";
  return "准备开课";
}
