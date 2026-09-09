"use client";

import { AlertCircle, LoaderCircle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ClassroomBackdrop,
  ClassroomHeader,
  PlaybackControls,
  SceneRail,
  TeacherDock,
} from "@/features/classroom/classroom-chrome";
import {
  classroomPlaybackReducer,
  createPlaybackState,
  currentAction,
  currentScene,
  narrationForScene,
  orderedScenes,
} from "@/features/classroom/classroom-runtime";
import { ClassroomSceneContent } from "@/features/classroom/scene-content";
import { classroomStagePresentation } from "@/features/classroom/classroom-stage-presentation";
import {
  createClassroomAudioController,
  type NarrationPlaybackSource,
} from "@/features/classroom/speech-controller";
import {
  completeClassroomAction,
  getClassroomRuntime,
  getLearningTeachers,
  LearningClientError,
} from "@/features/learning/learning-client";
import { teacherForSubject } from "@/features/learning/teacher-registry";
import type { ClassroomRuntimeResponse } from "@/lib/contracts/lesson-package";
import type { LearningQuestion, LearningStartResponse, LearningTeacherProfile } from "@/lib/contracts/learning";
import type { Student } from "@/lib/contracts/student-session";

export function ClassroomPlayer({ student, start }: { student: Student; start: LearningStartResponse }) {
  if (!start.classroom || !start.cursor || !start.package) return null;
  return <ClassroomPlayerReady student={student} start={start as Required<Pick<LearningStartResponse, "classroom" | "cursor" | "package">> & LearningStartResponse} />;
}

