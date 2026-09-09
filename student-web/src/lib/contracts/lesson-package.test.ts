import { describe, expect, it } from "vitest";

import { classroomPackageFixture } from "@/test/fixtures/classroom";
import { parseOpenMaicCanvas } from "@/features/classroom/openmaic-canvas";
import {
  classroomRuntimeResponseSchema,
  lessonPackageV2Schema,
} from "@/lib/contracts/lesson-package";

describe("lesson package v2 contract", () => {
  it("accepts the controlled five-phase package without executable content", () => {
    const parsed = lessonPackageV2Schema.parse(classroomPackageFixture);
    const slideScene = parsed.scenes.find((scene) => scene.type === "slide");
    const interactiveScene = parsed.scenes.find((scene) => scene.type === "interactive");
    expect(slideScene?.type).toBe("slide");
    expect(interactiveScene?.type).toBe("interactive");
    if (slideScene?.type !== "slide") throw new Error("missing slide fixture");
    if (interactiveScene?.type !== "interactive") throw new Error("missing interactive fixture");
    expect(slideScene.layoutTemplate).toBe("phonics_focus.v1");
    expect(slideScene.templateData?.focusItems?.map((item) => item.label)).toEqual(["a", "o", "e"]);
    expect(slideScene.templateData?.focusItems?.every((item) => item.audioAssetRef?.startsWith("asset:"))).toBe(true);
    expect(slideScene.actions.find((action) => action.type === "narrate" && action.audioAssetRef)?.type).toBe("narrate");
    expect(interactiveScene.widgetTemplate).toBe("listen_tap_choice.v1");
    expect(interactiveScene.questionRefs).toEqual(["q2", "q3"]);
    expect(interactiveScene.html).toBeUndefined();
    expect(slideScene.canvas).toBeUndefined();
    expect(parsed.learningMetadata?.masteryThreshold).toEqual({
      policy: "independent_all_correct_v1",
      evidenceCount: 2,
      requiredCorrect: 2,
      claimScope: "this_lesson_only",
    });
  });

  it("keeps legacy OpenMAIC canvas and sandboxed HTML packages playable", () => {
    const legacy = lessonPackageV2Schema.parse({
      schemaVersion: "mira.learning.lesson-package.v2",
      id: "legacy-package",
      version: 1,
      title: "旧版课堂",
      language: "zh-CN",
      estimatedMinutes: 8,
      scenes: [
        {
          id: "legacy-slide",
          type: "slide",
          order: 0,
          title: "旧版课件",
          canvas: {
            id: "legacy-canvas",
            elements: [{ id: "copy", type: "text", left: 30, top: 30, width: 500, height: 90, content: "旧版内容" }],
          },
          blocks: [],
          actions: [],
        },
        {
          id: "legacy-widget",
          type: "interactive",
          order: 1,
          title: "旧版互动",
          html: "<button id=\"done\">完成</button><script>MiraWidget.complete({completed:true})</script>",
          widgetType: "game",
          interactionRef: "legacy:widget",
          questionRefs: [],
          instructions: "点一下",
          actions: [],
        },
      ],
    });
    const slide = legacy.scenes[0];
    const widget = legacy.scenes[1];
    expect(slide.type).toBe("slide");
    expect(widget.type).toBe("interactive");
    if (slide.type !== "slide" || widget.type !== "interactive") throw new Error("missing legacy scenes");
    expect(parseOpenMaicCanvas(slide.canvas).elements).toHaveLength(1);
    expect(widget.html).toContain("MiraWidget.complete");
  });

  it("rejects incomplete controlled package authority and unsafe asset briefs", () => {
    expect(lessonPackageV2Schema.safeParse({ ...classroomPackageFixture, learningMetadata: undefined }).success).toBe(false);
    expect(lessonPackageV2Schema.safeParse({
      ...classroomPackageFixture,
      learningMetadata: { ...classroomPackageFixture.learningMetadata, answerKey: "never-public" },
    }).success).toBe(false);
    expect(lessonPackageV2Schema.safeParse({
      ...classroomPackageFixture,
      assetBrief: [{
        id: "bad-audio",
        kind: "audio",
        purpose: "https://example.com/audio.mp3",
        required: false,
        deliveryMode: "tts",
      }],
    }).success).toBe(false);
  });

  it("accepts consistent math manipulatives and rejects missing or invalid visual evidence", () => {
    const teach = classroomPackageFixture.scenes[0];
    const visualAids = [
      {
        id: "visual-add",
        kind: "math_counters.v1" as const,
        operation: "combine" as const,
        left: 8,
        right: 4,
        result: 12,
        caption: "把两部分合起来，就是加法。",
      },
      {
        id: "visual-subtract",
        kind: "math_counters.v1" as const,
        operation: "take_away" as const,
        left: 13,
        right: 4,
        result: 9,
        caption: "从原来的一组里去掉一部分，就是减法。",
      },
    ];
    const mathPackage = {
      ...classroomPackageFixture,
      id: "lesson-p1-math-add-sub",
      assetBrief: [],
      sourceCourse: {
        ...classroomPackageFixture.sourceCourse!,
        subject: "math" as const,
        nodeCode: "addition_subtraction_20",
      },
      learningMetadata: {
        ...classroomPackageFixture.learningMetadata!,
        subject: "math" as const,
      },
      scenes: [
        {
          ...teach,
          layoutTemplate: "concept_focus.v1" as const,
          templateData: { visualAids },
        },
        ...classroomPackageFixture.scenes.slice(1),
      ],
    };
    const parsed = lessonPackageV2Schema.parse(mathPackage);
    const parsedTeach = parsed.scenes[0];
    expect(parsedTeach.type).toBe("slide");
    if (parsedTeach.type !== "slide") throw new Error("missing math teach slide");
    expect(parsedTeach.templateData?.visualAids?.map((aid) => aid.kind)).toEqual([
      "math_counters.v1",
      "math_counters.v1",
    ]);
    expect(lessonPackageV2Schema.safeParse({
      ...mathPackage,
      scenes: [{ ...mathPackage.scenes[0], templateData: { visualAids: [] } }, ...mathPackage.scenes.slice(1)],
    }).success).toBe(false);
    expect(lessonPackageV2Schema.safeParse({
      ...mathPackage,
      scenes: [{
        ...mathPackage.scenes[0],
        templateData: { visualAids: [{ ...visualAids[0], result: 13 }, visualAids[1]] },
      }, ...mathPackage.scenes.slice(1)],
    }).success).toBe(false);
    expect(lessonPackageV2Schema.safeParse({
      ...mathPackage,
      assetBrief: [{
        id: "missing-image",
        kind: "image",
        purpose: "未兑现的图片",
        required: true,
        deliveryMode: "generated_asset",
      }],
    }).success).toBe(false);
  });

  it("rejects duplicate action ids and accepts the final completed runtime shape", () => {
    const first = classroomPackageFixture.scenes[0];
    expect(lessonPackageV2Schema.safeParse({
      ...classroomPackageFixture,
      scenes: [{ ...first, actions: [first.actions[0], first.actions[0]] }],
    }).success).toBe(false);

    const finalScene = classroomPackageFixture.scenes.at(-1);
    expect(classroomRuntimeResponseSchema.safeParse({
      ok: true,
      sessionId: "session-1",
      classroom: { id: classroomPackageFixture.id, version: 1, contentHash: "sha256:fixture" },
      scene: finalScene,
      action: null,
      cursor: {
        revision: 8,
        sceneId: finalScene?.id,
        actionId: null,
        sceneIndex: classroomPackageFixture.scenes.length - 1,
        actionIndex: finalScene?.actions.length,
        sceneCount: classroomPackageFixture.scenes.length,
        progress: 1,
      },
      completed: true,
    }).success).toBe(true);
  });
});
