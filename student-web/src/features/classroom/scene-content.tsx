"use client";

import { Check, Film, LoaderCircle, PartyPopper, Sparkles } from "lucide-react";
import { useCallback } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { ControlledSlideScene } from "@/features/classroom/controlled-slide-scene";
import { InteractiveFrame } from "@/features/classroom/interactive-frame";
import type { WidgetMessage } from "@/features/classroom/interactive-protocol";
import { MatchPairsScene } from "@/features/classroom/match-pairs-scene";
import { ClassroomQuizScene } from "@/features/classroom/quiz-scene";
import { SlideScene } from "@/features/classroom/slide-scene";
import { SortOrderScene } from "@/features/classroom/sort-order-scene";
import type { ClassroomScene } from "@/lib/contracts/lesson-package";
import type { LearningAnswerResponse, LearningQuestion, LearningSession, LearningTeacherProfile } from "@/lib/contracts/learning";

type SubmitAnswer = (
  sessionId: string,
  body: { answer?: string | string[]; response?: unknown },
) => Promise<LearningAnswerResponse>;

export function ClassroomSceneContent({
  scene,
  focusTarget,
  session,
  question,
  teacher,
  onSession,
  onQuestion,
  onInteractionComplete,
  onQuizComplete,
  quizEnabled,
  submitAnswer,
}: {
  scene: ClassroomScene;
  focusTarget?: string;
  session: LearningSession;
  question: LearningQuestion | null;
  teacher: LearningTeacherProfile;
  onSession: (session: LearningSession) => void;
  onQuestion: (question: LearningQuestion | null) => void;
  onInteractionComplete: (payload: Record<string, unknown>) => void;
  onQuizComplete: () => void;
  quizEnabled: boolean;
  submitAnswer?: SubmitAnswer;
}) {
  const receiveWidgetMessage = useCallback((message: WidgetMessage) => {
    if (message.kind === "complete") onInteractionComplete(message.payload || { completed: true });
  }, [onInteractionComplete]);

  if (scene.type === "slide") {
    return scene.layoutTemplate
      ? <ControlledSlideScene scene={scene} teacher={teacher} focusTarget={focusTarget} />
      : <SlideScene scene={scene} focusTarget={focusTarget} />;
  }
  if (scene.type === "interactive") {
    const controlledTemplate = scene.widgetTemplate;
    if (controlledTemplate) {
      if (controlledTemplate === "match_pairs.v1") {
        return <MatchPairsScene session={session} question={question} enabled={quizEnabled} questionRefs={scene.questionRefs} gameRules={scene.gameRules} submitAnswer={submitAnswer} onSession={onSession} onQuestion={onQuestion} onQuizComplete={() => onInteractionComplete({ completed: true, questionRefs: scene.questionRefs })} />;
      }
      if (controlledTemplate === "sort_order.v1") {
        return <SortOrderScene session={session} question={question} enabled={quizEnabled} questionRefs={scene.questionRefs} gameRules={scene.gameRules} submitAnswer={submitAnswer} onSession={onSession} onQuestion={onQuestion} onQuizComplete={() => onInteractionComplete({ completed: true, questionRefs: scene.questionRefs })} />;
      }
      return <ClassroomQuizScene session={session} question={question} teacher={teacher} guided enabled={quizEnabled} questionRefs={scene.questionRefs} presentation={controlledTemplate} gameRules={scene.gameRules} submitAnswer={submitAnswer} onSession={onSession} onQuestion={onQuestion} onQuizComplete={() => onInteractionComplete({ completed: true, questionRefs: scene.questionRefs })} />;
    }
    return <InteractiveFrame key={scene.id} sceneId={scene.id} title={scene.title} html={scene.html} templateId={legacyTemplateId(scene.templateId)} instructions={scene.instructions} onMessage={receiveWidgetMessage} />;
  }
  if (scene.type === "quiz") {
    return <ClassroomQuizScene session={session} question={question} teacher={teacher} guided={scene.mode !== "independent"} enabled={quizEnabled} questionRefs={scene.questionRefs} submitAnswer={submitAnswer} onSession={onSession} onQuestion={onQuestion} onQuizComplete={onQuizComplete} />;
  }
  if (scene.type === "video") {
    return <VideoScene scene={scene} />;
  }
  return <RecapScene scene={scene} />;
}

function legacyTemplateId(templateId: Extract<ClassroomScene, { type: "interactive" }>["templateId"]) {
  return templateId === "tap_choice.v1" || templateId === "match_pairs.v1" || templateId === "sort_order.v1" || templateId === "slider_lab.v1"
    ? templateId
    : undefined;
}

function RecapScene({ scene }: { scene: Extract<ClassroomScene, { type: "recap" }> }) {
  return (
    <section className="classroom-recap">
      <div className="classroom-recap-burst" aria-hidden="true"><Sparkles /><PartyPopper /></div>
      <MiraBuddy mood="celebrate" className="mx-auto w-36" label="Mira 为你庆祝" />
      <p className="classroom-recap-label">一起回顾</p>
      <h2>{scene.title}</h2>
      <p className="classroom-recap-say">{scene.sayText}</p>
      {scene.keyPoints.length ? <ul>{scene.keyPoints.map((point) => <li key={point}><Check className="size-5" />{point}</li>)}</ul> : null}
    </section>
  );
}

function VideoScene({ scene }: { scene: Extract<ClassroomScene, { type: "video" }> }) {
  const videoUrl = scene.assetRef.startsWith("asset:") ? `/api/learning/assets/${encodeURIComponent(scene.assetRef.slice(6))}` : scene.assetRef;
  const posterUrl = scene.posterRef?.startsWith("asset:") ? `/api/learning/assets/${encodeURIComponent(scene.posterRef.slice(6))}` : scene.posterRef;
  const captionsUrl = scene.captionsRef?.startsWith("asset:") ? `/api/learning/assets/${encodeURIComponent(scene.captionsRef.slice(6))}` : scene.captionsRef;
  return (
    <div className="classroom-video-scene">
      <div className="classroom-video-label"><Film className="size-5" />看一小段，再告诉 Mira 你发现了什么</div>
      {videoUrl.startsWith("/api/learning/assets/") ? <video controls playsInline preload="metadata" poster={posterUrl} className="size-full rounded-[20px] bg-[#101827]" aria-label={scene.title}>{captionsUrl ? <track kind="captions" src={captionsUrl} srcLang="zh" label="中文字幕" default /> : null}</video> : <div className="grid min-h-[340px] place-items-center bg-[var(--mira-bg)]"><p className="flex items-center gap-2 font-bold text-[var(--mira-muted)]"><LoaderCircle className="size-5 animate-spin" />视频正在准备中</p></div>}
    </div>
  );
}
