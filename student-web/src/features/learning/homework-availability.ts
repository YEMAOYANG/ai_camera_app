import type { HomeworkSubmission } from "@/lib/contracts/homework";
import { homeworkStudentCopy } from "./homework-student-copy";
import { homeworkCorrectionSelfReported, homeworkCorrectionWorkflowDone } from "./homework-correction-status";
import { homeworkPaperJudgment, homeworkTutorQuestions } from "./homework-paper-context";

const failedHomeworkStatuses = ["provider_unknown", "failed", "error"];

export function homeworkProcessing(submission: HomeworkSubmission) {
  return !failedHomeworkStatuses.includes(submission.status) && (submission.processing ?? ["processing", "queued", "working", "quality_check", "recognizing", "checking", "media_preparing"].includes(submission.status));
}

export function homeworkAvailability(submission: HomeworkSubmission) {
  const lowReading = ["primary_1", "primary_2"].includes(submission.gradeCode);
  const questions = homeworkTutorQuestions(submission), wrong = questions.filter(item => homeworkPaperJudgment(item) === "incorrect");
  const pendingOriginal = (submission.originalPaperSummary?.unknown ?? questions.filter(item => homeworkPaperJudgment(item) === "unknown").length) > 0 || !!submission.originalSummary?.pending || !!submission.originalSummary?.blank;
  if (!pendingOriginal && wrong.length && wrong.some(item => homeworkCorrectionSelfReported(item.studentCorrection)) && wrong.every(item => homeworkCorrectionWorkflowDone(item.studentCorrection) || (!item.studentCorrection && item.correctionStatus === "corrected"))) return "self_reported";
  if (submission.readyForStudent && submission.items.some(item => item.correctionStatus !== "corrected" && item.readyForStudent && (!lowReading || !!item.picture))) return "ready";
  if ([...submission.tutorItems, ...(submission.originalPaperItems ?? [])].some(item => item.tutorAvailable)) return "ready";
  if (failedHomeworkStatuses.includes(submission.status)) return "needs_check";
  if (homeworkProcessing(submission)) return "processing";
  if (submission.originalSummary?.pending || submission.originalSummary?.blank || submission.error || submission.retryAllowed || submission.status === "needs_confirmation") return "needs_check";
  if (submission.studentSummary?.awaitingMedia) return "media_waiting";
  if (submission.items.length > 0 && submission.items.every(item => item.correctionStatus === "corrected") && (submission.originalSummary?.unsupported || submission.studentSummary?.unsupportedCorrection)) return "completed_partial";
  if (submission.originalSummary?.unsupported || submission.studentSummary?.unsupportedCorrection) return "unsupported";
  if (submission.items.length > 0 && submission.items.every(item => item.correctionStatus === "corrected")) return "completed";
  if (submission.originalSummary?.total && submission.originalSummary.correct === submission.originalSummary.total) return "clear";
  return "unavailable";
}

export const homeworkAvailabilityLabels = { ready: homeworkStudentCopy.title, processing: "老师正在准备图片和声音", needs_check: "这份原作业还需要老师看一看", media_waiting: "老师的语音还没准备好", unsupported: "老师的原题讲解还没准备好", self_reported: "纸上订正已标记，待复习", completed_partial: "可订正的题目已完成", completed: "已和老师完成订正", clear: "这份作业没有需要订正的题目", unavailable: "这份作业暂时没有可订正的练习" };
