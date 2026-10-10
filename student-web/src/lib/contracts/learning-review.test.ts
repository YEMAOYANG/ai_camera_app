import { describe, expect, it } from "vitest";
import { reviewQuestionSchema } from "./learning-review";

const submissionId = `hw_${"a".repeat(32)}`, pageId = `hwp_${"b".repeat(32)}`, itemId = `hwi_${"c".repeat(56)}`;
const original = { id: "question_one", renderer: "homework_original", prompt: "看原图，再试一试", visual: { kind: "homework_original", submissionId, pageId, width: 1200, height: 1600, region: { x: .1, y: .2, width: .5, height: .2 }, answerRegion: null }, homeworkSource: { submissionId, itemId, itemRevision: 7 }, options: [], promptAudioUrl: "/api/learning/reviews/review_one/media/prompt.wav" };

describe("saved original homework review contract", () => {
  it("preserves the frozen source, geometry and spoken renderer without exposing a private answer", () => {
    const parsed = reviewQuestionSchema.parse({ ...original, correctAnswer: "5" });
    expect(parsed.visual).toEqual(original.visual); expect(parsed.homeworkSource).toEqual(original.homeworkSource);
    expect(parsed.options).toEqual([]); expect(parsed).not.toHaveProperty("correctAnswer");
  });
  it.each([
    { ...original, homeworkSource: undefined },
    { ...original, homeworkSource: { ...original.homeworkSource, submissionId: `hw_${"d".repeat(32)}` } },
    { ...original, homeworkSource: { ...original.homeworkSource, itemRevision: 0 } },
    { ...original, renderer: "quantity_arithmetic" },
    { ...original, visual: { kind: "quantity_arithmetic", operation: "add", left: 3, right: 2, choices: [] } },
    { ...original, visual: { ...original.visual, region: { x: .8, y: .2, width: .5, height: .2 } } },
    { ...original, options: [{ value: "5", label: "5", picture: { count: 5 } }] },
  ])("rejects an inconsistent original-photo renderer or source", value => {
    expect(reviewQuestionSchema.safeParse(value).success).toBe(false);
  });
});
