"use client";

import { PencilLine, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { homeworkDetailSchema, type HomeworkDetail, type HomeworkItem, type HomeworkSubmission } from "@/lib/contracts/homework";
import type { HomeworkStudentCorrection } from "@/lib/contracts/homework-tutor";
import { homeworkCorrectionCompleted, homeworkCorrectionSelfReported } from "./homework-correction-status";
import { homeworkReferenceAvailable } from "./homework-student-quality";
import { homeworkPaperJudgment, homeworkTutorQuestions } from "./homework-paper-context";

/** A paper-work acknowledgement never submits an answer or changes its grade. */
export function HomeworkPaperCompletion({ submission, item, correction = item.studentCorrection, disabled, onData, onLockChange }: { submission: HomeworkSubmission; item: HomeworkItem; correction?: HomeworkStudentCorrection; disabled?: boolean; onData?: (value: HomeworkDetail) => void; onLockChange?: (locked: boolean) => void }) {
  const [saved, setSaved] = useState<{ correction: HomeworkStudentCorrection; base: HomeworkStudentCorrection | undefined } | null>(null), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(false), [error, setError] = useState("");
  const pending = useRef<{ action: "self_complete" | "reopen"; key: string } | null>(null), sending = useRef(false);
  // A fresh server answer supersedes acknowledgement even when clocks match.
  const current = saved && saved.base === correction ? saved.correction : correction;
  useEffect(() => { onLockChange?.(busy || uncertain); return () => onLockChange?.(false); }, [busy, uncertain, onLockChange]);
  const allowed = current?.answerEvaluationAllowed && homeworkReferenceAvailable(item) && homeworkPaperJudgment(item) === "incorrect" && !homeworkCorrectionCompleted(current);
  function receive(value: unknown) {
    const detail = homeworkDetailSchema.parse(value), latest = homeworkTutorQuestions(detail.submission).find(question => question.id === item.id);
    if (detail.submission.id !== submission.id) throw new Error("作业记录不一致，请重新打开原题");
    if (detail.submission.revision !== submission.revision || !latest || latest.revision !== item.revision) { onData?.(detail); throw new Error("原题已更新，请回到原作业重新打开"); }
    onData?.(detail);
    if (latest.studentCorrection) setSaved({ correction: latest.studentCorrection, base: correction });
    const requested = pending.current;
    if (requested && latest.studentCorrection && (homeworkCorrectionCompleted(latest.studentCorrection) || (requested.action === "self_complete" ? homeworkCorrectionSelfReported(latest.studentCorrection) : !homeworkCorrectionSelfReported(latest.studentCorrection)))) { pending.current = null; setUncertain(false); setError(""); }
  }
  async function query() {
    const response = await fetch(`/api/learning/homework/${submission.id}`, { cache: "no-store" }), value = await response.json();
    if (!response.ok) throw new Error(value.message || "订正标记还没核实，请稍后查看");
    receive(value);
  }
  async function mark() {
    if (!allowed || disabled || sending.current || uncertain) return;
    sending.current = true; setBusy(true); setError("");
    pending.current = { action: homeworkCorrectionSelfReported(current) ? "reopen" : "self_complete", key: crypto.randomUUID() };
    try {
      const response = await fetch(`/api/learning/homework/${submission.id}/items/${item.id}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ itemRevision: item.revision, action: pending.current.action, idempotencyKey: pending.current.key }) }), value = await response.json();
      if (!response.ok) { if (response.status >= 400 && response.status < 500) pending.current = null; throw new Error(value.message || "订正标记还没保存，请查看当前记录"); }
      receive(value);
      if (pending.current) setUncertain(true);
    } catch (failure) {
      let reconciled = false;
      if (pending.current) { setUncertain(true); try { await query(); reconciled = pending.current === null; } catch { /* Read only after a lost response; never manufacture another write identity. */ } }
      if (!reconciled) setError(failure instanceof Error ? failure.message : "正在核实订正标记，不会重复提交");
    } finally { sending.current = false; setBusy(false); }
  }
  if (!allowed && !uncertain && !error) return null;
  return <div className="homework-tutor-paper-completion" aria-busy={busy}>
    {allowed && <><Button size="compact" variant="quiet" disabled={disabled || busy || uncertain} onClick={() => void mark()}>{homeworkCorrectionSelfReported(current) ? <RefreshCw /> : <PencilLine />}{busy ? "正在保存标记…" : homeworkCorrectionSelfReported(current) ? "继续订正" : "我在纸上改好了"}</Button><p>{homeworkCorrectionSelfReported(current) ? "已保存纸上订正标记，还没核对新答案。" : "只保存纸上订正标记，老师还没核对新答案。"}</p></>}
    {error && <p role="alert">{error}</p>}
    {(uncertain || error) && <Button size="compact" variant="secondary" disabled={busy} onClick={() => void query().catch(failure => setError(failure instanceof Error ? failure.message : "订正记录还没打开"))}><RefreshCw />查看订正标记</Button>}
    {uncertain && <p role="status">正在核实订正标记，不会重复提交。</p>}
  </div>;
}
