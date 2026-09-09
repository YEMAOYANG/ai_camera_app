import { z } from "zod";

const publicIdSchema = z.string().trim().min(1).max(160);
const publicTextSchema = z.string().trim().min(1).max(4000);
const assetRefSchema = z.string().trim().min(1).max(500);
const classroomPhaseRoleSchema = z.enum(["teach", "demo", "guided", "independent", "recap"]);
const controlledLayoutTemplateSchema = z.enum([
  "phonics_focus.v1",
  "concept_focus.v1",
  "worked_example.v1",
]);
const controlledWidgetTemplateSchema = z.enum([
  "listen_tap_choice.v1",
  "match_pairs.v1",
  "sort_order.v1",
]);

const narrateActionSchema = z.object({
  id: publicIdSchema,
  type: z.literal("narrate"),
  text: publicTextSchema,
  audioAssetRef: assetRefSchema.optional(),
});

const focusActionSchema = z.object({
  id: publicIdSchema,
  type: z.literal("focus"),
  targetId: publicIdSchema,
});

const playMediaActionSchema = z.object({
  id: publicIdSchema,
  type: z.literal("play_media"),
  assetRef: assetRefSchema,
});

const awaitContinueActionSchema = z.object({
  id: publicIdSchema,
  type: z.literal("await_continue"),
});

const awaitInteractionActionSchema = z.object({
  id: publicIdSchema,
  type: z.literal("await_interaction"),
  interactionRef: publicIdSchema,
});

const completeSceneActionSchema = z.object({
  id: publicIdSchema,
  type: z.literal("complete_scene"),
});

export const classroomActionSchema = z.discriminatedUnion("type", [
  narrateActionSchema,
  focusActionSchema,
  playMediaActionSchema,
  awaitContinueActionSchema,
  awaitInteractionActionSchema,
  completeSceneActionSchema,
]);

const sceneBaseShape = {
  id: publicIdSchema,
  order: z.number().int().nonnegative(),
  phaseRole: classroomPhaseRoleSchema.optional(),
  title: z.string().trim().min(1).max(240),
  actions: z.array(classroomActionSchema).max(80).default([]),
};

export const classroomSlideBlockSchema = z.discriminatedUnion("type", [
  z.object({
    id: publicIdSchema,
    type: z.literal("text"),
    text: publicTextSchema,
    styleToken: z.string().trim().min(1).max(48).optional(),
  }),
  z.object({
    id: publicIdSchema,
    type: z.literal("shape"),
    shape: z.enum(["circle", "rectangle", "line"]),
    styleToken: z.string().trim().min(1).max(48).optional(),
  }),
  z.object({
    id: publicIdSchema,
    type: z.literal("image"),
    assetRef: assetRefSchema,
    alt: z.string().trim().min(1).max(300),
  }),
]);

const phonicsFocusItemSchema = z.object({
  id: publicIdSchema,
  label: z.string().trim().min(1).max(12),
  mouthCue: z.string().trim().min(1).max(180),
  audioAssetRef: assetRefSchema.optional(),
}).strict();

const visualAidCaptionSchema = z.string().trim().min(1).max(180);
const mathCounterVisualAidSchema = z.object({
  id: publicIdSchema,
  kind: z.literal("math_counters.v1"),
  operation: z.enum(["combine", "take_away"]),
  left: z.number().int().min(0).max(20),
  right: z.number().int().min(0).max(20),
  result: z.number().int().min(0).max(20),
  caption: visualAidCaptionSchema,
}).strict();
const numberCompareVisualAidSchema = z.object({
  id: publicIdSchema,
  kind: z.literal("number_compare.v1"),
  left: z.number().int().min(0).max(20),
  right: z.number().int().min(0).max(20),
  relation: z.enum(["less_than", "greater_than"]),
  caption: visualAidCaptionSchema,
}).strict();
const placeValueVisualAidSchema = z.object({
  id: publicIdSchema,
  kind: z.literal("place_value.v1"),
  value: z.number().int().min(0).max(20),
  tens: z.number().int().min(0).max(2),
  ones: z.number().int().min(0).max(9),
  caption: visualAidCaptionSchema,
}).strict();
const shapeGalleryVisualAidSchema = z.object({
  id: publicIdSchema,
  kind: z.literal("shape_gallery.v1"),
  items: z.array(z.object({
    shape: z.enum(["circle", "triangle", "square", "rectangle"]),
    label: z.string().trim().min(1).max(12),
  }).strict()).length(4),
  caption: visualAidCaptionSchema,
}).strict();
const positionCompassVisualAidSchema = z.object({
  id: publicIdSchema,
  kind: z.literal("position_compass.v1"),
  labels: z.object({
    up: z.string().trim().min(1).max(12),
    down: z.string().trim().min(1).max(12),
    left: z.string().trim().min(1).max(12),
    right: z.string().trim().min(1).max(12),
  }).strict(),
  caption: visualAidCaptionSchema,
}).strict();

