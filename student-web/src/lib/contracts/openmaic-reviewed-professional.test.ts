import { describe, expect, it } from "vitest";
import launch from "@/test/fixtures/openmaic-reviewed-professional-launch.json";
import { openMaicFormalRuntimeLaunchSchema } from "./openmaic-runtime";

describe("published professional classroom launch contract", () => {
  it("accepts the actual seven-scene release with QA, skills and media receipts", () => {
    expect(openMaicFormalRuntimeLaunchSchema.safeParse(launch)).toMatchObject({ success: true });
  });
  it.each(["failed quality", "missing viewport", "wrong course media", "missing policy", "wrong boundary", "mismatched proof"])(
    "rejects %s without silently stripping its authority", (failure) => {
      const value = structuredClone(launch);
      const f = value.features;
      if (failure === "failed quality") f.professionalCreation.teachingQuality.review.dimensions[0].passed = false;
      if (failure === "missing viewport") f.professionalCreation.teachingQuality.renderChecks.shift();
      if (failure === "wrong course media") f.media.classroomId = "other-classroom";
      if (failure === "missing policy") Reflect.deleteProperty(f.generationContract.professionalCreationPolicy, "image");
      if (failure === "wrong boundary") f.generationContract.gradeBoundarySha256 = "0".repeat(64);
      if (failure === "mismatched proof") f.formalEvidence.teachingQuality.receiptSha256 = "0".repeat(64);
      expect(openMaicFormalRuntimeLaunchSchema.safeParse(value).success).toBe(false);
    });
});
