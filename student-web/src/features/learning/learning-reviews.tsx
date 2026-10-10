"use client";

import Link from "next/link";
import { ArrowRight, Backpack, Check, Clock3, Lightbulb, Pause, Play, RefreshCw, RotateCcw, Volume2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { Button } from "@/components/ui/button";
import type { Student } from "@/lib/contracts/student-session";
import { reviewAudioPath, reviewListSchema, reviewResponseSchema, type ReviewResponse, type ReviewSummary } from "@/lib/contracts/learning-review";
import { LearningListenButton, SubjectPicture } from "./learning-picture-navigation";
import { QuantityPicture } from "./quantity-picture";
import { PictureChoice, PicturePrompt } from "./review-picture-prompt";
import { HomeworkPaperImage } from "./homework-paper-overview";
import { HomeworkQuestionRecorder } from "./homework-question-recorder";

const labels: Record<string, string> = { pending: "准备好就开始", scheduled: "准备好就开始", in_progress: "接着上次的小任务", paused: "休息好了，接着玩", needs_schedule: "有空时再试试", completed: "这次复习完成啦", skipped: "这周先休息", superseded: "已有新的安排", content_gap: "老师还在准备图片和声音", rest: "这周先休息" };

function reviewGroup(review: ReviewSummary) {
  if (review.status === "completed") return "completed";
  if (review.totalQuestions > 0 && (["in_progress", "paused"].includes(review.status) || (review.currentIndex > 0 && ["pending", "scheduled", "needs_schedule"].includes(review.status)))) return "continue";
  if (["pending", "scheduled", "needs_schedule"].includes(review.status) && review.totalQuestions > 0) return "ready";
  return "other";
}

const reviewGroups = [
  { key: "continue", title: "接着完成" },
  { key: "ready", title: "可以开始" },
  { key: "completed", title: "已完成的复习" },
  { key: "other", title: "其他安排" },
] as const;

function ReviewRecord({ review }: { review: ReviewSummary }) {
  const group = reviewGroup(review);
  const action = group === "completed" ? "查看完成记录" : group === "continue" ? "继续复习" : group === "ready" ? "开始复习" : "查看安排";
  const week = /^(\d{4})-(\d{2})-(\d{2})$/.exec(review.weekStart);
  const weekLabel = week ? `${Number(week[2])} 月 ${Number(week[3])} 日这一周` : "";
  return <Link href={`/learning/reviews/${review.id}`} className={`learning-review-launch learning-review-record learning-review-record--${group}`} aria-label={`${action}：${review.title}${weekLabel ? `，${weekLabel}` : ""}`}>
    <SubjectPicture subject="chinese" />
    <span className="learning-review-play" aria-hidden="true">{group === "completed" ? <Check /> : group === "other" ? <Clock3 /> : <Play fill="currentColor" />}</span>
    <span className="learning-review-record-copy"><small>{weekLabel}</small><strong>{review.title}</strong><small>{group === "completed" ? `已完成 ${review.totalQuestions} 个小任务` : group === "continue" ? `已进行 ${Math.min(review.currentIndex, review.totalQuestions)} / ${review.totalQuestions} 个小任务` : group === "ready" ? `${review.totalQuestions} 个小任务 · 约 ${review.estimatedMinutes} 分钟` : labels[review.status] ?? "查看这次复习的安排"}</small><span className="learning-review-record-action">{action}<ArrowRight aria-hidden="true" /></span></span>
  </Link>;
}

async function readResponse(response: Response) {
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.message === "string" ? value.message : "暂时没连接上，请再试一次");
  return value;
}

