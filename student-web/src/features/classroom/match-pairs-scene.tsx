"use client";

import { ArrowRight, Check, CircleHelp, Eraser, Link2, LoaderCircle, PenLine, Sparkles } from "lucide-react";
import { useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { Button } from "@/components/ui/button";
import { submitLearningAnswer } from "@/features/learning/learning-client";
import type { ClassroomGameRules } from "@/lib/contracts/lesson-package";
import type { LearningAnswerResponse, LearningQuestion, LearningSession } from "@/lib/contracts/learning";

type SubmitAnswer = typeof submitLearningAnswer;

export function MatchPairsScene({
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
  const [leftArmed, setLeftArmed] = useState(false);
  const [selectedOptionId, setSelectedOptionId] = useState("");
  const [result, setResult] = useState<LearningAnswerResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (!question) return <ControlledGameState title="配对素材正在排队" copy="先听老师讲解，素材准备好后会自动出现。" />;
  if (!enabled) return <ControlledGameState title="先听老师讲完这一小段" copy="讲解完成后，配对游戏会自动解锁。" />;
  if (questionRefs.length && !questionRefs.includes(question.id)) return <ControlledGameState complete title="这一关已经完成" copy="可以回顾，也可以继续下一步。" />;
  if (question.type !== "single_choice" || question.choices.length < 2) {
    return <ControlledGameState title="配对素材制作中" copy="这道题不是服务端可判定的选择题，网页不会自行猜配对答案。" />;
  }

  async function submit() {
    if (!selectedOptionId || result || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const answer = await submitAnswer(session.id, {
        response: { kind: "single_choice", optionId: selectedOptionId },
      });
      setResult(answer);
      onSession(answer.session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "配对结果没有提交成功");
    } finally {
      setSubmitting(false);
    }
  }

  function resetBoard() {
    setLeftArmed(false);
    setSelectedOptionId("");
    setResult(null);
    setError("");
  }

  function continueAfterFeedback() {
    if (!result) return;
    if (result.canRetry) {
      onQuestion(result.nextQuestion || result.session.currentQuestion || question);
      resetBoard();
      return;
    }
    const next = result.nextQuestion || result.session.currentQuestion;
    const reachedBoundary = !next || !questionRefs.includes(next.id);
    onQuestion(result.completed ? null : next);
    resetBoard();
    if (result.completed || reachedBoundary) onQuizComplete();
  }

  const currentNumber = Math.max(1, questionRefs.indexOf(question.id) + 1);
  const selectedChoice = question.choices.find((choice) => choice.id === selectedOptionId);
  const finalFeedback = Boolean(result && !result.canRetry && (!result.nextQuestion || !questionRefs.includes(result.nextQuestion.id)));
  return (
    <section className="controlled-game match-pairs-game" aria-labelledby="match-pairs-title">
      <header className="controlled-game-header">
        <div><p><Link2 className="size-5" />配对小花园</p><h2 id="match-pairs-title">找出和线索最合适的一张卡</h2></div>
        <span>第 {currentNumber} 对 / 共 {questionRefs.length || 1} 对</span>
      </header>
      <div className="controlled-game-rule"><Sparkles className="size-5" /><p>{gameRules?.instructions[0] || "先点左边线索，再点右边卡片，把它们配成一对。"}</p><small>每一对都由服务端检查</small></div>
      <div className="match-pairs-board" aria-label="配对区域">
        <div className="match-pairs-column" aria-label="左侧线索">
          <p>第一步 · 点线索</p>
          <button type="button" disabled={Boolean(result)} className={`focus-ring match-pair-card match-clue-card ${leftArmed ? "is-active" : ""} ${selectedOptionId ? "is-paired" : ""}`} aria-pressed={leftArmed} onClick={() => { setLeftArmed(true); if (!result) setSelectedOptionId(""); }}><span>?</span><strong>{question.prompt}</strong>{selectedOptionId ? <Check className="size-5" /> : null}</button>
        </div>
        <div className="match-pairs-bridge" aria-hidden="true"><Link2 className="size-7" /><span>{selectedOptionId ? "配好一对" : leftArmed ? "再选右边" : "一左一右"}</span></div>
        <div className="match-pairs-column" aria-label="右侧选项">
          <p>第二步 · 选配对卡</p>
          {question.choices.map((choice, index) => <button key={choice.id} type="button" disabled={!leftArmed || Boolean(result)} className={`focus-ring match-pair-card side-right ${selectedOptionId === choice.id ? "is-paired" : ""}`} aria-pressed={selectedOptionId === choice.id} onClick={() => setSelectedOptionId(choice.id)}><strong>{choice.label}</strong><span>{String.fromCharCode(65 + index)}</span></button>)}
        </div>
      </div>
      {!result && selectedChoice ? <div className="match-current-pair" aria-live="polite"><span>{question.prompt}</span><Link2 className="size-4" /><strong>{selectedChoice.label}</strong><Button variant="quiet" size="compact" onClick={() => setSelectedOptionId("")}><Eraser className="size-4" />重配</Button></div> : null}
      {error ? <p className="controlled-game-error" role="alert">{error}</p> : null}
      {result ? <ControlledFeedback result={result} onContinue={continueAfterFeedback} final={finalFeedback} /> : <Button className="controlled-game-submit" onClick={() => void submit()} disabled={!selectedOptionId || submitting}>{submitting ? <LoaderCircle className="size-5 animate-spin" /> : <PenLine className="size-5" />}{submitting ? "正在检查…" : "配好啦"}</Button>}
    </section>
  );
}

function ControlledGameState({ title, copy, complete = false }: { title: string; copy: string; complete?: boolean }) {
  return <div className="controlled-game-state" role="status"><MiraBuddy mood={complete ? "celebrate" : "thinking"} className="w-28" /><h2>{title}</h2><p>{copy}</p></div>;
}

function ControlledFeedback({ result, onContinue, final }: { result: LearningAnswerResponse; onContinue: () => void; final: boolean }) {
  return <div className={`controlled-game-feedback ${result.correct ? "is-correct" : "is-retry"}`} role="status" aria-live="assertive"><span>{result.correct ? <Check className="size-5" /> : <CircleHelp className="size-5" />}</span><div><strong>{result.feedback}</strong>{result.hint ? <p>小提示：{result.hint}</p> : null}</div><Button onClick={onContinue}>{result.canRetry ? "按提示再试" : final ? "完成练习" : "下一对"}<ArrowRight className="size-5" /></Button></div>;
}
