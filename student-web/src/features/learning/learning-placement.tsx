"use client";

import { ArrowRight, CheckCircle2, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { LearningClientError } from "@/features/learning/learning-client";
import { TapObjectsInput } from "@/features/learning/tap-objects-input";
import type { LearningSubject } from "@/lib/contracts/learning";
import { placementResponseSchema, type PlacementResponse } from "@/lib/contracts/learning-placement";

async function placementRequest(path: string, subject: LearningSubject, body?: object, signal?: AbortSignal) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET", cache: "no-store", signal,
    ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = payload as { message?: string; error?: string };
    throw new LearningClientError(response.status, detail.error || "placement_unavailable", detail.message || "基础摸底暂时没有连接上");
  }
  const parsed = placementResponseSchema.safeParse(payload);
  if (!parsed.success || parsed.data.subject !== subject) throw new Error("基础摸底暂时没有加载好，请再试一次");
  return parsed.data;
}

export function LearningPlacement({ subject, onResolved, onReturnToLesson, onActivityChange }: {
  subject: LearningSubject;
  onResolved: () => void;
  onReturnToLesson: () => void;
  onActivityChange?: (active: boolean) => void;
}) {
  const router = useRouter();
  const [response, setResponse] = useState<PlacementResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [answer, setAnswer] = useState("");
  const [sequence, setSequence] = useState<string[]>([]);
  const [answerUnconfirmed, setAnswerUnconfirmed] = useState(false);
  const [returnRequired, setReturnRequired] = useState(false);
  const pendingAnswer = useRef<{ questionId: string; answer: string | string[] } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const attempt = response?.attempt;
  const question = attempt?.currentQuestion;
  const outcome = response?.status === "completed" ? attempt?.result : null;
  const active = busy || attempt?.status === "in_progress";

  useEffect(() => {
    onActivityChange?.(active);
    return () => onActivityChange?.(false);
  }, [active, onActivityChange]);

  useEffect(() => {
    const controller = new AbortController();
    void placementRequest(`/api/learning/placement?${new URLSearchParams({ subject })}`, subject, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { setResponse(value); setError(""); } })
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return;
        if (caught instanceof LearningClientError && caught.status === 401) { router.replace("/unlock"); return; }
        setError(caught instanceof Error ? caught.message : "基础摸底暂时没有加载好");
      });
    return () => controller.abort();
  }, [subject, revision, router]);

  useEffect(() => {
    if (question || outcome) heading.current?.focus();
  }, [question?.id, outcome, question]);

  function handleError(caught: unknown) {
    if (caught instanceof LearningClientError && caught.status === 401) { router.replace("/unlock"); return; }
    if (caught instanceof LearningClientError && caught.status === 409
      && !["placement_answer_immutable", "placement_question_out_of_order"].includes(caught.code)) {
      // A retired source or changed learning scope cannot be repaired by
      // replaying the same answer. Refresh the path before entering a lesson.
      setReturnRequired(true); setAnswerUnconfirmed(false); pendingAnswer.current = null;
    }
    setError(caught instanceof Error ? caught.message : "暂时没有连接上，请再试一次");
  }

  function accept(value: PlacementResponse) {
    setResponse(value); setAnswer(""); setSequence([]); setAnswerUnconfirmed(false); setReturnRequired(false); pendingAnswer.current = null;
  }

  async function start() {
    if (busy || !response?.canStart || !response.lesson) return;
    setBusy(true); setError("");
    try { accept(await placementRequest("/api/learning/placement", subject, { lessonId: response.lesson.lessonId })); }
    catch (caught) { handleError(caught); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (busy || returnRequired || !attempt || !question) return;
    pendingAnswer.current ??= { questionId: question.id, answer: question.type === "sequence" || question.type === "tap_objects" ? sequence : answer.trim() };
    setBusy(true); setError("");
    try { accept(await placementRequest(`/api/learning/placement/${attempt.id}/answers`, subject, pendingAnswer.current)); }
    catch (caught) { setAnswerUnconfirmed(true); handleError(caught); }
    finally { setBusy(false); }
  }

  async function resume() {
    if (busy || !attempt) return;
    setBusy(true); setError("");
    try { accept(await placementRequest(`/api/learning/placement/${attempt.id}`, subject)); }
    catch (caught) { handleError(caught); }
    finally { setBusy(false); }
  }

  if (response?.status === "not_required") return null;
  const disabled = busy || answerUnconfirmed;
  const canSubmit = question && (question.type === "sequence" ? sequence.length === question.choices.length
    : question.type === "tap_objects" ? sequence.length > 0 : Boolean(answer.trim()));

  return <section className={`learning-placement${question ? " is-answering" : ""}`} aria-label="基础摸底" aria-busy={busy}>
    {error && <div className="learning-placement-error" role="alert"><p>{error}</p>
      {answerUnconfirmed && <p>正在确认刚才的答案。可以重新保存同一个答案，或恢复已保存的进度。</p>}
      {returnRequired && <Button onClick={onResolved}>回到基础课<ArrowRight size={18} aria-hidden="true" /></Button>}
      {!response && !returnRequired && <Button variant="secondary" onClick={() => setRevision(value => value + 1)}>重新连接</Button>}
      {answerUnconfirmed && <Button variant="secondary" disabled={busy} onClick={() => void resume()}>恢复已保存的进度</Button>}
    </div>}
    {returnRequired ? null : !response && !error ? <p role="status">正在查看从哪里衔接…</p> : outcome ? <div className="learning-placement-result">
      <p className="space-eyebrow">基础摸底完成</p>
      <h3 ref={heading} tabIndex={-1}>{outcome.passed ? "这一步已经学会了" : "找到需要再练的地方了"}</h3>
      <p>独立完成 {outcome.totalQuestions} 题，答对 {outcome.correctCount} 题。{outcome.passed ? "学习路线会保留这次掌握记录。" : "跟着老师再学一遍，把这一步学稳。"}</p>
      <Button onClick={onResolved}>{outcome.passed ? "继续下一步" : "回到基础课"}<ArrowRight size={18} aria-hidden="true" /></Button>
    </div> : question && attempt ? <div className="learning-placement-question">
      <div className="learning-placement-topline"><p className="space-eyebrow">{response?.lesson?.title} · 独立试一试</p><span>第 {attempt.currentQuestionIndex + 1} 题 / {attempt.totalQuestions} 题</span></div>
      <progress aria-label="基础摸底进度" max={attempt.totalQuestions} value={attempt.answeredCount} />
      <h3 ref={heading} tabIndex={-1}>{question.prompt}</h3>
      {question.type === "tap_objects" ? <TapObjectsInput objects={question.objects || []} value={sequence} onChange={setSequence} disabled={disabled} />
        : question.type === "single_choice" || question.type === "sequence" ? <div className="learning-placement-choices" role="group" aria-label={question.type === "sequence" ? "按顺序选择" : "选择答案"}>
          {question.choices.map((choice, index) => {
            const position = sequence.indexOf(choice.id);
            const selected = question.type === "sequence" ? position >= 0 : answer === choice.id;
            return <button type="button" key={choice.id} className="focus-ring learning-placement-choice" aria-pressed={selected}
              disabled={disabled || question.type === "sequence" && selected}
              onClick={() => question.type === "sequence" ? setSequence(current => [...current, choice.id]) : setAnswer(choice.id)}>
              <span className="learning-placement-choice-marker" aria-hidden="true">{question.type === "sequence" ? selected ? position + 1 : "—" : String.fromCharCode(65 + index)}</span>
              <span>{choice.label}</span>{selected && <CheckCircle2 size={20} aria-hidden="true" />}
            </button>;
          })}
          {question.type === "sequence" && <Button variant="quiet" disabled={disabled || !sequence.length} onClick={() => setSequence([])}><RotateCcw size={18} aria-hidden="true" />重新排列</Button>}
        </div> : <label className="learning-placement-input-label">你的答案<input className="focus-ring" autoComplete="off" spellCheck={false}
          inputMode={question.type === "numeric" ? "decimal" : "text"} maxLength={4000} value={answer} disabled={disabled} onChange={event => setAnswer(event.target.value)} /></label>}
      <div className="learning-placement-actions"><Button disabled={busy || !canSubmit} onClick={() => void submit()}>
        {busy ? "正在保存…" : answerUnconfirmed ? "重新保存这个答案" : "提交答案"}<ArrowRight size={18} aria-hidden="true" />
      </Button><p>答案会自动保存，稍后回来可以接着完成。</p></div>
    </div> : response && <div className="learning-placement-intro">
      <div><h3>{response.status === "available" ? "这一步已经会了？" : response.status === "observation_required" ? "这一步要实际做一做" : response.status === "needs_learning" ? "先把这一步学稳" : "基础摸底正在准备"}</h3>
        <p>{response.status === "available" ? `独立做几道「${response.lesson?.title}」的题，看看是否已经掌握。` : response.message}</p></div>
      {response.canStart ? <Button variant="secondary" disabled={busy} onClick={() => void start()}>{busy ? "正在打开…" : "先试一试"}<ArrowRight size={18} aria-hidden="true" /></Button>
        : <button type="button" className="focus-ring learning-path-text-button" onClick={onReturnToLesson}>回到基础课</button>}
    </div>}
  </section>;
}
