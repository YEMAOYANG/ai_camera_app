import { describe, expect, it } from "vitest";
import launch from "@/test/fixtures/openmaic-progressive-formal-launch.json";
import scope from "@/test/fixtures/openmaic-progressive-authoring-scope.json";
import legacy from "@/test/fixtures/openmaic-multistate-professional-launch.json";
import { openMaicFormalRuntimeLaunchSchema } from "./openmaic-runtime";
import { progressiveTeachingBriefSchema } from "./openmaic-progressive-contract";

describe("published progressive student launch", () => {
  it("accepts the published six-question classroom and retains the legacy launch", () => {
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(launch).success).toBe(true);
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(legacy).success).toBe(true);
  });

  it("rejects mismatched lesson, grade, policy, assessment and private answer fields", () => {
    const changes: Array<(value: typeof launch) => void> = [
      value => { value.features.generationContract.teachingBrief.course.gradeCode = "primary_1"; },
      value => { value.features.generationContract.teachingBrief.progressiveLesson.lessonId = "ZH6A01.02"; },
      value => { value.features.generationContract.difficultyPolicy.lessonScope.unitTitle = "另一单元"; },
      value => { value.features.formalEvidence.assessmentQuestionIds.pop(); },
      value => { value.features.generationContract.teachingBrief.lesson.teachingFlow.independentQuestionIds.pop(); },
      value => { Object.assign(value.features.generationContract.teachingBrief.lesson.questions[0], { answer: "A" }); },
    ];
    for (const change of changes) {
      const altered = structuredClone(launch);
      change(altered);
      expect(openMaicFormalRuntimeLaunchSchema.safeParse(altered).success).toBe(false);
    }
  });

  it("accepts the host-issued optional scope only for the same lesson and question roles", () => {
    const brief = { ...structuredClone(launch.features.generationContract.teachingBrief),
      runtimeAuthoringScope: structuredClone(scope) };
    expect(progressiveTeachingBriefSchema.safeParse(brief).success).toBe(true);
    brief.runtimeAuthoringScope.assessmentProtection.protectedQuestions[0].phase = "independent";
    expect(progressiveTeachingBriefSchema.safeParse(brief).success).toBe(false);
    brief.runtimeAuthoringScope = structuredClone(scope);
    brief.runtimeAuthoringScope.lessonScope.gradeCode = "primary_1";
    expect(progressiveTeachingBriefSchema.safeParse(brief).success).toBe(false);
  });
});