export const classroomVisualAidSchema = z.discriminatedUnion("kind", [
  mathCounterVisualAidSchema,
  numberCompareVisualAidSchema,
  placeValueVisualAidSchema,
  shapeGalleryVisualAidSchema,
  positionCompassVisualAidSchema,
]).superRefine((aid, context) => {
  if (aid.kind === "math_counters.v1") {
    const expected = aid.operation === "combine" ? aid.left + aid.right : aid.left - aid.right;
    if (expected !== aid.result || expected < 0) {
      context.addIssue({ code: "custom", message: "圆片教具的算式关系无效", path: ["result"] });
    }
  }
  if (aid.kind === "number_compare.v1") {
    const valid = aid.relation === "less_than" ? aid.left < aid.right : aid.left > aid.right;
    if (!valid) context.addIssue({ code: "custom", message: "数值比较教具的关系无效", path: ["relation"] });
  }
  if (aid.kind === "place_value.v1" && aid.tens * 10 + aid.ones !== aid.value) {
    context.addIssue({ code: "custom", message: "数位教具的十位和个位不等于目标数", path: ["value"] });
  }
  if (aid.kind === "shape_gallery.v1" && new Set(aid.items.map((item) => item.shape)).size !== aid.items.length) {
    context.addIssue({ code: "custom", message: "图形教具不能重复图形", path: ["items"] });
  }
});

const slideTemplateDataSchema = z.object({
  focusItems: z.array(phonicsFocusItemSchema).min(1).max(8).optional(),
  visualAids: z.array(classroomVisualAidSchema).min(1).max(4).optional(),
  questionId: publicIdSchema.optional(),
  prompt: z.string().trim().min(1).max(600).optional(),
  explanation: z.string().trim().min(1).max(1200).optional(),
}).strict().optional();

const questionTemplateDataSchema = z.object({
  questionRefs: z.array(publicIdSchema).min(1).max(8),
  questionSource: z.literal("session_questions"),
  stateContract: z.object({
    initial: z.literal("awaiting_answer"),
    transitions: z.tuple([
      z.literal("awaiting_answer->answered"),
      z.literal("answered->retry_or_next"),
      z.literal("all_guided_evaluated->completed"),
    ]),
    completion: z.literal("guided_questions_evaluated"),
  }).strict().optional(),
}).strict();

export const classroomGameRulesSchema = z.object({
  goal: z.string().trim().min(1).max(240),
  instructions: z.array(z.string().trim().min(1).max(240)).min(1).max(3),
  successCriterion: z.string().trim().min(1).max(240),
  maxAttempts: z.literal(2),
  feedbackMode: z.enum(["encouraging_retry", "explain_then_retry"]),
}).strict();

