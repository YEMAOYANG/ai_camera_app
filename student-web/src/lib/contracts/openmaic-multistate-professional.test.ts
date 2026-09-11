import { describe, expect, it } from "vitest";
import launch from "@/test/fixtures/openmaic-multistate-professional-launch.json";
import { openMaicFormalRuntimeLaunchSchema } from "./openmaic-runtime";

describe("published multistate classroom launch", () => {
  it("accepts the actual grade-six launch with strict difficulty and interaction evidence", () => {
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(launch).success).toBe(true);
  });

  it.each(["unknown receipt field", "different difficulty", "different visual snapshot", "missing teaching actions"])(
    "rejects %s instead of stripping authority", (failure) => {
      const value = structuredClone(launch);
      if (failure === "unknown receipt field") {
        Object.assign(value.features.professionalCreation.interactionDesign.visualReview, { bypass: true });
      } else if (failure === "different difficulty") {
        value.features.generationContract.course.difficultyCode = "challenge";
      } else if (failure === "different visual snapshot") {
        value.features.professionalCreation.interactionDesign.visualReview.snapshotSha256 = "0".repeat(64);
      } else {
        Reflect.deleteProperty(value.features.formalEvidence, "requiredTeachingActions");
      }
      expect(openMaicFormalRuntimeLaunchSchema.safeParse(value).success).toBe(false);
    },
  );
});
