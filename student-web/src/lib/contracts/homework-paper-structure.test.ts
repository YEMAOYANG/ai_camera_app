import { describe, expect, it } from "vitest";
import fixture from "@/test/fixtures/homework-service.json";
import { homeworkPaperStructureFixture } from "@/test/fixtures/homework-paper-structure";
import { homeworkDetailSchema, homeworkPaperStructureSchema } from "./homework";

const structure = () => homeworkPaperStructureFixture(fixture.studentDetail.submission.items[0].id, `hwp_${"b".repeat(32)}`);
describe("original paper source-tree contract", () => {
  it("preserves the actual hierarchy, shared media, exact answer link and unanswered leaf without adding grading", () => {
    const paperStructure = structure();
    const payload = { ...fixture.studentDetail, submission: { ...fixture.studentDetail.submission, paperStructure } };
    const parsed = homeworkDetailSchema.parse(payload).submission.paperStructure!;
    expect(parsed).toEqual(paperStructure);
    expect(parsed.pages[0].questions[0].children[1].answers[0]).toMatchObject({ index: null, count: 0, region: null });
    expect(parsed.pages[0].questions[0].children[0].answers[0].itemId).toBe(fixture.studentDetail.submission.items[0].id);
    expect(parsed).not.toHaveProperty("countsForAbility");
    expect(homeworkDetailSchema.parse(fixture.studentDetail).submission.paperStructure).toBeUndefined();
  });
  it("keeps unknown source media as unknown instead of filling in a guessed region", () => {
    const value = structure(); value.pages[0].questions[0].illustrations[0] = { id: "unknown", geometryVerified: false, region: null };
    expect(homeworkPaperStructureSchema.parse(value).pages[0].questions[0].illustrations[0]).toEqual({ id: "unknown", geometryVerified: false, region: null });
  });
  it("rejects out-of-frame coordinates and malformed exact answer identity", () => {
    const badRegion = structure(); badRegion.pages[0].questions[0].region = { x: .9, y: .1, width: .3, height: .1 };
    expect(homeworkPaperStructureSchema.safeParse(badRegion).success).toBe(false);
    const badId = structure(); badId.pages[0].questions[0].children[0].answers[0].itemId = "answer-1";
    expect(homeworkPaperStructureSchema.safeParse(badId).success).toBe(false);
    const badCount = structure(); badCount.pages[0].questions[0].children[1].answers[0].count = -1;
    expect(homeworkPaperStructureSchema.safeParse(badCount).success).toBe(false);
  });
});
