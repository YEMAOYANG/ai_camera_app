import type { HomeworkItem } from "@/lib/contracts/homework";
import type { HomeworkTutorTurn } from "@/lib/contracts/homework-tutor";

/** The backend owns verification. Legacy Tencent results without that decision
 * must not become student answers merely because two model replies agree. */
export function homeworkGradingNeedsReview(item: HomeworkItem) {
  const grading = item.reviewContext?.grading;
  if (!grading) return false;
  if (grading.referenceGate && (!grading.referenceGate.available || !["provider_consistent", "exact", "human_verified"].includes(grading.referenceGate.status))) return true;
  if (grading.studentQuality) return grading.studentQuality.status !== "verified";
  return grading.source === "tencent" || grading.provider === "tencent";
}

export function homeworkTeachingNeedsReview(turn: HomeworkTutorTurn | undefined, item: HomeworkItem) {
  if (!turn) return false;
  if (turn.teachingQuality) return !["verified", "guidance"].includes(turn.teachingQuality.status);
  const grading = item.reviewContext?.grading;
  return grading?.source === "tencent" || grading?.provider === "tencent";
}

/** A same-question reference permits teaching and correction, never mastery. */
export function homeworkReferenceAvailable(item: HomeworkItem) {
  const gate = item.reviewContext?.grading?.referenceGate;
  if (gate) return gate.available && ["provider_consistent", "exact", "human_verified"].includes(gate.status);
  return !homeworkGradingNeedsReview(item);
}

/** A provisional provider verdict locates questions only. It does not change
 * studentQuality, permit a reference answer, or unlock independent practice. */
export function homeworkProvisionalVerdict(item: HomeworkItem) {
  const grading = item.reviewContext?.grading;
  if (grading?.studentQuality?.status === "verified") return undefined;
  if (grading?.providerVerdictBlockedReason) return undefined;
  if (!grading?.referenceGate || !homeworkReferenceAvailable(item)) return undefined;
  const verdict = grading?.providerVerdict;
  return verdict?.source === "tencent" && verdict.provisional === true && verdict.countsForAbility === false && verdict.status === grading.status ? verdict : undefined;
}
