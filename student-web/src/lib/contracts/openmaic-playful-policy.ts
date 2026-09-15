import { z } from "zod";

const playfulLearningAuthority = {
  aiDesigned: z.literal(true),
  maxQuizScenes: z.literal(2),
  lockedAssessmentPreserved: z.literal(true),
  minimumReplayableGames: z.literal(1),
};

export const playfulLearningPolicySchema = z.discriminatedUnion("schemaVersion", [
  z.object({
    ...playfulLearningAuthority,
    schemaVersion: z.literal("mira.openmaic.playful-learning.v1"),
    policyId: z.literal("mira-primary-playful-exploration.v1"),
    threeDUsage: z.literal("teaching_need"),
  }).strict(),
  z.object({
    ...playfulLearningAuthority,
    schemaVersion: z.literal("mira.openmaic.playful-learning.v2"),
    policyId: z.literal("mira-primary-playful-3d.v2"),
    threeDUsage: z.literal("required"),
    minimumThreeDScenes: z.literal(1),
  }).strict(),
]);
