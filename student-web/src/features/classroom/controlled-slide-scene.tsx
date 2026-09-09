"use client";

import { ArrowRight, BookOpenCheck, Lightbulb, Volume2 } from "lucide-react";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { ControlledVisualAids } from "@/features/classroom/controlled-visual-aids";
import {
  createClassroomAudioController,
  type NarrationPlaybackSource,
} from "@/features/classroom/speech-controller";
import type { ClassroomScene } from "@/lib/contracts/lesson-package";
import type { LearningTeacherProfile } from "@/lib/contracts/learning";

type ControlledSlide = Extract<ClassroomScene, { type: "slide" }>;
type ControlledTextBlock = Extract<ControlledSlide["blocks"][number], { type: "text" }>;

export function ControlledSlideScene({
  scene,
  teacher,
  focusTarget,
}: {
  scene: ControlledSlide;
  teacher: LearningTeacherProfile;
  focusTarget?: string;
}) {
  if (scene.layoutTemplate === "phonics_focus.v1") return <PhonicsFocusScene scene={scene} teacher={teacher} focusTarget={focusTarget} />;
  if (scene.layoutTemplate === "worked_example.v1") return <WorkedExampleScene scene={scene} focusTarget={focusTarget} />;
  return <ConceptFocusScene scene={scene} focusTarget={focusTarget} />;
}

function PhonicsFocusScene({ scene, teacher, focusTarget }: { scene: ControlledSlide; teacher: LearningTeacherProfile; focusTarget?: string }) {
  const audio = useMemo(() => createClassroomAudioController(), []);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [playbackSource, setPlaybackSource] = useState<NarrationPlaybackSource | "idle">("idle");
  const [audioProgress, setAudioProgress] = useState(0);
  const focusItems = scene.templateData?.focusItems || [];
  const teacherBlock = textBlockEntries(scene, "teacher")[0];
  const teacherCopy = teacherBlock?.text || "先听发音，再看嘴巴的样子。";
  const keyPointBlocks = textBlockEntries(scene, "key_point");
  const keyPoints = keyPointBlocks.map((block) => block.text);

  useEffect(() => () => audio.stop(), [audio]);

  async function speak(item: (typeof focusItems)[number]) {
    audio.stop();
    setSpeakingId(item.id);
    setAudioProgress(0);
    setPlaybackSource("idle");
    const controller = new AbortController();
    try {
      await audio.playNarration({
        text: `${item.label}。${item.mouthCue}`,
        audioAssetRef: item.audioAssetRef,
        teacher,
        onSource: setPlaybackSource,
        onProgress: setAudioProgress,
      }, controller.signal);
    } catch {
      // A stopped utterance is expected when the child taps another sound.
    } finally {
      setSpeakingId((current) => current === item.id ? null : current);
    }
  }

  return (
    <section className="controlled-slide phonics-focus" aria-labelledby={`${scene.id}-title`} data-spotlight-active={spotlightActive(scene, focusTarget)}>
      <div className="controlled-slide-copy">
        <p className="controlled-eyebrow"><BookOpenCheck className="size-5" />第一步 · 认识新朋友</p>
        <h2 id={`${scene.id}-title`}>{scene.title}</h2>
        <p className="controlled-teacher-copy" data-focus-id={teacherBlock?.id} data-spotlight-target={spotlightTarget(teacherBlock?.id, focusTarget)}>{teacherCopy}</p>
        <div className="controlled-instruction"><Volume2 className="size-5" /><span>点字母，跟着读</span></div>
      </div>
      <div className="phonics-focus-grid" aria-label="单韵母发音卡">
        {focusItems.map((item, index) => (
          <button
            key={item.id}
            type="button"
            className={`focus-ring phonics-focus-card tone-${index + 1} ${speakingId === item.id ? "is-speaking" : ""}`}
            data-focus-id={keyPointBlocks[index]?.id}
            data-spotlight-target={spotlightTarget(keyPointBlocks[index]?.id, focusTarget)}
            onClick={() => void speak(item)}
            aria-label={`听 ${item.label} 的发音，${item.mouthCue}`}
          >
            <MouthCueIllustration
              label={item.label}
              cue={item.mouthCue}
              officialPlaying={speakingId === item.id && playbackSource === "package_audio"}
              progress={audioProgress}
            />
            <span className="phonics-letter">{item.label}</span>
            <span className="phonics-mouth-cue">{compactMouthCue(item.mouthCue)}</span>
            <span className={`phonics-listen ${item.audioAssetRef ? "is-official" : "is-fallback"}`}><Volume2 className="size-5" />{phonicsAudioLabel(item.audioAssetRef, speakingId === item.id ? playbackSource : "idle")}</span>
          </button>
        ))}
      </div>
      {keyPoints.length ? (
        <ul className="controlled-key-points" aria-label="发音小窍门">
          {keyPoints.slice(0, 3).map((point) => <li key={point}><Lightbulb className="size-5" />{point}</li>)}
        </ul>
      ) : null}
    </section>
  );
}

