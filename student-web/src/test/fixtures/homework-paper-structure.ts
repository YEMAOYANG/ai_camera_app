import { homeworkPaperStructureSchema } from "@/lib/contracts/homework";

/** Synthetic source-tree fixture; contains no uploaded homework or provider response. */
export function homeworkPaperStructureFixture(itemId: string, pageId: string) {
  return homeworkPaperStructureSchema.parse({
    schemaVersion: "mira.homework-paper-structure.v1", projectionVersion: "test.v1", sourceDigest: "a".repeat(64),
    coverage: { status: "partial", issues: [], linkedAnswers: 2, totalAnswers: 2 },
    pages: [{ pageId, geometryVerified: true, frameWidth: 1200, frameHeight: 1600, coverage: { status: "partial", issues: [] }, unassignedItemIds: [], questions: [{
      id: `hwq_${"a".repeat(32)}`, label: "一", prompt: "看图回答下面的小题", region: { x: .1, y: .08, width: .6, height: .08 }, geometryVerified: true,
      illustrations: [{ id: "shared-picture", region: { x: .1, y: .18, width: .6, height: .15 }, geometryVerified: true }],
      tables: [{ id: "shared-table", text: "共享表格", region: { x: .1, y: .35, width: .6, height: .1 }, geometryVerified: true }], options: [], answers: [],
      children: [{
        id: `hwq_${"b".repeat(32)}`, label: "（1）", prompt: "看上面的图，选择一张图片", region: { x: .1, y: .48, width: .6, height: .04 }, geometryVerified: true,
        illustrations: [], tables: [], options: [
          { id: "A", label: "A", text: "第一个印刷选项", region: { x: .15, y: .55, width: .15, height: .1 }, geometryVerified: true },
          { id: "B", label: "B", text: "第二个印刷选项", region: { x: .45, y: .55, width: .15, height: .1 }, geometryVerified: true },
        ], answers: [{ itemId, index: 1, count: 1, region: { x: .6, y: .49, width: .035, height: .02 }, geometryVerified: true }], children: [],
      }, {
        id: `hwq_${"c".repeat(32)}`, label: "（2）", prompt: "另一个小题，不属于当前作答", region: { x: .1, y: .8, width: .8, height: .1 }, geometryVerified: true,
        illustrations: [{ id: "sibling-picture", region: { x: .1, y: .9, width: .8, height: .09 }, geometryVerified: true }], options: [], tables: [],
        answers: [{ itemId: `hwi_${"f".repeat(32)}`, index: null, count: 0, region: null, geometryVerified: false }], children: [],
      }],
    }] }],
  });
}
