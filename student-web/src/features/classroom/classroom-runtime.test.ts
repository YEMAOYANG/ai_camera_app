import { describe, expect, it } from "vitest";

import { classroomPackageFixture } from "@/test/fixtures/classroom";
import {
  classroomPlaybackReducer,
  createPlaybackState,
} from "@/features/classroom/classroom-runtime";

const initialCursor = {
  revision: 0,
  sceneId: classroomPackageFixture.scenes[0].id,
  actionId: classroomPackageFixture.scenes[0].actions[0].id,
  sceneIndex: 0,
  actionIndex: 0,
  sceneCount: classroomPackageFixture.scenes.length,
  progress: 0,
};

describe("classroom playback runtime", () => {
  it("does not auto-play after the first server sync", () => {
    const ready = createPlaybackState(classroomPackageFixture, initialCursor);
    const synced = classroomPlaybackReducer(ready, {
      type: "RUNTIME_SYNCED",
      sceneId: initialCursor.sceneId,
      actionId: initialCursor.actionId,
      cursorRevision: 1,
      completed: false,
      autoResume: false,
    });
    expect(synced.status).toBe("ready");
    expect(classroomPlaybackReducer(synced, { type: "START" }).status).toBe("playing");
  });

  it("runs narration before locking a quiz or interactive action for student input", () => {
    const ready = createPlaybackState(classroomPackageFixture, initialCursor);
    const playing = classroomPlaybackReducer(ready, { type: "START" });
    const narrating = classroomPlaybackReducer(playing, {
      type: "ACTION_STARTED",
      action: { id: "narrate", type: "narrate", text: "先听老师讲完" },
    });
    expect(narrating.status).toBe("playing");
    const waiting = classroomPlaybackReducer(narrating, {
      type: "ACTION_STARTED",
      action: { id: "quiz", type: "await_interaction", interactionRef: "quiz-1" },
    });
    expect(waiting.status).toBe("waiting");
  });
});
