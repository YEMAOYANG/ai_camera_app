"use client";

import { ArrowLeft, ArrowRight, Check, CircleHelp, Eraser, GripVertical, LoaderCircle, PenLine, Sparkles, TrainFront, X } from "lucide-react";
import { useState, type DragEvent } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { Button } from "@/components/ui/button";
import { submitLearningAnswer } from "@/features/learning/learning-client";
import type { ClassroomGameRules } from "@/lib/contracts/lesson-package";
import type { LearningAnswerResponse, LearningQuestion, LearningSession } from "@/lib/contracts/learning";

type SubmitAnswer = typeof submitLearningAnswer;

export function SortOrderScene({
  session,
  question,
  enabled,
  questionRefs,
  gameRules,
  onSession,
  onQuestion,
  onQuizComplete,
  submitAnswer = submitLearningAnswer,
}: {
  session: LearningSession;
  question: LearningQuestion | null;
  enabled: boolean;
  questionRefs: string[];
  gameRules?: ClassroomGameRules;
  onSession: (session: LearningSession) => void;
  onQuestion: (question: LearningQuestion | null) => void;
  onQuizComplete: () => void;
  submitAnswer?: SubmitAnswer;
}) {
  const [sequence, setSequence] = useState<string[]>([]);
  const [result, setResult] = useState<LearningAnswerResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (!question) return <SortState title="排序素材正在排队" copy="先听老师讲解，素材准备好后会自动出现。" />;
  if (!enabled) return <SortState title="先听老师讲完这一小段" copy="讲解完成后，顺序小火车会自动解锁。" />;
  if (questionRefs.length && !questionRefs.includes(question.id)) return <SortState complete title="这一关已经完成" copy="可以回顾，也可以继续下一步。" />;
  if (question.type !== "sequence" || question.choices.length < 2) {
    return <SortState title="排序素材制作中" copy="这道题还没有发布可排序项目，网页不会根据文字猜正确顺序。" />;
  }

  const ready = sequence.length === question.choices.length;
  const available = question.choices.filter((choice) => !sequence.includes(choice.id));

  function move(itemId: string, delta: number) {
    setSequence((items) => reorderSequence(items, itemId, delta));
  }

  function dropBefore(event: DragEvent, targetId: string) {
    event.preventDefault();
    const draggedId = event.dataTransfer.getData("text/plain");
    if (!sequence.includes(draggedId) || draggedId === targetId) return;
    setSequence((items) => {
      const next = items.filter((id) => id !== draggedId);
      next.splice(next.indexOf(targetId), 0, draggedId);
      return next;
    });
  }

  async function submit() {
    if (!ready || result || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const answer = await submitAnswer(session.id, { response: { kind: "sequence", items: sequence } });
      setResult(answer);
      onSession(answer.session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "排序结果没有提交成功");
    } finally {
      setSubmitting(false);
    }
  }

  function continueAfterFeedback() {
    if (!result) return;
    if (result.canRetry) {
      onQuestion(result.nextQuestion || result.session.currentQuestion || question);
      setSequence([]);
      setResult(null);
      return;
    }
    const next = result.nextQuestion || result.session.currentQuestion;
    const reachedBoundary = !next || !questionRefs.includes(next.id);
    onQuestion(result.completed ? null : next);
    setSequence([]);
    setResult(null);
    if (result.completed || reachedBoundary) onQuizComplete();
  }

  const finalFeedback = Boolean(result && !result.canRetry && (!result.nextQuestion || !questionRefs.includes(result.nextQuestion.id)));
  return (
    <section className="controlled-game sort-order-game" aria-labelledby="sort-order-title">
      <header className="controlled-game-header"><div><p><TrainFront className="size-5" />顺序小火车</p><h2 id="sort-order-title">{question.prompt}</h2></div><span>{sequence.length} / {question.choices.length} 节</span></header>
      <div className="controlled-game-rule"><Sparkles className="size-5" /><p>{gameRules?.instructions[0] || "点下面的卡片放进小火车，再用箭头调整顺序。"}</p><small>答案只交给服务端检查</small></div>

      <div className="sort-train" aria-label="当前排列" aria-live="polite">
        <span className="sort-train-engine"><TrainFront className="size-7" /><small>出发</small></span>
        {sequence.length ? <ol>{sequence.map((id, index) => {
          const choice = question.choices.find((item) => item.id === id);
          return <li key={id} draggable={!result} onDragStart={(event) => event.dataTransfer.setData("text/plain", id)} onDragOver={(event) => event.preventDefault()} onDrop={(event) => dropBefore(event, id)}><div><GripVertical className="size-5" aria-hidden="true" /><span>{index + 1}</span><strong>{choice?.label}</strong></div><nav aria-label={`调整${choice?.label}的位置`}><button type="button" className="focus-ring" disabled={index === 0 || Boolean(result)} onClick={() => move(id, -1)} aria-label="向前移动"><ArrowLeft className="size-4" /></button><button type="button" className="focus-ring" disabled={index === sequence.length - 1 || Boolean(result)} onClick={() => move(id, 1)} aria-label="向后移动"><ArrowRight className="size-4" /></button><button type="button" className="focus-ring" disabled={Boolean(result)} onClick={() => setSequence((items) => items.filter((item) => item !== id))} aria-label="移出小火车"><X className="size-4" /></button></nav></li>;
        })}</ol> : <p>从下面选第一节车厢</p>}
      </div>

      <div className="sort-card-pool" aria-label="还可以选择的项目">{available.map((choice) => <button key={choice.id} type="button" className="focus-ring" disabled={Boolean(result)} onClick={() => setSequence((items) => [...items, choice.id])}><span>{choice.label}</span><ArrowRight className="size-5" /></button>)}</div>
      {!result && sequence.length ? <Button variant="quiet" size="compact" onClick={() => setSequence([])}><Eraser className="size-4" />全部放回去</Button> : null}
      {error ? <p className="controlled-game-error" role="alert">{error}</p> : null}
      {result ? <SortFeedback result={result} final={finalFeedback} onContinue={continueAfterFeedback} /> : <Button className="controlled-game-submit" onClick={() => void submit()} disabled={!ready || submitting}>{submitting ? <LoaderCircle className="size-5 animate-spin" /> : <PenLine className="size-5" />}{submitting ? "正在检查…" : "排好啦"}</Button>}
    </section>
  );
}

export function reorderSequence(items: string[], itemId: string, delta: number) {
  const from = items.indexOf(itemId);
  const to = Math.max(0, Math.min(items.length - 1, from + delta));
  if (from < 0 || from === to) return items;
  const next = [...items];
  next.splice(from, 1);
  next.splice(to, 0, itemId);
  return next;
}

function SortState({ title, copy, complete = false }: { title: string; copy: string; complete?: boolean }) {
  return <div className="controlled-game-state" role="status"><MiraBuddy mood={complete ? "celebrate" : "thinking"} className="w-28" /><h2>{title}</h2><p>{copy}</p></div>;
}

function SortFeedback({ result, final, onContinue }: { result: LearningAnswerResponse; final: boolean; onContinue: () => void }) {
  return <div className={`controlled-game-feedback ${result.correct ? "is-correct" : "is-retry"}`} role="status" aria-live="assertive"><span>{result.correct ? <Check className="size-5" /> : <CircleHelp className="size-5" />}</span><div><strong>{result.feedback}</strong>{result.hint ? <p>小提示：{result.hint}</p> : null}</div><Button onClick={onContinue}>{result.canRetry ? "按提示再试" : final ? "完成练习" : "下一题"}<ArrowRight className="size-5" /></Button></div>;
}
