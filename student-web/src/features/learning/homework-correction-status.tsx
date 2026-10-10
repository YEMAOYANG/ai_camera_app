import { Check, Hand, HelpCircle, PencilLine, RefreshCw } from "lucide-react";
import type { HomeworkStudentCorrection } from "@/lib/contracts/homework-tutor";

export function homeworkCorrectionCompleted(correction: HomeworkStudentCorrection | undefined) {
  return correction?.status === "corrected" && correction.answerEvaluationAllowed && correction.correct === true && correction.attempts > 0;
}

export function homeworkCorrectionSelfReported(correction: HomeworkStudentCorrection | undefined) {
  return correction?.status === "self_reported" && correction.answerEvaluationAllowed && correction.selfReportedCompleted === true;
}

/** Workflow acknowledgement is separate from answering correctly. */
export function homeworkCorrectionWorkflowDone(correction: HomeworkStudentCorrection | undefined) {
  return homeworkCorrectionCompleted(correction) || homeworkCorrectionSelfReported(correction);
}

/** Only the server's saved same-question answer record may report correction. */
export function HomeworkCorrectionStatus({ correction }: { correction: HomeworkStudentCorrection }) {
  const completed = homeworkCorrectionCompleted(correction);
  const selfReported = homeworkCorrectionSelfReported(correction);
  const retry = correction.answerEvaluationAllowed && correction.status === "needs_practice" && correction.correct === false && correction.attempts > 0;
  const pending = !correction.answerEvaluationAllowed || correction.status === "needs_review" || (correction.status === "corrected" && !completed);
  const state = completed ? "corrected" : selfReported ? "self_reported" : retry ? "needs_practice" : pending ? "needs_review" : "not_started";
  return <div className="homework-tutor-correction" role="status" aria-label="这道题的订正记录" data-state={state}>
    {completed ? <Check aria-hidden="true" /> : selfReported ? <PencilLine aria-hidden="true" /> : retry ? <RefreshCw aria-hidden="true" /> : pending ? <HelpCircle aria-hidden="true" /> : <Hand aria-hidden="true" />}
    <div><strong>{completed ? "这道题已订正" : selfReported ? "已标记在纸上改好" : retry ? "再试一次" : pending ? "可以说说你的想法" : "听完讲解，自己试试"}</strong>
      <p>{completed ? "同一道题已经答对，还要在复习时再试试。" : selfReported ? "已保存你的标记，还没核对新答案，复习时再试试。" : retry ? "看看原题，听完讲解后，再说说你的答案。" : pending ? "参考答案还没核对清楚，这次不判断对错。" : "自己作答后才会记录订正，听讲解不算答对。"}</p>
    </div>
  </div>;
}
