import type { ClassroomAction, ClassroomCursor, ClassroomScene, LessonPackageV2 } from "@/lib/contracts/lesson-package";

export type ClassroomPlaybackStatus = "ready" | "playing" | "paused" | "waiting" | "saving" | "completed" | "error";

export type ClassroomPlaybackState = {
  status: ClassroomPlaybackStatus;
  sceneId: string;
  actionId: string | null;
  cursorRevision: number;
  focusTarget?: string;
  teacherText: string;
  interactionCompleted: boolean;
  error?: string;
};

export type ClassroomPlaybackEvent =
  | { type: "START" }
  | { type: "PAUSE" }
  | { type: "RESUME" }
  | { type: "SCENE_SELECTED"; sceneId: string; actionId: string | null; cursorRevision: number; teacherText: string }
  | { type: "ACTION_STARTED"; action: ClassroomAction }
  | { type: "INTERACTION_COMPLETED" }
  | { type: "SAVING" }
  | { type: "RUNTIME_SYNCED"; sceneId: string; actionId: string | null; cursorRevision: number; completed: boolean; autoResume: boolean }
  | { type: "FAILED"; message: string };

export function createPlaybackState(
  classroom: LessonPackageV2,
  cursor: ClassroomCursor,
): ClassroomPlaybackState {
  const scene = classroom.scenes.find((item) => item.id === cursor.sceneId) || orderedScenes(classroom)[0];
  const action = cursor.actionId ? scene.actions.find((item) => item.id === cursor.actionId) : scene.actions[cursor.actionIndex];
  return {
    status: "ready",
    sceneId: scene.id,
    actionId: action?.id || null,
    cursorRevision: cursor.revision,
    teacherText: narrationForScene(scene),
    interactionCompleted: false,
  };
}

export function classroomPlaybackReducer(
  state: ClassroomPlaybackState,
  event: ClassroomPlaybackEvent,
): ClassroomPlaybackState {
  switch (event.type) {
    case "START":
    case "RESUME":
      return { ...state, status: "playing", error: undefined };
    case "PAUSE":
      return { ...state, status: "paused" };
    case "SCENE_SELECTED":
      return {
        ...state,
        status: "paused",
        sceneId: event.sceneId,
        actionId: event.actionId,
        cursorRevision: event.cursorRevision,
        focusTarget: undefined,
        teacherText: event.teacherText,
        interactionCompleted: false,
        error: undefined,
      };
    case "ACTION_STARTED":
      return {
        ...state,
        status: event.action.type === "await_continue" || event.action.type === "await_interaction" || event.action.type === "play_media" ? "waiting" : state.status,
        actionId: event.action.id,
        focusTarget: event.action.type === "focus" ? event.action.targetId : state.focusTarget,
        teacherText: event.action.type === "narrate" ? event.action.text : state.teacherText,
      };
    case "INTERACTION_COMPLETED":
      return { ...state, interactionCompleted: true, teacherText: "做得真棒！这个小实验已经完成了。" };
    case "SAVING":
      return { ...state, status: "saving" };
    case "RUNTIME_SYNCED":
      return {
        ...state,
        status: event.completed
          ? "completed"
          : event.autoResume
            ? "playing"
            : state.status === "ready"
              ? "ready"
              : "paused",
        sceneId: event.sceneId,
        actionId: event.actionId,
        cursorRevision: event.cursorRevision,
        focusTarget: event.sceneId === state.sceneId ? state.focusTarget : undefined,
        interactionCompleted: event.sceneId === state.sceneId && state.interactionCompleted,
        error: undefined,
      };
    case "FAILED":
      return { ...state, status: "error", error: event.message };
  }
}

export function orderedScenes(classroom: LessonPackageV2) {
  return [...classroom.scenes].sort((left, right) => left.order - right.order);
}

export function currentScene(classroom: LessonPackageV2, sceneId: string): ClassroomScene {
  return classroom.scenes.find((scene) => scene.id === sceneId) || orderedScenes(classroom)[0];
}

export function currentAction(scene: ClassroomScene, actionId: string | null) {
  return (actionId ? scene.actions.find((action) => action.id === actionId) : undefined) || null;
}

export function narrationForScene(scene: ClassroomScene) {
  const narration = scene.actions.find((action) => action.type === "narrate");
  if (narration?.type === "narrate") return narration.text;
  if (scene.type === "recap") return scene.sayText;
  if (scene.type === "interactive") return scene.instructions || "动手试一试，Mira 会在旁边陪着你。";
  if (scene.type === "quiz") return scene.mode === "independent" ? "现在自己试试看，相信你可以。" : "我们一起练一练，不着急。";
  return "先看一看这一页，找到今天最重要的线索。";
}