export function ReviewInvitation({ compact = false }: { compact?: boolean }) {
  const [reviews, setReviews] = useState<ReviewSummary[] | null>(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/learning/reviews", { signal: controller.signal, cache: "no-store" })
      .then(readResponse).then(value => { if (!controller.signal.aborted) { setReviews(reviewListSchema.parse(value).reviews); setError(""); } })
      .catch(error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "复习暂时没有加载好"); });
    return () => controller.abort();
  }, [refresh]);
  const groups = reviewGroups.map(group => ({ ...group, items: reviews?.filter(item => reviewGroup(item) === group.key) ?? [] }));
  const first = groups.flatMap(group => group.items)[0];
  return <section className="learning-review-invitation" aria-label="复习与小测验">
    {error ? <div role="alert"><p>{error}</p><Button size="compact" variant="secondary" onClick={() => { setError(""); setReviews(null); setRefresh(v => v + 1); }}><RefreshCw />再试一次</Button></div>
      : !reviews ? <div className="learning-review-loading" role="status">正在打开复习…</div>
      : reviews.length ? <><div className="learning-review-list-toolbar"><p>点图片打开，没做完的可以接着来。</p>{(groups[0].items.length > 0 || groups[1].items.length > 0) && <LearningListenButton cue={groups[0].items.length ? "continue" : "review"} />}</div>
        {compact ? <><ReviewRecord review={first} /><Button asChild variant="quiet" size="compact"><Link href="/learning/reviews">查看全部复习<ArrowRight /></Link></Button></>
          : groups.filter(group => group.items.length).map(group => <section className="learning-review-group" key={group.key} aria-label={group.title}><h2>{group.title}<span>{group.items.length}</span></h2><div className="learning-review-records">{group.items.map(review => <ReviewRecord key={review.id} review={review} />)}</div></section>)}
      </> : <div className="learning-review-rest"><SubjectPicture subject="chinese" /><h2>还没有复习或小测验</h2><p>有新的复习时会放在这里，完成的记录也会保留。</p><Button asChild size="compact"><Link href="/learning">回到书包<ArrowRight /></Link></Button></div>}
  </section>;
}

export function useReviewVoice() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [failed, setFailed] = useState(false);
  const stop = useCallback(() => { audio.current?.pause(); audio.current = null; }, []);
  const play = useCallback((url: string | null) => {
    window.dispatchEvent(new Event("mira:learner-narration"));
    setFailed(false);
    if (!url) { setFailed(true); return; }
    const player = new Audio(url); audio.current = player;
    const onError = () => { if (audio.current === player) setFailed(true); };
    player.onerror = onError;
    void player.play().catch(onError);
  }, []);
  useEffect(() => {
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener("mira:learner-narration", stop);
    document.addEventListener("visibilitychange", hide);
    return () => { stop(); window.removeEventListener("mira:learner-narration", stop); document.removeEventListener("visibilitychange", hide); };
  }, [stop]);
  return { play, failed, stop };
}

export function LearningReviews({ student, reviewId }: { student: Student; reviewId?: string }) {
  const [homeworkOriginal, setHomeworkOriginal] = useState(false);
  return <SchoolbagShell student={student} className="learning-review-shell">
    <div className="learning-review-heading"><div><p>{reviewId ? "我的复习" : "我的书包"}</p><h1>{reviewId ? homeworkOriginal ? "看原图，再试一试" : "换个地方，再试一试" : "复习与小测验"}</h1></div><Button asChild variant="quiet" size="compact"><Link href={reviewId ? "/learning/reviews" : "/learning"}><Backpack />{reviewId ? "全部复习" : "回到书包"}</Link></Button></div>
    {reviewId ? <ReviewActivity key={reviewId} id={reviewId} onQuestionKind={setHomeworkOriginal} /> : <ReviewInvitation />}
  </SchoolbagShell>;
}

