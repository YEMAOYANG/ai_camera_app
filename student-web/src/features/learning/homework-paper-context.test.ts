import { describe, expect, it } from "vitest";
import fixture from "@/test/fixtures/homework-service.json";
import { homeworkPaperStructureFixture } from "@/test/fixtures/homework-paper-structure";
import { homeworkDetailSchema, type HomeworkSubmission } from "@/lib/contracts/homework";
import { homeworkQuestionContext } from "./homework-paper-context";

const pageId = `hwp_${"b".repeat(32)}`;
function source(): HomeworkSubmission {
  const original = fixture.studentDetail.submission, itemId = original.items[0].id;
  return homeworkDetailSchema.parse({ ok: true, submission: { ...original,
    pages: [{ id: pageId, order: 0, rotation: 0, crop: null, width: 1200, height: 1600, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${original.id}/pages/${pageId}/image` }],
    items: [{ ...original.items[0], reviewContext: { pageId, originalOrdinal: 1, region: { x: .1, y: .48, width: .6, height: .04 }, originalAnswer: "4", grading: { status: "incorrect", geometryVerified: true, knowledgePoints: [], answerRegion: { x: .6, y: .49, width: .035, height: .02 } } } }],
    paperStructure: homeworkPaperStructureFixture(itemId, pageId),
  } }).submission;
}
describe("current question source context", () => {
  it("combines its shared stem, illustration, table and actual options without taking a sibling question", () => {
    const submission = source(), context = homeworkQuestionContext(submission, submission.items[0]);
    expect(context.structured).toBe(true);
    expect(context.region?.x).toBeCloseTo(.1); expect(context.region?.y).toBeCloseTo(.08);
    expect(context.region?.width).toBeCloseTo(.6); expect(context.region?.height).toBeCloseTo(.57);
    expect(context.focusRegion).toEqual({ x: .6, y: .49, width: .035, height: .02 });
    expect(context.media.map(element => element.kind)).toEqual(["illustration", "table", "option", "option"]);
    expect(context.media.some(element => element.id.includes("sibling"))).toBe(false);
  });
  it("uses the exact blank link when several answers share the same stem", () => {
    const submission = source(), node = submission.paperStructure!.pages[0].questions[0].children[0], item = submission.items[0];
    node.answers.unshift({ ...node.answers[0], itemId: `hwi_${"e".repeat(32)}`, index: 1, count: 2, region: { x: .2, y: .49, width: .035, height: .02 } });
    node.answers[1].index = 2; node.answers[1].count = 2;
    expect(homeworkQuestionContext(submission, item).focusRegion?.x).toBe(.6);
  });
  it.each(["stem", "illustration", "table", "option"])("returns the complete page when a necessary %s region cannot be verified", missing => {
    const submission = source(), root = submission.paperStructure!.pages[0].questions[0];
    if (missing === "stem") root.region = null;
    else if (missing === "illustration") root.illustrations[0].geometryVerified = false;
    else if (missing === "table") root.tables[0].region = null;
    else root.children[0].options[0].region = null;
    const context = homeworkQuestionContext(submission, submission.items[0]);
    expect(context.region).toBeNull(); expect(context.focusRegion?.x).toBe(.6);
    expect(context.media.every(element => element.region !== null)).toBe(true);
  });
  it.each(["unverified", "wrong-frame"])("does not place media or answers into an %s page frame", reason => {
    const submission = source(), page = submission.paperStructure!.pages[0];
    if (reason === "unverified") page.geometryVerified = false; else page.frameWidth = 2400;
    const context = homeworkQuestionContext(submission, submission.items[0]);
    expect(context.region).toBeNull(); expect(context.focusRegion).toBeNull(); expect(context.media).toEqual([]);
  });
  it("does not guess node ownership from matching titles or a duplicated item link", () => {
    const submission = source(), root = submission.paperStructure!.pages[0].questions[0];
    root.children[1].prompt = root.children[0].prompt;
    root.children[1].answers = [{ ...root.children[0].answers[0] }];
    const context = homeworkQuestionContext(submission, submission.items[0]);
    expect(context.structured).toBe(false); expect(context.region).toBeNull(); expect(context.media).toEqual([]);
  });
  it("does not reuse old answer coordinates when an unavailable projection has no linked nodes", () => {
    const submission = source(), page = submission.paperStructure!.pages[0];
    page.geometryVerified = false; page.questions = []; page.unassignedItemIds = [submission.items[0].id]; page.coverage.status = "unavailable";
    const context = homeworkQuestionContext(submission, submission.items[0]);
    expect(context.region).toBeNull(); expect(context.focusRegion).toBeNull(); expect(context.media).toEqual([]);
  });
  it("keeps saved submissions compatible and still protects a thin equation-only crop", () => {
    const submission = source(); delete submission.paperStructure;
    const context = homeworkQuestionContext(submission, submission.items[0]);
    expect(context.region).toBeNull(); expect(context.structured).toBe(false); expect(context.focusRegion?.x).toBe(.6);
  });
});
