import { describe, expect, it } from "vitest";
import oldLaunch from "@/test/fixtures/openmaic-multistate-professional-launch.json";
import { openMaicFormalRuntimeLaunchSchema } from "./openmaic-runtime";
import { playfulLearningPolicySchema } from "./openmaic-playful-policy";

const policy = {
  schemaVersion: "mira.openmaic.playful-learning.v1",
  policyId: "mira-primary-playful-exploration.v1",
  aiDesigned: true,
  maxQuizScenes: 2,
  lockedAssessmentPreserved: true,
  minimumReplayableGames: 1,
  threeDUsage: "teaching_need",
};

const threeDPolicy = {
  ...policy,
  schemaVersion: "mira.openmaic.playful-learning.v2",
  policyId: "mira-primary-playful-3d.v2",
  threeDUsage: "required",
  minimumThreeDScenes: 1,
};

describe("AI-designed playful course authority", () => {
  it("accepts the versioned policy but rejects changed authority and extra fields", () => {
    expect(playfulLearningPolicySchema.safeParse(policy).success).toBe(true);
    for (const mutation of [{ aiDesigned: false }, { maxQuizScenes: 4 },
      { minimumReplayableGames: 0 }, { lockedAssessmentPreserved: false }, { bypass: true }]) {
      expect(playfulLearningPolicySchema.safeParse({ ...policy, ...mutation }).success).toBe(false);
    }
  });

  it("accepts the opt-in 3D policy without allowing mixed versions or weaker authority", () => {
    expect(playfulLearningPolicySchema.parse(threeDPolicy)).toEqual(threeDPolicy);
    for (const mutation of [
      { schemaVersion: policy.schemaVersion },
      { policyId: policy.policyId },
      { threeDUsage: "teaching_need" },
      { minimumThreeDScenes: 0 },
      { minimumThreeDScenes: undefined },
      { minimumReplayableGames: 0 },
      { aiDesigned: false },
      { maxQuizScenes: 4 },
      { lockedAssessmentPreserved: false },
      { bypass: true },
    ]) {
      expect(playfulLearningPolicySchema.safeParse({ ...threeDPolicy, ...mutation }).success).toBe(false);
    }
    expect(playfulLearningPolicySchema.safeParse({ ...policy, minimumThreeDScenes: 1 }).success).toBe(false);
  });

  it("preserves the published old course without pretending it meets the new policy", () => {
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(oldLaunch).success).toBe(true);
    const incorrectlyRelabelled = structuredClone(oldLaunch);
    Object.assign(incorrectlyRelabelled.features.generationContract.professionalCreationPolicy, {
      playfulLearningPolicy: policy,
    });
    const parsed = openMaicFormalRuntimeLaunchSchema.safeParse(incorrectlyRelabelled);
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues.some(issue => issue.message.includes("AI 小游戏"))).toBe(true);
    }
  });
});