const slideSceneSchema = z.object({
  ...sceneBaseShape,
  type: z.literal("slide"),
  layoutTemplate: controlledLayoutTemplateSchema.optional(),
  templateData: slideTemplateDataSchema,
  canvas: z.unknown().optional(),
  blocks: z.array(classroomSlideBlockSchema).max(40).default([]),
}).superRefine((scene, context) => {
  if (scene.canvas === undefined && scene.blocks.length === 0 && scene.layoutTemplate === undefined) {
    context.addIssue({
      code: "custom",
      message: "幻灯片必须包含受控模板、受控课件画布或安全内容块",
      path: ["layoutTemplate"],
    });
  }
  if (scene.layoutTemplate === "phonics_focus.v1" && !scene.templateData?.focusItems?.length) {
    context.addIssue({ code: "custom", message: "拼音模板必须包含发音项目", path: ["templateData", "focusItems"] });
  }
  if (scene.layoutTemplate === "worked_example.v1" && (!scene.templateData?.prompt || !scene.templateData.explanation)) {
    context.addIssue({ code: "custom", message: "示范模板必须包含题干和讲解", path: ["templateData"] });
  }
});

const legacyWidgetTemplateSchema = z.enum([
  "tap_choice.v1",
  "match_pairs.v1",
  "sort_order.v1",
  "slider_lab.v1",
]);

const interactiveSceneSchema = z.object({
  ...sceneBaseShape,
  type: z.literal("interactive"),
  html: z.string().min(1).max(200_000).optional(),
  widgetType: z.enum(["simulation", "diagram", "code", "game", "visualization3d", "procedural-skill"]).optional(),
  widgetTemplate: controlledWidgetTemplateSchema.optional(),
  templateId: z.union([legacyWidgetTemplateSchema, controlledWidgetTemplateSchema]).optional(),
  templateData: questionTemplateDataSchema.optional(),
  gameRules: classroomGameRulesSchema.optional(),
  interactionRef: publicIdSchema,
  questionRefs: z.array(publicIdSchema).max(20).default([]),
  instructions: z.string().trim().max(1200).optional(),
}).superRefine((scene, context) => {
  const controlled = scene.widgetTemplate !== undefined;
  if (scene.html === undefined && scene.templateId === undefined && scene.widgetTemplate === undefined) {
    context.addIssue({ code: "custom", message: "互动场景必须包含受控模板或旧版安全内容", path: ["widgetTemplate"] });
  }
  if (controlled && (!scene.gameRules || !scene.templateData?.stateContract)) {
    context.addIssue({ code: "custom", message: "受控互动模板必须包含游戏规则和题目引用", path: ["gameRules"] });
  }
  if (scene.templateData && scene.questionRefs.join("|") !== scene.templateData.questionRefs.join("|")) {
    context.addIssue({ code: "custom", message: "互动模板题目引用必须与场景一致", path: ["templateData", "questionRefs"] });
  }
});

const quizSceneSchema = z.object({
  ...sceneBaseShape,
  type: z.literal("quiz"),
  mode: z.enum(["practice", "guided", "independent"]),
  interactionRef: publicIdSchema.optional(),
  questionRefs: z.array(publicIdSchema).min(1).max(30),
  instructions: z.string().trim().max(1200).optional(),
  templateData: questionTemplateDataSchema.optional(),
});

const recapSceneSchema = z.object({
  ...sceneBaseShape,
  type: z.literal("recap"),
  sayText: publicTextSchema,
  keyPoints: z.array(z.string().trim().min(1).max(300)).max(8).default([]),
});

const videoSceneSchema = z.object({
  ...sceneBaseShape,
  type: z.literal("video"),
  assetRef: assetRefSchema,
  posterRef: assetRefSchema.optional(),
  captionsRef: assetRefSchema.optional(),
  minWatchRatio: z.number().min(0).max(1).optional(),
});

export const classroomSceneSchema = z.discriminatedUnion("type", [
  slideSceneSchema,
  interactiveSceneSchema,
  quizSceneSchema,
  recapSceneSchema,
  videoSceneSchema,
]);

const classroomPedagogySchema = z.object({
  sequence: z.tuple([
    z.literal("teach"),
    z.literal("demo"),
    z.literal("guided"),
    z.literal("independent"),
    z.literal("recap"),
  ]),
  teachBeforePractice: z.literal(true),
}).strict();

