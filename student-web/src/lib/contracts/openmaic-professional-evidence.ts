import { z } from "zod";
import { interactionDesignReceiptSchema } from "./openmaic-interaction-evidence";

const sha = z.string().regex(/^[0-9a-f]{64}$/);
const id = z.string().trim().min(1).max(255);
const text = z.string().trim().min(1).max(4096);
const strings = z.array(text).max(100);
const count = z.number().int().nonnegative();
const sceneHash = z.object({ sceneId: id, sceneSha256: sha }).strict();
const evidence = z.array(z.object({ sceneId: id, quote: text }).strict()).min(1).max(100);
export const qualityDimensionIds = ["grade_fit", "goal_coverage", "teaching_sequence",
  "misconception_repair", "meaningful_interaction", "assessment_alignment", "language_load"] as const;

export const gradeBoundarySchema = z.object({
  gradeCode: id, subject: z.enum(["chinese", "math", "english"]),
  curriculumVersion: id, boundaryVersion: id, skillId: id, skillTitle: text,
  learningObjectives: strings.min(1), allowedContent: strings.min(1), excludedContent: strings,
  prerequisiteSkills: strings, language: z.literal("zh-CN"), estimatedMinutes: z.number().positive(),
}).strict();
export const teachingQualityPolicySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.teaching-quality-policy.v1"),
  policyId: z.literal("mira-primary-quality.v1"), gradeBoundaryRequired: z.literal(true),
  finalSnapshotRequired: z.literal(true), independentReviewRequired: z.literal(true),
  renderedScenesRequired: z.literal(true), maxReviewAttempts: z.literal(3),
}).strict();
export const skillPolicySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.skill-orchestration.v2"),
  profileId: z.literal("mira-primary-adaptive.v2"), registryId: z.literal("openmaic-builtin-skills.v1-23"),
  baseSkillIds: strings.min(1), selectionMode: z.literal("server_rules"), mainMethodMax: z.literal(1),
  gradeBoundaryRequired: z.literal(true), decisionCoverageRequired: z.literal(true), sceneContextRequired: z.literal(true),
}).strict();
export const imagePolicySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.formal-image-policy.v1"),
  policyId: z.literal("mira-formal-qwen-image.v1"), providerId: z.literal("qwen-image"),
  modelId: z.literal("qwen-image-max"), enabled: z.literal(true), providerManaged: z.literal(true),
  assetValidationRequired: z.literal(true), usage: z.literal("teaching_need"),
}).strict();
export const videoPolicySchema = z.object({
  schemaVersion: z.literal("mira.openmaic.formal-video-policy.v1"),
  policyId: z.literal("mira-formal-happyhorse-video.v1"), providerId: z.literal("happyhorse"),
  modelId: z.literal("happyhorse-1.0-t2v"), enabled: z.literal(true), providerManaged: z.literal(true),
  assetValidationRequired: z.literal(true), usage: z.literal("teaching_need"), maxCalls: z.literal(1),
  maxVideos: z.literal(1), aspectRatio: z.literal("16:9"), durationSec: z.literal(5), resolution: z.literal("720p"),
}).strict();
export const skillReceiptSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.skill-orchestration-receipt.v2"),
  profileId: z.literal("mira-primary-adaptive.v2"), status: z.literal("succeeded"), receiptSha256: sha,
  selectionPlan: z.object({
    schemaVersion: z.literal("mira.openmaic.skill-selection.v1"), registryId: z.literal("openmaic-builtin-skills.v1-23"),
    gradeBand: id, gradeBoundarySha256: sha, inputSha256: sha, planSha256: sha, primaryMethod: id.nullable(),
    selectedSkillIds: strings.min(1), decisions: z.array(z.object({
      skillId: id, status: z.enum(["selected", "not_applicable", "deferred"]), reasonCode: id, evidencePaths: strings,
    }).strict()).min(1).max(100),
  }).strict(),
  skillReads: z.array(z.object({ skillId: id, sourceHash: sha }).strict()).min(1).max(100),
  referenceReads: z.array(z.object({ resourcePath: text, sourceHash: sha }).strict()).max(100),
  sceneContexts: z.array(z.object({ sceneId: id, sceneType: z.enum(["slide", "quiz", "interactive", "pbl"]),
    actionsContextSha256: sha, contentContextSha256: sha }).strict()).min(1).max(60),
}).strict();
export const teachingQualityReceiptSchema = z.object({
  schemaVersion: z.literal("mira.openmaic.teaching-quality-receipt.v1"), policyId: z.literal("mira-primary-quality.v1"),
  status: z.literal("passed"), sessionId: id, stageId: id, gradeBoundarySha256: sha, selectionPlanSha256: sha,
  teachingBriefSha256: sha, snapshotSha256: sha, sceneHashes: z.array(sceneHash).min(1).max(60), receiptSha256: sha,
  renderChecks: z.array(z.object({ sceneId: id, sceneSha256: sha, screenshotSha256: sha, domSha256: sha,
    passed: z.literal(true), probeCount: count, viewport: z.object({ width: z.number().int().positive(),
      height: z.number().int().positive() }).strict() }).strict()).min(2).max(120),
  review: z.object({ providerId: z.literal("deepseek"), modelId: z.literal("deepseek-v4-flash"),
    requestIdHash: sha, inputSha256: sha,
    dimensions: z.array(z.object({ id: z.enum(qualityDimensionIds), passed: z.literal(true), evidence }).strict()).length(7),
    objectives: z.array(z.object({ objectiveIndex: count, evidence }).strict()).min(1).max(100),
  }).strict(),
}).strict().superRefine((receipt, ctx) => {
  if (new Set(receipt.review.dimensions.map(d => d.id)).size !== 7)
    ctx.addIssue({ code: "custom", path: ["review", "dimensions"], message: "教学审核必须覆盖全部七个维度" });
  for (const scene of receipt.sceneHashes) {
    for (const [width, height] of [[1280, 720], [1024, 768]]) {
      if (!receipt.renderChecks.some(c => c.sceneId === scene.sceneId && c.sceneSha256 === scene.sceneSha256
          && c.viewport.width === width && c.viewport.height === height))
        ctx.addIssue({ code: "custom", path: ["renderChecks"], message: "每个场景必须有完整的双尺寸渲染证据" });
    }
  }
});
export const teachingQualityEvidenceSchema = z.object({ verified: z.literal(true), receiptSha256: sha,
  snapshotSha256: sha, sceneHashes: z.array(sceneHash).min(1).max(60) }).strict();