export function ReviewActivity({ id, onQuestionKind }: { id: string; onQuestionKind?: (homeworkOriginal: boolean) => void }) {
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const pendingRequest = useRef<{ key: string; requestId: string } | null>(null);
  const [selection, setSelection] = useState<string | null>(null);
  const voice = useReviewVoice();
  const load = useCallback(async (signal?: AbortSignal) => {
    const value = await fetch(`/api/learning/reviews/${id}`, { signal, cache: "no-store" }).then(readResponse);
    return reviewResponseSchema.parse(value);
  }, [id]);
  async function refresh() {
    try {
      setData(await load()); setError("");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "复习还没打开"); }
  }
  useEffect(() => {
    const c = new AbortController();
    load(c.signal).then(value => { if (!c.signal.aborted) { setData(value); setError(""); } })
      .catch(caught => { if (!c.signal.aborted) setError(caught instanceof Error ? caught.message : "复习还没打开"); });
    return () => c.abort();
  }, [load]);
  useEffect(() => { onQuestionKind?.(data?.currentQuestion?.renderer === "homework_original"); }, [data?.currentQuestion?.renderer, onQuestionKind]);

  async function send(operation: "actions" | "answers", values: Record<string, string | number>) {
    if (!data || busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); voice.stop();
    const key = JSON.stringify([operation, data.review.revision, values]);
    if (pendingRequest.current?.key !== key) pendingRequest.current = { key, requestId: crypto.randomUUID() };
    try {
      const result = await fetch(`/api/learning/reviews/${id}/${operation}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...values, revision: data.review.revision, requestId: pendingRequest.current.requestId }) });
      if (result.status === 409) { await refresh(); throw new Error("进度已更新，请继续当前小任务"); }
      const next = reviewResponseSchema.parse(await readResponse(result));
      pendingRequest.current = null; setData(next);
      if (next.currentQuestion?.id !== data.currentQuestion?.id) setSelection(null);
      const narration = values.action === "hint" ? next.currentQuestion?.hintAudioUrl : values.action === "explanation" ? next.currentQuestion?.explanationAudioUrl : next.feedback?.audioUrl || next.feedback?.explanationAudioUrl || ((values.action === "start" || values.action === "next") ? next.currentQuestion?.promptAudioUrl : null);
      if (narration) voice.play(reviewAudioPath(narration, id));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "还没保存好，请再试一次"); }
    finally { busyRef.current = false; setBusy(false); }
  }
  if (!data) return <section className="learning-review-rest" role={error ? "alert" : "status"}><p>{error || "正在打开你上次的小任务…"}</p>{error && <Button onClick={() => void refresh()}><RefreshCw />再试一次</Button>}</section>;
  const { review, currentQuestion: question, feedback } = data;
  const done = review.status === "completed";
  const playing = review.status === "in_progress";
  const answered = feedback?.answered === true || typeof feedback?.correct === "boolean";
  const replay = reviewAudioPath(feedback?.audioUrl || feedback?.explanationAudioUrl || question?.explanationAudioUrl || question?.hintAudioUrl || question?.promptAudioUrl, id);
  return <section className="learning-review-activity" aria-busy={busy}>
    <div className="learning-review-progress"><span>{review.title}</span><progress max={Math.max(1, review.totalQuestions)} value={review.currentIndex} aria-label="复习进度" /><span>{Math.min(review.currentIndex + (done ? 0 : 1), review.totalQuestions)} / {review.totalQuestions}</span></div>
    {error && <p className="learning-review-error" role="alert">{error}</p>}
    {done ? <div className="learning-review-rest"><Check className="learning-review-state-icon" aria-hidden="true" /><h2>这次复习完成啦</h2><p>你的学习记录已经保存，家长可以在 App 查看。</p><Button asChild><Link href="/learning"><Backpack />回到书包</Link></Button></div>
      : ["skipped", "superseded", "rest", "content_gap"].includes(review.status) ? <div className="learning-review-rest"><Backpack className="learning-review-state-icon" /><h2>{labels[review.status]}</h2><Button asChild><Link href="/learning">回到书包<ArrowRight /></Link></Button></div>
      : !playing ? <div className="learning-review-start"><SubjectPicture subject="chinese" /><div><h2>{labels[review.status] ?? "准备好了就开始"}</h2><p>约 {review.estimatedMinutes} 分钟，随时可以休息。</p><div className="learning-review-actions"><Button disabled={busy || !review.totalQuestions} onClick={() => void send("actions", { action: "start" })}><Play fill="currentColor" />{review.currentIndex ? "接着玩" : "开始"}</Button><LearningListenButton cue={review.currentIndex ? "continue" : "review"} /><Button size="compact" variant="quiet" disabled={busy} onClick={() => void send("actions", { action: "snooze", minutes: 20 })}><Clock3 />20 分钟后</Button></div></div></div>
      : question ? <><div className="learning-review-task-heading"><h2>{question.renderer === "homework_original" ? "看原图，再试一试" : question.prompt}</h2><Button size="compact" variant="secondary" aria-label="再听一遍题目" onClick={() => voice.play(reviewAudioPath(question.promptAudioUrl, id))}><Volume2 />{voice.failed ? "再试一次" : "听一听"}</Button></div>
        {"kind" in question.visual && question.visual.kind === "homework_original" && question.homeworkSource ? <div className="learning-review-question homework-original-review">
          <div className="learning-review-scene"><HomeworkPaperImage submissionId={question.visual.submissionId} page={{ id: question.visual.pageId, order: 0, rotation: 0, crop: null, width: question.visual.width, height: question.visual.height, status: "recognized", error: null, assetUrl: `/api/v2/student/learning/homework/${question.visual.submissionId}/pages/${question.visual.pageId}/image` }} region={question.visual.region} focusRegion={question.visual.answerRegion} alt="这次复习的原作业题目" /></div>
          <HomeworkQuestionRecorder key={question.id} endpoint={`/api/learning/homework/${question.homeworkSource.submissionId}/items/${question.homeworkSource.itemId}/tutor/transcribe`} itemRevision={question.homeworkSource.itemRevision} intent="answer" actionLabel="提交我的答案" disabled={busy || answered} onQuestion={value => void send("answers", { questionId: question.id, response: value })} />
        </div> : <div className="learning-review-question"><div className="learning-review-scene">{"kind" in question.visual ? question.visual.kind === "quantity_arithmetic" && <div className="homework-quantity-scene"><QuantityPicture count={question.visual.left} removed={question.visual.operation === "subtract" ? question.visual.right : 0} />{question.visual.operation === "add" && <><span aria-label="加上">+</span><QuantityPicture count={question.visual.right} /></>}<span aria-hidden="true">= ?</span></div> : <PicturePrompt scene={question.visual} label="看图片，听老师说" />}</div>
          <div className="learning-review-choices" role="group" aria-label="点图片作答">{question.options.map(option => <button key={option.value} type="button" disabled={busy || answered} aria-label={option.label} aria-pressed={(selection ?? question.selectedResponse) === option.value} onClick={() => { setSelection(option.value); void send("answers", { questionId: question.id, response: option.value }); }}>{typeof option.picture === "object" && "count" in option.picture ? <QuantityPicture count={option.picture.count} /> : <PictureChoice picture={option.picture} />}<span>{option.label}</span>{(selection ?? question.selectedResponse) === option.value && <span className="learning-review-choice-mark" aria-hidden="true"><Check /></span>}</button>)}</div>
        </div>}
        {feedback && <div className="learning-review-feedback" aria-live="polite">{feedback.correct === true ? <Check aria-label="答对了" /> : feedback.correct === false ? <RotateCcw aria-label="一起再看看" /> : <Lightbulb aria-hidden="true" />}<p>{feedback.message || feedback.hint || feedback.explanation}</p>{replay && <Button size="icon" variant="secondary" onClick={() => voice.play(replay)} aria-label="再听一遍老师的话"><Volume2 /></Button>}</div>}
        {!feedback && (question.hint || question.explanation) && <div className="learning-review-feedback" aria-live="polite"><Lightbulb aria-hidden="true" /><p>{question.explanation || question.hint}</p><Button size="icon" variant="secondary" onClick={() => voice.play(replay)} aria-label="再听一遍提示"><Volume2 /></Button></div>}
        <div className="learning-review-actions">{answered ? <Button disabled={busy} onClick={() => void send("actions", { action: "next" })}>继续<ArrowRight /></Button> : <Button variant="secondary" size="compact" disabled={busy} onClick={() => void send("actions", { action: "hint" })}><Lightbulb />给一点提示</Button>}<Button variant="quiet" size="compact" disabled={busy} onClick={() => void send("actions", { action: "pause" })}><Pause />休息一下</Button></div>
      </> : <div className="learning-review-rest"><h2>题目还没准备好</h2><Button onClick={() => void refresh()}><RefreshCw />再试一次</Button></div>}
    {review.coverage.contentGap && <p className="learning-review-note">这次先练已经准备好的部分，不需要凑满时间。</p>}
  </section>;
}
