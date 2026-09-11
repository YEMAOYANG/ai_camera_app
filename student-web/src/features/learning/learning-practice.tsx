"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, LoaderCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { practiceResponseSchema, type PracticeResponse } from "@/lib/contracts/learning-practice";
import type { Student } from "@/lib/contracts/student-session";

const subjects = [{ id: "chinese", label: "语文" }, { id: "math", label: "数学" }, { id: "english", label: "英语" }] as const;
async function practiceRequest(path: string, body?: object): Promise<PracticeResponse> {
  const response = await fetch(path, { method: body ? "POST" : "GET", cache: "no-store",
    ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.message || "练习暂时没有连接上");
  return practiceResponseSchema.parse(payload);
}

export function LearningPractice({ student, sessionId }: { student: Student; sessionId?: string }) {
  const router = useRouter();
  const [subject, setSubject] = useState<"chinese" | "math" | "english">("math");
  const [result, setResult] = useState<PracticeResponse | null>(null);
  const [feedback, setFeedback] = useState<PracticeResponse["evaluation"]>();
  const [answer, setAnswer] = useState("");
  const [sequence, setSequence] = useState<string[]>([]);
  const [busy, setBusy] = useState(Boolean(sessionId));
  const [error, setError] = useState("");
  const requestId = useRef<string | null>(null);
  const loadedSessionId = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId || loadedSessionId.current === sessionId) return;
    let active = true;
    practiceRequest(`/api/learning/practice/sessions/${encodeURIComponent(sessionId)}`)
      .then(value => { if (active) { loadedSessionId.current = sessionId; setResult(value); if (value.session) setSubject(value.session.subject); } })
      .catch(caught => { if (active) setError(caught instanceof Error ? caught.message : "暂时无法恢复练习"); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [sessionId]);

  async function start() {
    if (busy) return;
    setBusy(true); setError(""); setFeedback(undefined); setAnswer(""); setSequence([]);
    requestId.current ??= crypto.randomUUID();
    try {
      const value = await practiceRequest("/api/learning/practice/sessions", { requestId: requestId.current, subject, count: 5 });
      loadedSessionId.current = value.session?.id ?? null;
      setResult(value);
      if (value.session) router.replace(`/learning/practice?session=${value.session.id}`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "暂时无法开始练习"); }
    finally { setBusy(false); }
  }
  async function submit() {
    const session = result?.session, question = session?.currentQuestion;
    if (!session || !question || busy) return;
    setBusy(true); setError("");
    try {
      const value = await practiceRequest(`/api/learning/practice/sessions/${session.id}/answers`, {
        questionId: question.id, response: question.type === "sequence" ? sequence : answer,
      });
      setResult(value); setFeedback(value.evaluation); setAnswer(""); setSequence([]);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "答案还没保存，请再试一次"); }
    finally { setBusy(false); }
  }
  function chooseSubject(value: typeof subject) {
    setSubject(value); requestId.current = null; setResult(null); setError("");
  }
  const session = result?.session;
  const question = session?.currentQuestion;
  return (
    <div className="learning-space mira-doodle-grid">
      <main id="main-content" className="learning-main max-w-3xl">
        <Link href="/learning" className="focus-ring inline-flex min-h-12 items-center gap-2 font-bold text-[var(--mira-brand-deep)]"><ArrowLeft className="size-5" />回到学习书架</Link>
        <header className="my-7">
          <p className="learning-eyebrow">{student.displayName}的复习时间</p>
          <h1 className="mt-2 text-3xl font-black">学过的内容，练一练</h1>
          <p className="mt-3 text-lg leading-8 text-[var(--mira-muted)]">每次最多五题，只复习已经学完的课程。</p>
        </header>
        <section className="rounded-[28px] border-2 border-white bg-white p-6 shadow-[var(--mira-shadow-card)] sm:p-8" aria-live="polite">
          {error && <p role="alert" className="mb-5 rounded-2xl bg-amber-50 p-4 leading-7">{error}</p>}
          {busy && !result ? <p className="flex items-center gap-3 py-5 text-lg"><LoaderCircle className="size-6 animate-spin motion-reduce:animate-none" />正在取出复习题…</p> : feedback ? (
            <div>
              <h2 className="text-2xl font-black">{feedback.message}</h2>
              {feedback.explanation && <p className="mt-4 text-xl leading-9">{feedback.explanation}</p>}
              <Button className="mt-7 min-h-12" onClick={() => setFeedback(undefined)}>{session?.status === "completed" ? "看看这次练习" : "下一题"}</Button>
            </div>
          ) : session?.status === "completed" ? (
            <div>
              <CheckCircle2 className="mb-4 size-10 text-emerald-600" aria-hidden="true" />
              <h2 className="text-2xl font-black">这次复习完成啦！</h2>
              <p className="mt-4 text-xl">完成 {session.totalQuestions} 题，答对 {session.correctCount} 题。</p>
              <div className="mt-7 flex flex-wrap gap-4"><Link href="/learning" className="focus-ring inline-flex min-h-12 items-center rounded-2xl bg-[var(--mira-brand-deep)] px-6 font-bold text-white">回到学习书架</Link>
                <Button variant="quiet" onClick={() => { requestId.current = null; setResult(null); router.replace("/learning/practice"); }}>再选一组</Button></div>
            </div>
          ) : question ? (
            <div>
              <p className="font-bold text-[var(--mira-brand-deep)]">第 {(session?.currentQuestionIndex ?? 0) + 1} 题 / {session?.totalQuestions} 题</p>
              <h2 className="my-6 text-2xl font-black leading-10">{question.prompt}</h2>
              {(question.type === "single_choice" || question.type === "sequence") && question.choices.length ? (
                <div className="grid gap-3" role="group" aria-label={question.type === "sequence" ? "按顺序选择" : "选择答案"}>
                  {question.choices.map(choice => {
                    const position = sequence.indexOf(choice.id), selected = question.type === "sequence" ? position >= 0 : answer === choice.id;
                    return <button key={choice.id} disabled={busy || (question.type === "sequence" && selected)} aria-pressed={selected}
                      className={`focus-ring min-h-14 rounded-2xl border-2 px-5 py-3 text-left text-xl font-bold ${selected ? "border-[var(--mira-brand)] bg-blue-50" : "border-slate-200 bg-white"}`}
                      onClick={() => question.type === "sequence" ? setSequence(current => [...current, choice.id]) : setAnswer(choice.id)}>
                      {question.type === "sequence" && selected ? `${position + 1}. ` : ""}{choice.label}
                    </button>;
                  })}
                  {question.type === "sequence" && <Button variant="quiet" disabled={busy} onClick={() => setSequence([])}><RotateCcw className="size-4" />重新排列</Button>}
                </div>
              ) : <label className="block text-lg font-bold">你的答案<input autoComplete="off" value={answer} disabled={busy} onChange={event => setAnswer(event.target.value)}
                  inputMode={question.type === "numeric" ? "decimal" : "text"} className="focus-ring mt-3 block min-h-14 w-full rounded-2xl border-2 border-slate-200 px-5 py-3 text-2xl" /></label>}
              <Button className="mt-7 min-h-12" disabled={busy || (question.type === "sequence" ? sequence.length !== question.choices.length : !answer.trim())} onClick={() => void submit()}>{busy ? "正在保存…" : "提交答案"}</Button>
            </div>
          ) : (
            <div>
              {result?.session === null && <p className="mb-5 text-lg leading-8">{result.message}</p>}
              <h2 className="text-xl font-black">想复习哪一科？</h2>
              <div className="my-5 flex flex-wrap gap-3" role="group" aria-label="复习学科">{subjects.map(item => <button key={item.id} disabled={busy} aria-pressed={subject === item.id}
                className={`focus-ring min-h-12 rounded-2xl border-2 px-6 py-3 text-xl font-bold ${subject === item.id ? "border-[var(--mira-brand)] bg-blue-50" : "border-slate-200"}`} onClick={() => chooseSubject(item.id)}>{item.label}</button>)}</div>
              <Button className="min-h-12" disabled={busy} onClick={() => void start()}>{busy ? "正在准备…" : "开始复习"}</Button>
              {result?.session === null && <Link className="focus-ring ml-5 inline-flex min-h-12 items-center font-bold" href="/learning">先复习学过的课程</Link>}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