function MouthCueIllustration({
  label,
  cue,
  officialPlaying,
  progress,
}: {
  label: string;
  cue: string;
  officialPlaying: boolean;
  progress: number;
}) {
  const vowel = /^[aoe]$/i.test(label.trim()) ? label.trim().toLowerCase() : "other";
  const pulse = officialPlaying ? 0.9 + Math.abs(Math.sin(progress * Math.PI * 8)) * 0.22 : 1;
  const style = { "--mouth-timeline-scale": String(pulse) } as CSSProperties;
  return (
    <span className={`phonics-mouth-illustration mouth-${vowel} ${officialPlaying ? "is-timeline-playing" : ""}`} style={style} role="img" aria-label={`口型示意：${label}，${compactMouthCue(cue)}`}>
      <svg viewBox="0 0 120 92" aria-hidden="true" focusable="false">
        <path className="mouth-face" d="M20 48c0-24 17-39 40-39s40 15 40 39c0 23-17 36-40 36S20 71 20 48Z" />
        <path className="mouth-eye" d="M39 39c3-4 7-4 10 0M71 39c3-4 7-4 10 0" />
        {vowel === "a" ? <ellipse className="mouth-shape mouth-shape-a" cx="60" cy="62" rx="16" ry="17" /> : null}
        {vowel === "o" ? <ellipse className="mouth-shape mouth-shape-o" cx="60" cy="61" rx="13" ry="14" /> : null}
        {vowel === "e" ? <path className="mouth-shape mouth-shape-e" d="M36 60c8-8 40-8 48 0-8 12-40 12-48 0Z" /> : null}
        {vowel === "other" ? <path className="mouth-shape mouth-shape-other" d="M45 62c8 6 22 6 30 0" /> : null}
      </svg>
      <small>口型示意</small>
    </span>
  );
}

function phonicsAudioLabel(audioAssetRef: string | undefined, source: NarrationPlaybackSource | "idle") {
  if (source === "package_audio") return "标准课件音频";
  if (source === "browser_tts_fallback" || source === "silent") return "设备朗读（开发降级）";
  return audioAssetRef ? "听标准课件音频" : "设备朗读（开发降级）";
}

function WorkedExampleScene({ scene, focusTarget }: { scene: ControlledSlide; focusTarget?: string }) {
  const promptBlock = textBlockEntries(scene, "question")[0];
  const explanationBlock = textBlockEntries(scene, "worked_answer")[0];
  const prompt = scene.templateData?.prompt || promptBlock?.text || textBlocks(scene)[0] || scene.title;
  const explanation = scene.templateData?.explanation || explanationBlock?.text || textBlocks(scene)[1] || "先听声音，再观察字母的样子。";
  return (
    <section className="controlled-slide worked-example" aria-labelledby={`${scene.id}-title`} data-spotlight-active={spotlightActive(scene, focusTarget)}>
      <div className="worked-example-heading">
        <div>
          <p className="controlled-eyebrow"><BookOpenCheck className="size-5" />第二步 · 看老师示范</p>
          <h2 id={`${scene.id}-title`}>{scene.title}</h2>
        </div>
        <MiraBuddy mood="reading" className="w-28" label="Mira 正在示范" />
      </div>
      <div className="worked-example-flow">
        <div className="worked-example-question" data-focus-id={promptBlock?.id} data-spotlight-target={spotlightTarget(promptBlock?.id, focusTarget)}><span>先听题目</span><strong>{prompt}</strong></div>
        <ArrowRight className="worked-example-arrow size-8" aria-hidden="true" />
        <div className="worked-example-answer" data-focus-id={explanationBlock?.id} data-spotlight-target={spotlightTarget(explanationBlock?.id, focusTarget)}><span>老师这样想</span><p>{explanation}</p></div>
      </div>
      <p className="controlled-stage-note"><Lightbulb className="size-5" />先看懂方法，不急着做题。</p>
    </section>
  );
}

function ConceptFocusScene({ scene, focusTarget }: { scene: ControlledSlide; focusTarget?: string }) {
  const blocks = textBlockEntries(scene);
  const teacherBlock = textBlockEntries(scene, "teacher")[0] || blocks[0];
  const keyPointBlocks = textBlockEntries(scene, "key_point");
  const visualAids = scene.templateData?.visualAids || [];
  return (
    <section className={`controlled-slide concept-focus ${visualAids.length ? "has-visual-aids" : ""}`} aria-labelledby={`${scene.id}-title`} data-spotlight-active={spotlightActive(scene, focusTarget)}>
      <p className="controlled-eyebrow"><BookOpenCheck className="size-5" />先学一个新方法</p>
      <h2 id={`${scene.id}-title`}>{scene.title}</h2>
      {teacherBlock ? <p className="controlled-teacher-copy" data-focus-id={teacherBlock.id} data-spotlight-target={spotlightTarget(teacherBlock.id, focusTarget)}>{teacherBlock.text}</p> : null}
      {visualAids.length ? <ControlledVisualAids aids={visualAids} /> : null}
      <ul className="concept-focus-grid">
        {keyPointBlocks.slice(0, 3).map((point, index) => <li key={point.id} data-focus-id={point.id} data-spotlight-target={spotlightTarget(point.id, focusTarget)}><span>{index + 1}</span><p>{point.text}</p></li>)}
      </ul>
    </section>
  );
}

function textBlockEntries(scene: ControlledSlide, styleToken?: string): ControlledTextBlock[] {
  return scene.blocks.filter((block): block is ControlledTextBlock => (
    block.type === "text" && (!styleToken || block.styleToken === styleToken)
  ));
}

function textBlocks(scene: ControlledSlide, styleToken?: string) {
  return textBlockEntries(scene, styleToken).map((block) => block.text);
}

function spotlightActive(scene: ControlledSlide, focusTarget?: string) {
  return focusTarget && scene.blocks.some((block) => block.id === focusTarget) ? "true" : undefined;
}

function spotlightTarget(elementId?: string, focusTarget?: string) {
  return elementId && elementId === focusTarget ? "true" : undefined;
}

function compactMouthCue(value: string) {
  return value.replace(/\s+[a-zA-Z](?:\s+[a-zA-Z]){1,3}\s*$/, "").trim() || value;
}