function ClassroomPlayerReady({
  student,
  start,
}: {
  student: Student;
  start: LearningStartResponse & Required<Pick<LearningStartResponse, "classroom" | "cursor" | "package">>;
}) {
  const classroom = start.classroom;
  const stagePresentation = classroomStagePresentation(
    start.lesson.subject,
    classroom.sourceCourse?.gradeCode || start.lesson.gradeCode,
  );
  const scenes = useMemo(() => orderedScenes(classroom), [classroom]);
  const [playback, dispatch] = useReducer(classroomPlaybackReducer, undefined, () => createPlaybackState(classroom, start.cursor));
  const [learningSession, setLearningSession] = useState(start.session);
  const [question, setQuestion] = useState<LearningQuestion | null>(start.session.currentQuestion);
  const [runtime, setRuntime] = useState<ClassroomRuntimeResponse | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  const [interactionResult, setInteractionResult] = useState<Record<string, unknown> | null>(null);
  const [teacher, setTeacher] = useState<LearningTeacherProfile>(() => teacherForSubject(null, start.lesson.subject));
  const [audioSource, setAudioSource] = useState<NarrationPlaybackSource | "idle">("idle");
  const runRef = useRef(0);
  const replayRef = useRef<AbortController | null>(null);
  const completionKeys = useRef(new Map<string, string>());
  const completionInFlight = useRef<string | null>(null);
  const audio = useMemo(() => createClassroomAudioController(), []);
  const scene = currentScene(classroom, playback.sceneId);
  const action = currentAction(scene, playback.actionId);
  const sceneIndex = scenes.findIndex((item) => item.id === scene.id);
  const progress = runtime?.cursor.progress ?? Math.min(1, sceneIndex / Math.max(1, scenes.length - 1));

  const syncRuntime = useCallback((value: ClassroomRuntimeResponse, autoResume = false) => {
    setRuntime(value);
    setInteractionResult(null);
    dispatch({
      type: "RUNTIME_SYNCED",
      sceneId: value.cursor.sceneId,
      actionId: value.action?.id || value.cursor.actionId || null,
      cursorRevision: value.cursor.revision,
      completed: value.completed,
      autoResume,
    });
  }, []);

  const reloadRuntime = useCallback(async () => {
    const controller = new AbortController();
    try {
      syncRuntime(await getClassroomRuntime(start.session.id, controller.signal), false);
    } catch (error) {
      if (error instanceof LearningClientError && error.code === "learning_classroom_not_available") return;
      dispatch({ type: "FAILED", message: error instanceof Error ? error.message : "课堂进度没有同步成功" });
    }
    return () => controller.abort();
  }, [start.session.id, syncRuntime]);

  useEffect(() => {
    const controller = new AbortController();
    void getClassroomRuntime(start.session.id, controller.signal)
      .then((value) => syncRuntime(value, false))
      .catch((error: unknown) => {
        if (controller.signal.aborted || (error instanceof LearningClientError && error.code === "learning_classroom_not_available")) return;
        dispatch({ type: "FAILED", message: error instanceof Error ? error.message : "课堂进度没有同步成功" });
      });
    return () => {
      controller.abort();
      runRef.current += 1;
      replayRef.current?.abort();
      audio.stop();
    };
  }, [audio, start.session.id, syncRuntime]);

  useEffect(() => {
    let active = true;
    void getLearningTeachers(start.lesson.subject as "chinese" | "math" | "english")
      .then((value) => {
        if (active) setTeacher(teacherForSubject(value.selected?.id, start.lesson.subject, value.items));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [start.lesson.subject]);

  const finishAction = useCallback(async (
    actionId: string,
    result: Record<string, unknown> = {},
  ) => {
    if (completionInFlight.current === actionId) return;
    completionInFlight.current = actionId;
    dispatch({ type: "SAVING" });
    const key = completionKeys.current.get(actionId) || createIdempotencyKey(start.session.id, actionId);
    completionKeys.current.set(actionId, key);
    try {
      const next = await completeClassroomAction(start.session.id, actionId, {
        cursorRevision: playback.cursorRevision,
        idempotencyKey: key,
        result,
      });
      syncRuntime(next, true);
    } catch (error) {
      if (error instanceof LearningClientError && error.code === "learning_cursor_conflict") {
        await reloadRuntime();
      } else {
        dispatch({ type: "FAILED", message: error instanceof Error ? error.message : "这一步暂时没有保存成功" });
      }
    } finally {
      completionInFlight.current = null;
    }
  }, [playback.cursorRevision, reloadRuntime, start.session.id, syncRuntime]);

  useEffect(() => {
    if (playback.status !== "playing" || !action) return;
    const executingAction = action;
    const run = ++runRef.current;
    const controller = new AbortController();
    dispatch({ type: "ACTION_STARTED", action: executingAction });
    async function execute() {
      try {
        if (executingAction.type === "narrate") {
          const result = await audio.playNarration({
            text: executingAction.text,
            audioAssetRef: executingAction.audioAssetRef,
            teacher,
            onSource: setAudioSource,
          }, controller.signal);
          if (run === runRef.current) await finishAction(executingAction.id, result);
        } else if (executingAction.type === "focus") {
          await delay(650, controller.signal);
          if (run === runRef.current) await finishAction(executingAction.id, { viewed: true });
        } else if (executingAction.type === "complete_scene") {
          await finishAction(executingAction.id);
        }
      } catch (error) {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          dispatch({ type: "FAILED", message: error instanceof Error ? error.message : "老师的讲解暂停了" });
        }
      }
    }
    void execute();
    return () => controller.abort();
  }, [action, audio, finishAction, playback.status, teacher]);

  const authoritativeSceneIndex = runtime?.cursor.sceneIndex ?? start.cursor.sceneIndex;

  function selectScene(selectedScene: typeof scene) {
    const selectedIndex = scenes.findIndex((candidate) => candidate.id === selectedScene.id);
    if (selectedIndex > authoritativeSceneIndex) return;
    runRef.current += 1;
    replayRef.current?.abort();
    audio.stop();
    const selectedAction = selectedIndex === authoritativeSceneIndex
      ? (runtime?.action || selectedScene.actions.find((candidate) => candidate.id === runtime?.cursor.actionId) || selectedScene.actions[0] || null)
      : null;
    dispatch({
      type: "SCENE_SELECTED",
      sceneId: selectedScene.id,
      actionId: selectedAction?.id || null,
      cursorRevision: playback.cursorRevision,
      teacherText: narrationForScene(selectedScene),
    });
    setRailOpen(false);
  }

  function moveScene(delta: number) {
    const next = scenes[sceneIndex + delta];
    if (next) selectScene(next);
  }

  const onInteractionComplete = useCallback((result: Record<string, unknown>) => {
    setInteractionResult(result);
    dispatch({ type: "INTERACTION_COMPLETED" });
  }, []);

  function continueWaiting() {
    if (!action) return;
    if (action.type === "await_interaction") void finishAction(action.id, interactionResult || { completed: true });
    else if (action.type === "await_continue") void finishAction(action.id);
    else if (action.type === "play_media") void finishAction(action.id, { watchRatio: 1 });
  }

  function handleQuizComplete() {
    if (action?.type === "await_interaction") void finishAction(action.id, { completed: true });
    else {
      const completion = scene.actions.find((item) => item.type === "complete_scene");
      if (completion) void finishAction(completion.id);
      else moveScene(1);
    }
  }

  function togglePlayback() {
    runRef.current += 1;
    if (playback.status === "playing") {
      audio.stop();
      dispatch({ type: "PAUSE" });
    } else {
      dispatch({ type: playback.status === "ready" ? "START" : "RESUME" });
    }
  }

  function replayTeacher() {
    runRef.current += 1;
    replayRef.current?.abort();
    audio.stop();
    if (playback.status === "playing") dispatch({ type: "PAUSE" });
    const controller = new AbortController();
    replayRef.current = controller;
    const narration = scene.actions.find((candidate) => (
      candidate.type === "narrate" && candidate.text === playback.teacherText
    ));
    void audio.playNarration({
      text: playback.teacherText,
      audioAssetRef: narration?.type === "narrate" ? narration.audioAssetRef : undefined,
      teacher,
      onSource: setAudioSource,
    }, controller.signal).catch(() => undefined);
  }

  const waitingLabel = action?.type === "await_interaction"
    ? interactionResult ? (scene.type === "interactive" ? "完成练习" : "保存练习") : "先完成练习"
    : action?.type === "await_continue"
      ? "我看懂了"
      : action?.type === "play_media"
        ? "视频看完了"
        : undefined;

  return (
    <div className={`classroom-page ${stagePresentation.subjectClass} ${stagePresentation.gradeBandClass}`}>
      <ClassroomHeader studentName={student.displayName} title={classroom.title} minutes={classroom.estimatedMinutes} />
      <div className="classroom-layout">
        <SceneRail scenes={scenes} currentSceneId={scene.id} unlockedSceneIndex={authoritativeSceneIndex} open={railOpen} onClose={() => setRailOpen(false)} onSelect={selectScene} />
        <main id="main-content" className="classroom-main">
          <div className="classroom-scene-meta"><span>{scenePhaseLabel(scene)}</span><strong>{scene.title}</strong><small className="classroom-stage-identity">{stagePresentation.stageCopy}</small></div>
          <div className={`classroom-stage classroom-stage-${scene.type}`}>
            <ClassroomSceneContent scene={scene} focusTarget={playback.focusTarget} session={learningSession} question={question} teacher={teacher} quizEnabled={scene.type !== "quiz" || action?.type === "await_interaction"} onSession={setLearningSession} onQuestion={setQuestion} onInteractionComplete={onInteractionComplete} onQuizComplete={handleQuizComplete} />
          </div>
          {playback.error ? <div className="classroom-error" role="alert"><AlertCircle className="size-5" /><p>{playback.error}</p><Button variant="secondary" size="compact" onClick={() => void reloadRuntime()}><RefreshCw className="size-4" />同步进度</Button></div> : null}
          <div className="classroom-companion-row">
            <TeacherDock teacher={teacher} text={playback.teacherText} status={playback.status} audioSource={audioSource} progress={progress} onReplay={replayTeacher} />
            <PlaybackControls status={playback.status} sceneNumber={sceneIndex + 1} sceneCount={scenes.length} canPrevious={sceneIndex > 0} canNext={sceneIndex < authoritativeSceneIndex} waitingLabel={waitingLabel} waitingDisabled={action?.type === "await_interaction" && !interactionResult} onToggle={togglePlayback} onPrevious={() => moveScene(-1)} onNext={() => moveScene(1)} onContinue={continueWaiting} onOpenRail={() => setRailOpen(true)} />
          </div>
        </main>
      </div>
      <ClassroomBackdrop open={railOpen} onClose={() => setRailOpen(false)} />
    </div>
  );
}

function scenePhaseLabel(scene: ReturnType<typeof currentScene>) {
  if (scene.phaseRole === "teach") return "先认识";
  if (scene.phaseRole === "demo") return "看示范";
  if (scene.phaseRole === "guided") return "一起练";
  if (scene.phaseRole === "independent") return "自己做";
  if (scene.phaseRole === "recap") return "回顾";
  if (scene.type === "interactive") return "动手练";
  if (scene.type === "quiz") return "练习时间";
  if (scene.type === "video") return "视频课件";
  return "Mira 正在讲";
}

export function ClassroomBooting() {
  return <main id="main-content" className="grid min-h-screen place-items-center"><p className="flex items-center gap-3 rounded-full bg-white px-5 py-3 font-extrabold text-[var(--mira-muted)] shadow-sm"><LoaderCircle className="size-5 animate-spin text-[var(--mira-brand)]" />Mira 正在打开互动课堂</p></main>;
}

function createIdempotencyKey(sessionId: string, actionId: string) {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${sessionId}:${actionId}:${random}`;
}

function delay(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("课堂动作已停止", "AbortError"));
    }, { once: true });
  });
}