const classroomAssetBriefSchema = z.object({
  id: publicIdSchema,
  kind: z.enum(["audio", "image", "video"]),
  purpose: z.string().trim().min(1).max(300).refine(
    (value) => !/(?:[a-z][a-z0-9+.-]*:|\/|\\|\.\.)/i.test(value),
    "素材说明不能包含 URL 或路径",
  ),
  required: z.boolean(),
  deliveryMode: z.enum(["tts", "generated_asset", "none"]),
}).strict();

const classroomAuthoritySchema = z.object({
  curriculum: z.literal("published_learning_course"),
  assessment: z.literal("server_reference_only"),
  sourceArtifactHash: z.string().trim().min(1).max(200),
}).strict();

const classroomSourceCourseSchema = z.object({
  id: publicIdSchema,
  version: z.string().trim().min(1).max(80),
  gradeCode: z.enum(["primary_1", "primary_2", "primary_3", "primary_4", "primary_5", "primary_6"]),
  subject: z.enum(["chinese", "math", "english"]),
  nodeCode: publicIdSchema,
}).strict();

const classroomLearningMetadataSchema = z.object({
  gradeBand: z.string().trim().min(1).max(40),
  subject: z.enum(["chinese", "math", "english"]),
  objectives: z.array(z.string().trim().min(1).max(240)).min(1).max(8),
  prerequisites: z.array(z.string().trim().min(1).max(240)).max(8),
  misconceptions: z.array(z.string().trim().min(1).max(240)).min(1).max(3),
  masteryThreshold: z.object({
    policy: z.literal("independent_all_correct_v1"),
    evidenceCount: z.literal(2),
    requiredCorrect: z.literal(2),
    claimScope: z.literal("this_lesson_only"),
  }).strict(),
}).strict();

export const lessonPackageV2Schema = z.object({
  schemaVersion: z.literal("mira.learning.lesson-package.v2"),
  id: publicIdSchema,
  version: z.number().int().positive(),
  title: z.string().trim().min(1).max(240),
  language: z.string().trim().min(2).max(24),
  estimatedMinutes: z.number().int().positive().max(180),
  sourceCourse: classroomSourceCourseSchema.optional(),
  pedagogy: classroomPedagogySchema.optional(),
  learningMetadata: classroomLearningMetadataSchema.optional(),
  assetBrief: z.array(classroomAssetBriefSchema).max(4).default([]),
  scenes: z.array(classroomSceneSchema).min(1).max(80),
  assetRefs: z.array(publicIdSchema).max(40).default([]),
  authority: classroomAuthoritySchema.optional(),
}).superRefine((value, context) => {
  const sceneIds = new Set<string>();
  const orders = new Set<number>();
  for (const [index, scene] of value.scenes.entries()) {
    if (sceneIds.has(scene.id)) {
      context.addIssue({ code: "custom", path: ["scenes", index, "id"], message: "课堂场景 ID 不能重复" });
    }
    if (orders.has(scene.order)) {
      context.addIssue({ code: "custom", path: ["scenes", index, "order"], message: "课堂场景顺序不能重复" });
    }
    sceneIds.add(scene.id);
    orders.add(scene.order);

    const actionIds = new Set<string>();
    for (const [actionIndex, action] of scene.actions.entries()) {
      if (actionIds.has(action.id)) {
        context.addIssue({
          code: "custom",
          path: ["scenes", index, "actions", actionIndex, "id"],
          message: "场景动作 ID 不能重复",
        });
      }
      actionIds.add(action.id);
      if (action.type === "focus" && scene.type === "slide" && scene.canvas === undefined && !scene.blocks.some((block) => block.id === action.targetId)) {
        context.addIssue({
          code: "custom",
          path: ["scenes", index, "actions", actionIndex, "targetId"],
          message: "聚焦动作必须指向当前幻灯片中的内容",
        });
      }
      if (action.type === "await_interaction" && scene.type === "interactive" && action.interactionRef !== scene.interactionRef) {
        context.addIssue({
          code: "custom",
          path: ["scenes", index, "actions", actionIndex, "interactionRef"],
          message: "互动动作必须指向当前互动场景",
        });
      }
    }
  }

  if (value.pedagogy) {
    const orderedRoles = [...value.scenes]
      .sort((left, right) => left.order - right.order)
      .map((scene) => scene.phaseRole);
    if (value.scenes.length !== 5 || orderedRoles.some((role, index) => role !== value.pedagogy?.sequence[index])) {
      context.addIssue({
        code: "custom",
        path: ["scenes"],
        message: "受控课堂必须严格按照教、示范、引导、独立练习、总结五段编排",
      });
    }
    if (!value.sourceCourse || !value.learningMetadata || !value.authority) {
      context.addIssue({
        code: "custom",
        path: ["pedagogy"],
        message: "受控课堂必须同时声明课程来源、学习边界和内容权威",
      });
    }
    const guided = value.scenes.find((scene) => scene.phaseRole === "guided");
    const independent = value.scenes.find((scene) => scene.phaseRole === "independent");
    if (guided?.type !== "interactive" || guided.questionRefs.length !== 2) {
      context.addIssue({ code: "custom", path: ["scenes"], message: "引导练习必须绑定两道服务端题目" });
    }
    if (independent?.type !== "quiz" || independent.questionRefs.length !== 2) {
      context.addIssue({ code: "custom", path: ["scenes"], message: "独立练习必须绑定两道服务端题目" });
    }
    const requiresControlledMathVisuals = value.sourceCourse?.gradeCode === "primary_1"
      && value.sourceCourse.subject === "math"
      && ["number_sense_20", "addition_subtraction_20", "shapes_position"].includes(value.sourceCourse.nodeCode);
    if (requiresControlledMathVisuals) {
      const teach = value.scenes.find((scene) => scene.phaseRole === "teach");
      if (teach?.type !== "slide" || teach.layoutTemplate !== "concept_focus.v1" || (teach.templateData?.visualAids?.length || 0) < 2) {
        context.addIssue({ code: "custom", path: ["scenes"], message: "一年级数学正式课堂必须包含至少两项受控视觉教具" });
      }
      if (value.assetBrief.some((brief) => brief.required)) {
        context.addIssue({ code: "custom", path: ["assetBrief"], message: "一年级数学正式课堂不能公开未兑现的必需素材说明" });
      }
    }
  }
});