const asset = {
  src: z.string().regex(/^\/api\/classroom-media\/[A-Za-z0-9_-]+\/media\/[A-Za-z0-9_.-]+$/), sha256: sha,
  byteSize: z.number().int().positive(), width: z.number().int().positive(), height: z.number().int().positive(),
  sceneIds: z.array(id).min(1).max(60),
};
const mediaIdentity = { schemaVersion: z.literal("mira.openmaic.formal-media-receipt.v1"),
  policyId: z.literal("mira-formal-qwen-image.v1"), providerId: z.literal("qwen-image"), modelId: z.literal("qwen-image-max") };
const videoIdentity = { schemaVersion: z.literal("mira.openmaic.formal-video-receipt.v1"),
  policyId: z.literal("mira-formal-happyhorse-video.v1"), providerId: z.literal("happyhorse"), modelId: z.literal("happyhorse-1.0-t2v") };
const receiptIdentity = { status: z.literal("succeeded"), runtimeRequestId: id, buildItemId: id,
  classroomId: id, sessionId: id, receiptSha256: sha };
export const imageReceiptSchema = z.object({ ...mediaIdentity, ...receiptIdentity, imageCount: count,
  assets: z.array(z.object({ ...asset, mimeType: z.enum(["image/png", "image/jpeg", "image/webp", "image/gif"]) }).strict()).max(240),
}).strict().refine(r => r.assets.length === r.imageCount, "图片数量与素材回执必须一致");
export const videoReceiptSchema = z.object({ ...videoIdentity, ...receiptIdentity, videoCount: count.max(1),
  assets: z.array(z.object({ ...asset, mimeType: z.literal("video/mp4"), durationMs: z.number().positive() }).strict()).max(1),
}).strict().refine(r => r.assets.length === r.videoCount, "视频数量与素材回执必须一致");
export const imageEvidenceSchema = z.object({ ...mediaIdentity, verified: z.literal(true),
  imageCount: count, verifiedAssetCount: count, receiptSha256: sha }).strict();
export const videoEvidenceSchema = z.object({ ...videoIdentity, verified: z.literal(true),
  videoCount: count.max(1), verifiedAssetCount: count.max(1), receiptSha256: sha }).strict();
export const professionalEvidenceExtensions = {
  interactionDesign: interactionDesignReceiptSchema.optional(),
  imageGenerationEnabled: z.literal(true).optional(), imagePolicyId: z.literal("mira-formal-qwen-image.v1").optional(),
  videoGenerationEnabled: z.literal(true).optional(), videoPolicyId: z.literal("mira-formal-happyhorse-video.v1").optional(),
  skillOrchestration: skillReceiptSchema.optional(), teachingQuality: teachingQualityReceiptSchema.optional(),
};
