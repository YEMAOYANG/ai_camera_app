import type { HomeworkItem, HomeworkPage, HomeworkPaperQuestion, HomeworkPaperRegion, HomeworkSubmission } from "@/lib/contracts/homework";

import { homeworkGradingNeedsReview, homeworkReferenceAvailable } from "./homework-student-quality";

function sourceAnswerConfirmed(item: HomeworkItem) {
  return item.reviewContext?.recognitionConfirmed === true && !item.reviewContext.recognitionNeedsConfirmation && item.reviewContext.answerState !== "unclear";
}

export function homeworkTutorQuestions(submission: HomeworkSubmission): HomeworkItem[] {
  const merged = new Map<string, HomeworkItem>(submission.items.map(item => [item.id, item]));
  for (const item of [...submission.tutorItems, ...(submission.originalPaperItems ?? [])]) {
    const regular = merged.get(item.id);
    merged.set(item.id, { ...regular, ...item, reviewContext: item.reviewContext ?? regular?.reviewContext,
      assessmentMethod: item.assessmentMethod ?? regular?.assessmentMethod,
      readyForStudent: regular?.readyForStudent ?? false, correctionStatus: regular?.correctionStatus ?? "pending",
      hintViewed: regular?.hintViewed ?? false, explanationViewed: regular?.explanationViewed ?? false,
      voice: regular?.voice ?? {}, tutorAvailable: item.tutorAvailable || regular?.tutorAvailable });
  }
  return [...merged.values()];
}
export function homeworkPaperJudgment(item: HomeworkItem): "correct" | "incorrect" | "unknown" {
  const grading = item.reviewContext?.grading;
  // Current source/reference gates supersede an older provider verdict or
  // quality flag. This is the paper judgment, never independent mastery.
  if (grading?.referenceGate) return homeworkReferenceAvailable(item) ? grading.status : "unknown";
  if (homeworkGradingNeedsReview(item)) return "unknown";
  if (grading) return grading.status;
  if (sourceAnswerConfirmed(item) && ["correct", "incorrect"].includes(item.status)) return item.status as "correct" | "incorrect";
  return "unknown";
}

type Region = HomeworkPaperRegion;
export type HomeworkQuestionMedia = { id: string; kind: "illustration" | "table" | "option"; label: string | null; region: Region };
type QuestionMatch = { pageId: string; pageGeometryVerified: boolean; frameWidth?: number; frameHeight?: number; path: HomeworkPaperQuestion[] };

function usable(region: Region | null | undefined): region is Region {
  return !!region && region.width > 0 && region.height > 0;
}
function contains(outer: Region, inner: Region) {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width + .000001 && inner.y + inner.height <= outer.y + outer.height + .000001;
}
function completePreview(region: Region | null | undefined, focus: Region | null): Region | null {
  // OCR can locate only an equation line and omit the illustrations above it.
  if (!usable(region) || region.height < .08 || region.width * region.height < .02 || (focus && !contains(region, focus))) return null;
  return region;
}
function union(regions: Region[]): Region | null {
  if (!regions.length) return null;
  const x = Math.min(...regions.map(region => region.x)), y = Math.min(...regions.map(region => region.y));
  return { x, y, width: Math.max(...regions.map(region => region.x + region.width)) - x, height: Math.max(...regions.map(region => region.y + region.height)) - y };
}
function matches(submission: HomeworkSubmission, itemId: string): QuestionMatch[] {
  const found: QuestionMatch[] = [];
  for (const page of submission.paperStructure?.pages ?? []) {
    const visit = (nodes: HomeworkPaperQuestion[], ancestors: HomeworkPaperQuestion[]) => {
      for (const node of nodes) {
        const path = [...ancestors, node];
        // A duplicate link is ambiguous even when it appears in the same node.
        for (const answer of node.answers) if (answer.itemId === itemId) found.push({ pageId: page.pageId, pageGeometryVerified: page.geometryVerified, frameWidth: page.frameWidth, frameHeight: page.frameHeight, path });
        visit(node.children, path);
      }
    };
    visit(page.questions, []);
  }
  return found;
}

/** Uses source-tree membership, never a guessed title, OCR index or sibling region. */
export function homeworkQuestionContext(submission: HomeworkSubmission, item: HomeworkItem, requestedRegion?: Region | null): {
  page: HomeworkPage | undefined; region: Region | null; focusRegion: Region | null; media: HomeworkQuestionMedia[]; structured: boolean;
} {
  const original = item.reviewContext, page = submission.pages.find(page => page.id === original?.pageId);
  const fallbackFocus = original?.grading?.geometryVerified && usable(original.grading.answerRegion) ? original.grading.answerRegion : null;
  const fallbackRegion = original?.grading && !original.grading.geometryVerified ? null : completePreview(requestedRegion ?? original?.region, fallbackFocus);
  const fallback = { page, region: fallbackRegion, focusRegion: fallbackFocus, media: [], structured: false };
  if (!submission.paperStructure) return fallback;
  const sourcePage = submission.paperStructure.pages.find(sourcePage => sourcePage.pageId === page?.id);
  if (!sourcePage?.geometryVerified || sourcePage.frameWidth !== page?.width || sourcePage.frameHeight !== page?.height) return { ...fallback, region: null, focusRegion: null };
  const found = matches(submission, item.id);
  // A saved but unlinked/ambiguous structure must not silently restore an unsafe OCR crop.
  if (found.length !== 1 || found[0].pageId !== page?.id) return { ...fallback, region: null };
  const match = found[0], node = match.path.at(-1)!, answer = node.answers.find(answer => answer.itemId === item.id)!;
  if (!match.pageGeometryVerified || match.frameWidth !== page.width || match.frameHeight !== page.height) return { ...fallback, region: null, focusRegion: null };
  const focusRegion = answer.geometryVerified && usable(answer.region) ? answer.region : fallbackFocus;
  const regions: Region[] = [], media: HomeworkQuestionMedia[] = [];
  let incomplete = false;
  for (const owner of match.path) {
    // Shared stems are actual ancestors. Include their own source region, not siblings.
    if (owner === node || owner.prompt.trim()) {
      if (owner.geometryVerified && usable(owner.region)) regions.push(owner.region);
      else incomplete = true;
    }
    for (const [kind, elements] of [["illustration", owner.illustrations], ["table", owner.tables]] as const) {
      for (const element of elements) {
        if (!element.geometryVerified || !usable(element.region)) { incomplete = true; continue; }
        regions.push(element.region);
        media.push({ id: `${owner.id}:${kind}:${element.id}`, kind, label: null, region: element.region });
      }
    }
  }
  // Only the closest explicitly owning option set belongs to the current branch.
  const optionOwner = [...match.path].reverse().find(owner => owner.options.length);
  for (const option of optionOwner?.options ?? []) {
    if (!option.geometryVerified || !usable(option.region)) { incomplete = true; continue; }
    regions.push(option.region);
    media.push({ id: `${optionOwner!.id}:option:${option.id}`, kind: "option", label: option.label, region: option.region });
  }
  if (requestedRegion) regions.push(requestedRegion);
  if (focusRegion) regions.push(focusRegion);
  const region = incomplete ? null : completePreview(union(regions), focusRegion);
  const uniqueMedia = media.filter((element, index) => media.findIndex(other => other.kind === element.kind && other.region.x === element.region.x && other.region.y === element.region.y && other.region.width === element.region.width && other.region.height === element.region.height) === index);
  return { page, region, focusRegion, media: uniqueMedia, structured: true };
}