export const classroomDescriptorSchema = z.object({
  id: publicIdSchema,
  version: z.number().int().positive(),
  contentHash: z.string().trim().min(1).max(200),
});

export const classroomCursorSchema = z.object({
  revision: z.number().int().nonnegative(),
  sceneId: publicIdSchema,
  actionId: publicIdSchema.nullable().optional(),
  sceneIndex: z.number().int().nonnegative(),
  actionIndex: z.number().int().nonnegative(),
  sceneCount: z.number().int().positive(),
  progress: z.number().min(0).max(1),
});

export const classroomRuntimeResponseSchema = z.object({
  ok: z.literal(true),
  sessionId: publicIdSchema,
  classroom: classroomDescriptorSchema,
  scene: classroomSceneSchema,
  action: classroomActionSchema.nullable(),
  cursor: classroomCursorSchema,
  completed: z.boolean(),
});

export const completeClassroomActionRequestSchema = z.object({
  cursorRevision: z.number().int().nonnegative(),
  idempotencyKey: z.string().trim().min(8).max(240),
  result: z.record(z.string(), z.unknown()).optional(),
});

export type ClassroomAction = z.infer<typeof classroomActionSchema>;
export type ClassroomScene = z.infer<typeof classroomSceneSchema>;
export type ClassroomSlideBlock = z.infer<typeof classroomSlideBlockSchema>;
export type ClassroomGameRules = z.infer<typeof classroomGameRulesSchema>;
export type ClassroomVisualAid = z.infer<typeof classroomVisualAidSchema>;
export type LessonPackageV2 = z.infer<typeof lessonPackageV2Schema>;
export type ClassroomDescriptor = z.infer<typeof classroomDescriptorSchema>;
export type ClassroomCursor = z.infer<typeof classroomCursorSchema>;
export type ClassroomRuntimeResponse = z.infer<typeof classroomRuntimeResponseSchema>;
