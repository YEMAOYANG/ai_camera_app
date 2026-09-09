"use client";

import { ArrowRight, Check, CircleHelp, Eraser, Headphones, LoaderCircle, PenLine, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MiraBuddy } from "@/components/student/mira-buddy";
import { Button } from "@/components/ui/button";
import { submitLearningAnswer } from "@/features/learning/learning-client";
import { createClassroomAudioController, type NarrationPlaybackSource } from "@/features/classroom/speech-controller";
import type { ClassroomGameRules } from "@/lib/contracts/lesson-package";
import type { LearningAnswerResponse, LearningQuestion, LearningSession, LearningTeacherProfile } from "@/lib/contracts/learning";

type QuizPresentation = "standard" | "listen_tap_choice.v1";
type SubmitAnswer = typeof submitLearningAnswer;

export function ClassroomQuizScene({
  session,
  question,
  teacher,
  guided,
  onSession,
  onQuestion,
  onQuizComplete,
  enabled,
  questionRefs,
  presentation = "standard",
  gameRules,
  submitAnswer = submitLearningAnswer,
}: {
  session: LearningSession;
  question: LearningQuestion | null;
  teacher: LearningTeacherProfile;
  guided: boolean;
  onSession: (session: LearningSession) => void;
  onQuestion: (question: LearningQuestion | null) => void;
  onQuizComplete: () => void;
  enabled: boolean;
  questionRefs?: string[];
  presentation?: QuizPresentation;
  gameRules?: ClassroomGameRules;
  submitAnswer?: SubmitAnswer;
}) {
  const [text, setText] = useState("");
  const [selected, setSelected] = useState("");
  const [sequence, setSequence] = useState<string[]>([]);
  const [result, setResult] = useState<LearningAnswerResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [listening, setListening] = useState(false);
  const [listeningSource, setListeningSource] = useState<NarrationPlaybackSource | "idle">("idle");
  const audio = useMemo(() => createClassroomAudioController(), []);
  const guidedGame = presentation !== "standard";
  const responseReady = useMemo(() => {
    if (!question) return false;
    if (question.type === "single_choice") return Boolean(selected);
    if (question.type === "sequence") return sequence.length === question.choices.length;
    return Boolean(text.trim());
  }, [question, selected, sequence, text]);

  useEffect(() => () => audio.stop(), [audio]);

  function resetResponse() {
    setText("");
    setSelected("");
    setSequence([]);
    setResult(null);
    setError("");
  }

  async function submit() {
    if (!question || !responseReady || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const body = question.type === "single_choice"
        ? { response: { kind: "single_choice", optionId: selected } }
        : question.type === "sequence"
          ? { response: { kind: "sequence", items: sequence } }
          : { answer: text.trim() };
      const answer = await submitAnswer(session.id, body);
      setResult(answer);
      onSession(answer.session);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "答案没有提交成功");
    } finally {
      setSubmitting(false);
    }
  }

  function continueAfterFeedback() {
    if (!result) return;
    if (result.canRetry) {
      onQuestion(result.nextQuestion || result.session.currentQuestion || question);
      resetResponse();
      return;
    }
    const next = result.nextQuestion || result.session.currentQuestion;
    const reachedSceneBoundary = Boolean(questionRefs?.length) && (!next || !questionRefs?.includes(next.id));
    if (result.completed || reachedSceneBoundary) {
      onQuestion(result.completed ? null : next);
      onQuizComplete();
      resetResponse();
      return;
    }
    onQuestion(next);
    resetResponse();
  }

  async function listenToQuestion() {
    if (!question || listening) return;
    audio.stop();
    setListening(true);
    const controller = new AbortController();
    try {
      await audio.playNarration({
        text: question.prompt,
        teacher,
        onSource: setListeningSource,
      }, controller.signal);
    } catch {
      // Switching scenes or replaying another voice intentionally cancels this utterance.
    } finally {
      setListening(false);
    }
  }

  if (!question) {
    return <div className="grid min-h-[360px] place-items-center p-8 text-center"><div><MiraBuddy mood="thinking" className="mx-auto w-28" /><h2 className="mt-3 text-2xl font-black">练习题正在排队</h2><p className="mt-2 text-[var(--mira-muted)]">先听完老师讲解，题目准备好就会出现。</p></div></div>;
  }

  if (!enabled) {
    return <div className="grid min-h-[360px] place-items-center p-8 text-center"><div><MiraBuddy mood="reading" className="mx-auto w-28" /><h2 className="mt-3 text-2xl font-black">先听 Mira 讲完这一小段</h2><p className="mt-2 text-[var(--mira-muted)]">讲解完成后，练习会自动解锁。</p></div></div>;
  }

  if (questionRefs?.length && !questionRefs.includes(question.id)) {
    return <div className="classroom-segment-complete" role="status"><MiraBuddy mood="celebrate" className="mx-auto w-28" /><Sparkles className="classroom-segment-sparkle size-7" /><h2>这一关已经完成</h2><p>可以回顾，也可以继续下一步。</p></div>;
  }

  const currentNumber = Math.min(session.currentQuestionIndex + 1, session.totalQuestions);
  const segmentNumber = questionRefs?.indexOf(question.id) ?? -1;
  const resultNextQuestion = result?.nextQuestion || result?.session.currentQuestion || null;
  const resultEndsSegment = Boolean(
    result && questionRefs?.length && (!resultNextQuestion || !questionRefs.includes(resultNextQuestion.id)),
  );
  const numberLabel = segmentNumber >= 0
    ? `第 ${segmentNumber + 1} 题 / 共 ${questionRefs?.length} 题`
    : `第 ${currentNumber} 题 / 共 ${session.totalQuestions} 题`;
  return (
    <section className={`classroom-quiz-scene ${guidedGame ? "is-guided-game" : ""}`} aria-labelledby="classroom-question-title">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3"><MiraBuddy mood={result ? (result.correct ? "celebrate" : "thinking") : "hello"} className="w-16" /><div><p className="text-sm font-extrabold text-[var(--mira-brand-deep)]">{guidedGame ? widgetLabel() : guided ? "Mira 陪你练" : "自己来挑战"}</p><h2 id="classroom-question-title" className="text-xl font-black">{numberLabel}</h2></div></div>
        <div className="hidden h-3 w-36 overflow-hidden rounded-full bg-[var(--mira-border-soft)] sm:block"><div className="h-full rounded-full bg-[var(--mira-brand)]" style={{ width: `${(session.currentQuestionIndex / Math.max(1, session.totalQuestions)) * 100}%` }} /></div>
      </div>
      {guidedGame ? <div className="classroom-game-brief"><span><Headphones className="size-5" />{shortInstruction()}</span>{gameRules ? <small>答对后进入下一步</small> : null}</div> : null}
      <div className="mt-5 rounded-[24px] bg-[var(--mira-bg)] p-5 sm:p-7">
        <div className="classroom-question-heading"><p className="text-[clamp(21px,3.2vw,31px)] font-black leading-relaxed">{question.prompt}</p>{guidedGame ? <button type="button" className={`focus-ring classroom-listen-question ${listening ? "is-listening" : ""}`} onClick={() => void listenToQuestion()} aria-label="用设备朗读再听一遍题目"><span className="classroom-listen-ripple" aria-hidden="true" />{listening ? <Volume2 className="size-6" /> : <Headphones className="size-6" />}<span>{listening ? "正在朗读" : "设备听题"}</span><small>{listeningSource === "silent" ? "音频不可用" : "开发降级"}</small></button> : null}</div>
        <div className="mt-6">
          {question.type === "single_choice" ? <div className={`grid gap-3 sm:grid-cols-2 ${guidedGame ? "classroom-choice-garden" : ""}`}>{question.choices.map((choice, index) => <button key={choice.id} type="button" disabled={Boolean(result)} onClick={() => setSelected(choice.id)} className={`focus-ring classroom-choice min-h-16 rounded-[18px] border-2 px-5 text-left text-lg font-extrabold ${selected === choice.id ? "is-selected border-[var(--mira-brand)] bg-[var(--mira-brand-wash)] text-[var(--mira-brand-deep)]" : "border-white bg-white"}`}><span className="classroom-choice-index">{String.fromCharCode(65 + index)}</span><span>{choice.label}</span>{selected === choice.id ? <Check className="ml-auto size-5" /> : null}</button>)}</div> : null}
          {question.type === "sequence" ? <div><div className="min-h-16 rounded-[18px] border-2 border-dashed border-[var(--mira-border)] bg-white p-3">{sequence.length ? <div className="flex flex-wrap gap-2">{sequence.map((id, index) => <span key={id} className="rounded-full bg-[var(--mira-brand-wash)] px-3 py-2 font-bold text-[var(--mira-brand-deep)]">{index + 1}. {question.choices.find((item) => item.id === id)?.label}</span>)}</div> : <p className="py-2 text-center text-[var(--mira-subtle)]">按正确顺序点下面的内容</p>}</div><div className="mt-3 grid gap-2 sm:grid-cols-2">{question.choices.map((choice) => <button key={choice.id} type="button" disabled={sequence.includes(choice.id) || Boolean(result)} onClick={() => setSequence((items) => [...items, choice.id])} className="focus-ring min-h-14 rounded-[17px] border-2 border-white bg-white px-4 font-bold disabled:opacity-40">{choice.label}</button>)}</div>{!result && sequence.length ? <Button variant="quiet" size="compact" className="mt-3" onClick={() => setSequence([])}><Eraser className="size-4" />重新排列</Button> : null}</div> : null}
          {!question.choices.length ? <label className="block"><span className="sr-only">我的答案</span><input value={text} disabled={Boolean(result)} onChange={(event) => setText(event.target.value)} inputMode={question.type === "numeric" ? "decimal" : "text"} className="focus-ring h-16 w-full rounded-[18px] border-2 border-white bg-white px-5 text-xl font-extrabold outline-none focus:border-[var(--mira-brand)]" placeholder="把答案写在这里" /></label> : null}
        </div>
      </div>
      {error ? <p className="mt-4 rounded-[16px] bg-[#fff1ee] p-4 font-bold text-[var(--mira-danger)]" role="alert">{error}</p> : null}
      {result ? <div className={`classroom-answer-feedback mt-4 rounded-[20px] p-5 ${result.correct ? "is-correct bg-[var(--mira-mint)]" : "is-retry bg-[var(--mira-sun-soft)]"}`} role="status" aria-live="assertive"><div className="flex gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-full bg-white">{result.correct ? <Check className="size-5 text-[var(--mira-success)]" /> : <CircleHelp className="size-5 text-[var(--mira-warning)]" />}</span><div><p className="font-black">{result.feedback}</p>{result.hint ? <p className="mt-1 text-[var(--mira-muted)]">小提示：{result.hint}</p> : null}</div></div><Button className="mt-4 w-full sm:w-auto" onClick={continueAfterFeedback}>{result.canRetry ? "按提示再试" : resultEndsSegment ? "完成练习" : result.completed ? "看看总结" : "下一题"}<ArrowRight className="size-5" /></Button></div> : <Button className="mt-5 w-full sm:w-auto" onClick={submit} disabled={!responseReady || submitting}>{submitting ? <LoaderCircle className="size-5 animate-spin" /> : <PenLine className="size-5" />}{submitting ? "正在检查…" : guidedGame ? "选好了" : "提交答案"}</Button>}
    </section>
  );
}

function widgetLabel() {
  return "听音小花园";
}

function shortInstruction() {
  return "先听，再选择";
}
