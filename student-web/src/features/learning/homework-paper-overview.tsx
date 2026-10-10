"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, ArrowRight, BookOpen, Check, Clock3, Hand, HelpCircle, PencilLine, Play, Pointer, RefreshCw, Volume2, X } from "lucide-react";
import { useState, type CSSProperties } from "react";
import { Button } from "@/components/ui/button";
import { homeworkImagePath, type HomeworkDetail, type HomeworkItem, type HomeworkPage, type HomeworkSubmission } from "@/lib/contracts/homework";
import { homeworkAvailability, homeworkAvailabilityLabels } from "./homework-availability";
import { LearningListenButton, SubjectPicture } from "./learning-picture-navigation";
import { teacherForSubject } from "./teacher-registry";
import { homeworkQuestionContext, homeworkTutorQuestions, homeworkPaperJudgment } from "./homework-paper-context";
export { homeworkTutorQuestions, homeworkPaperJudgment } from "./homework-paper-context";
import { homeworkGradingNeedsReview, homeworkProvisionalVerdict, homeworkReferenceAvailable } from "./homework-student-quality";
import { HomeworkMathText } from "./homework-math-text";
import { homeworkStudentCopy } from "./homework-student-copy";
import { homeworkCorrectionCompleted, homeworkCorrectionSelfReported, homeworkCorrectionWorkflowDone } from "./homework-correction-status";
import { HomeworkPaperCompletion } from "./homework-paper-completion";

type Region = NonNullable<NonNullable<HomeworkItem["reviewContext"]>["region"]>;
const completedStates = ["completed", "completed_partial", "clear", "self_reported"];
const subjectNames: Record<string, string> = { math: "数学", chinese: "语文", english: "英语", science: "科学" };
function correctionCompleted(item: HomeworkItem) {
  return item.studentCorrection ? homeworkCorrectionCompleted(item.studentCorrection) : item.correctionStatus === "corrected";
}
function correctionWorkflowDone(item: HomeworkItem) {
  return item.studentCorrection ? homeworkCorrectionWorkflowDone(item.studentCorrection) : item.correctionStatus === "corrected";
}
export function practiceReady(submission: HomeworkSubmission, item: HomeworkItem) {
  return !homeworkGradingNeedsReview(item) && submission.readyForStudent && item.readyForStudent && !correctionWorkflowDone(item) && !item.reviewContext?.recognitionNeedsConfirmation && item.reviewContext?.answerState !== "unclear" && (!["primary_1", "primary_2"].includes(submission.gradeCode) || !!item.picture);
}
function sourceQuestionTitle(item: HomeworkItem, fallbackOrdinal = 1) {
  const label = item.reviewContext?.sourceQuestionLabel?.trim();
  const title = label ? `原题 ${label}` : `题目图片 ${item.reviewContext?.originalOrdinal ?? fallbackOrdinal}`;
  return (item.reviewContext?.answerCount ?? 0) > 1 ? `${title} · 第 ${item.reviewContext?.answerIndex ?? 1} 个答案` : title;
}
function sourceAnswerConfirmed(item: HomeworkItem) {
  return item.reviewContext?.recognitionConfirmed === true && !item.reviewContext.recognitionNeedsConfirmation && item.reviewContext.answerState !== "unclear";
}
export function homeworkPaperDisplayJudgment(item: HomeworkItem): "correct" | "incorrect" | "unknown" {
  const verified = homeworkPaperJudgment(item);
  return verified !== "unknown" ? verified : homeworkProvisionalVerdict(item)?.status ?? "unknown";
}
function questionPriority(item: HomeworkItem) {
  return correctionWorkflowDone(item) ? 4 : homeworkPaperDisplayJudgment(item) === "incorrect" ? 0 : item.status === "blank" ? 1 : homeworkPaperDisplayJudgment(item) === "unknown" ? 2 : 3;
}
function JudgmentPicture({ item }: { item: HomeworkItem }) {
  const judgment = homeworkPaperDisplayJudgment(item);
  return judgment === "correct" ? <Check aria-hidden="true" /> : judgment === "incorrect" ? <X aria-hidden="true" /> : <HelpCircle aria-hidden="true" />;
}
function judgmentLabel(item: HomeworkItem) {
  const provisional = homeworkProvisionalVerdict(item);
  if (provisional) return provisional.status === "correct" ? homeworkStudentCopy.checkCorrect : homeworkStudentCopy.checkIncorrect;
  if (homeworkGradingNeedsReview(item) && homeworkPaperJudgment(item) === "unknown") return "老师还要核实原题";
  if (item.reviewContext?.grading?.answerState === "blank" || item.reviewContext?.answerState === "blank") return "这里还没作答，老师陪你试试";
  if (item.reviewContext?.grading?.studentQuality?.status === "verified") return homeworkPaperJudgment(item) === "correct" ? "核对后答对" : homeworkPaperJudgment(item) === "incorrect" ? "核对后再试试" : "老师看原图讲解";
  return homeworkPaperJudgment(item) === "correct" ? homeworkStudentCopy.checkCorrect : homeworkPaperJudgment(item) === "incorrect" ? homeworkStudentCopy.checkIncorrect : "老师看原图讲解";
}
function usableRegion(region: Region | null | undefined): region is Region {
  return !!region && region.width > 0 && region.height > 0;
}
function paddedRegion(region: Region): Region {
  const x = Math.max(0, region.x - .012), y = Math.max(0, region.y - .002);
  return { x, y, width: Math.min(1, region.x + region.width + .012) - x, height: Math.min(1, region.y + region.height + .002) - y };
}
/** The picture and its local pointer layer must use the same original-page crop. */
export function homeworkPaperCropRegion(region?: Region | null): Region | null {
  return usableRegion(region) ? paddedRegion(region) : null;
}
function containsRegion(outer: Region, inner: Region) {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width + .000001 && inner.y + inner.height <= outer.y + outer.height + .000001;
}
function markerRegion(item: HomeworkItem) {
  const context = item.reviewContext;
  if (!context || (context.grading ? !context.grading.geometryVerified : !sourceAnswerConfirmed(item))) return null;
  if (usableRegion(context.grading?.answerRegion)) return context.grading.answerRegion;
  return (context.answerCount ?? 1) === 1 && usableRegion(context.region) ? context.region : null;
}
function markerGroups(items: HomeworkItem[]) {
  const groups: { region: Region; items: HomeworkItem[] }[] = [];
  for (const item of items) {
    const region = markerRegion(item); if (!region) continue;
    const touching = groups.filter(group => region.x < group.region.x + group.region.width && region.x + region.width > group.region.x && region.y < group.region.y + group.region.height && region.y + region.height > group.region.y);
    if (!touching.length) { groups.push({ region, items: [item] }); continue; }
    const regions = [region, ...touching.map(group => group.region)], x = Math.min(...regions.map(r => r.x)), y = Math.min(...regions.map(r => r.y));
    for (const group of touching) groups.splice(groups.indexOf(group), 1);
    groups.push({ region: { x, y, width: Math.max(...regions.map(r => r.x + r.width)) - x, height: Math.max(...regions.map(r => r.y + r.height)) - y }, items: [...touching.flatMap(group => group.items), item] });
  }
  return groups;
}

/** Browser fetch preserves the student cookie; Next's image optimizer cannot forward it. */
export function HomeworkPaperImage({ submissionId, page, region, focusRegion, alt, className = "", allowRetry = true, onImageState }: { submissionId: string; page: HomeworkPage; region?: Region | null; focusRegion?: Region | null; alt: string; className?: string; allowRetry?: boolean; onImageState?: (loaded: boolean) => void }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const src = homeworkImagePath(page.assetUrl, submissionId, page.id);
  const failed = !!src && failedSrc === src;
  const crop = homeworkPaperCropRegion(region);
  const frame: CSSProperties = { aspectRatio: crop ? `${page.width * crop.width} / ${page.height * crop.height}` : `${page.width} / ${page.height}` };
  const imageStyle: CSSProperties = crop ? { position: "absolute", width: `${100 / crop.width}%`, height: `${100 / crop.height}%`, left: `${-crop.x / crop.width * 100}%`, top: `${-crop.y / crop.height * 100}%`, maxWidth: "none" } : { width: "100%", height: "100%", objectFit: "contain" };
  const visibleArea = crop ?? { x: 0, y: 0, width: 1, height: 1 };
  const focus = usableRegion(focusRegion) && containsRegion(visibleArea, focusRegion) ? { left: `${(focusRegion.x - visibleArea.x) / visibleArea.width * 100}%`, top: `${(focusRegion.y - visibleArea.y) / visibleArea.height * 100}%`, width: `${focusRegion.width / visibleArea.width * 100}%`, height: `${focusRegion.height / visibleArea.height * 100}%` } : null;
  return <div className={`homework-paper-image ${className}${failed || !src ? " is-unavailable" : ""}`} style={frame}>
    {src && !failed && loadedSrc !== src && <div className="homework-photo-loading" aria-hidden="true"><RefreshCw /><span>正在打开原作业图片…</span></div>}
    {src && !failed ? <Image key={retry} src={src} width={page.width} height={page.height} alt={alt} unoptimized style={imageStyle} onLoad={() => { setLoadedSrc(src); onImageState?.(true); }} onError={() => { setFailedSrc(src); setLoadedSrc(null); onImageState?.(false); }} />
      : <div className="homework-photo-unavailable"><span>原作业图片暂时没打开</span>{src && allowRetry && <Button size="compact" variant="quiet" onClick={() => { setFailedSrc(null); setRetry(v => v + 1); }}><RefreshCw />重新看图</Button>}</div>}
    {src && !failed && loadedSrc === src && focus && <span className="homework-answer-focus" style={focus} aria-hidden="true" />}
  </div>;
}

export function HomeworkQuestionPicture({ submission, item, allowRetry = true, region: requestedRegion, alt }: { submission: HomeworkSubmission; item: HomeworkItem; allowRetry?: boolean; region?: Region | null; alt?: string }) {
  const { page, region, focusRegion } = homeworkQuestionContext(submission, item, requestedRegion);
  return page ? <HomeworkPaperImage submissionId={submission.id} page={page} region={region} focusRegion={focusRegion} alt={alt ?? sourceQuestionTitle(item)} allowRetry={allowRetry} />
    : <div className="homework-question-fallback"><p>原图位置还没确认</p>{item.picture ? <strong>{item.picture.left} {item.picture.operation === "add" ? "+" : "−"} {item.picture.right} = ?</strong> : <HomeworkMathText text={item.prompt} />}</div>;
}

function OriginalQuestionMedia({ submission, item }: { submission: HomeworkSubmission; item: HomeworkItem }) {
  const { page, media } = homeworkQuestionContext(submission, item);
  if (!page || !media.length) return null;
  const renderMedia = (elements: typeof media) => <div className="homework-source-media-grid">{elements.map((element, index) => <div key={element.id} className="homework-source-media-picture"><HomeworkPaperImage submissionId={submission.id} page={page} region={element.region} alt={element.kind === "option" ? `原题选项图片 ${element.label ?? index + 1}` : element.kind === "table" ? `原题表格图片 ${index + 1}` : `原题配图 ${index + 1}`} allowRetry={false} /></div>)}</div>;
  return <div className="homework-source-media" role="group" aria-label="这道原题的配图和选项">{renderMedia(media.slice(0, 6))}{media.length > 6 && <details><summary>看看其余原题图片</summary>{renderMedia(media.slice(6))}</details>}</div>;
}

export function HomeworkOriginalQuestion({ submission, item, neutralAnswer = false }: { submission: HomeworkSubmission; item: HomeworkItem; neutralAnswer?: boolean }) {
  if (!item.reviewContext) return null;
  const context = item.reviewContext;
  const page = submission.pages.find(p => p.id === context.pageId);
  if (submission.analysisKind === "essay" && page) {
    return <figure className="homework-original-question" aria-label="正在修改的原作文"><figcaption><span>我的原作文<span className="homework-source-page"> · 第 {page.order + 1} 页</span></span></figcaption><HomeworkPaperImage submissionId={submission.id} page={page} alt="老师正在看的原作文照片" /></figure>;
  }
  const confirmed = sourceAnswerConfirmed(item);
  const answerCaption = neutralAnswer ? confirmed ? "孩子原作答" : "原图识别到的作答" : confirmed ? "原作答" : "识别到的作答";
  const answer = context.answerState === "blank" ? "□（空白）" : context.answerState === "unclear" ? "老师会结合原图来看" : context.answerState === "drawing" ? "画图作答，见原图" : context.originalAnswer || "见原图";
  return <figure className="homework-original-question" aria-label="正在订正的原题"><figcaption><span>{sourceQuestionTitle(item)}<span className="homework-source-page"> · {page ? `第 ${page.order + 1} 页` : "原作业"}</span></span><span><span>{answerCaption}：</span>{!neutralAnswer && homeworkPaperJudgment(item) === "incorrect" && context.answerState !== "blank" && context.answerState !== "drawing" ? <s><HomeworkMathText text={answer} /></s> : <HomeworkMathText text={answer} />}</span></figcaption><HomeworkQuestionPicture submission={submission} item={item} /><OriginalQuestionMedia submission={submission} item={item} /></figure>;
}

export function HomeworkGradingDetails({ item }: { item: HomeworkItem }) {
  const grading = item.reviewContext?.grading;
  if (!homeworkReferenceAvailable(item)) return null;
  if (!grading || (!grading.referenceAnswer && !grading.analysis && !grading.knowledgePoints.length)) return null;
  const verified = grading.studentQuality?.status === "verified";
  return <details className="homework-grading-details"><summary><BookOpen aria-hidden="true" /><span>{verified ? "核对后的答案与讲解" : grading.referenceGate ? "原题参考与解析" : "看原题答案和解析"}</span></summary>
    {!verified && grading.referenceGate?.available && <div><span>这份参考用于同一道题的讲解和订正。</span></div>}
    {!verified && !grading.referenceGate && (grading.source === "tencent" || grading.provider === "tencent") && <div><span>{homeworkStudentCopy.checkReference}</span></div>}
    {grading.referenceAnswer && <div><span>{verified ? "核对后的答案" : grading.referenceGate ? "原题参考答案" : "批改参考答案"}</span><p><HomeworkMathText text={grading.referenceAnswer} /></p></div>}
    {grading.analysis && <div><span>{grading.referenceGate ? "原题解析" : "题目解析"}</span><p><HomeworkMathText text={grading.analysis} /></p></div>}
    {!!grading.knowledgePoints.length && <div><span>练习的知识</span><p><HomeworkMathText text={grading.knowledgePoints.join(" · ")} /></p></div>}
  </details>;
}

export function HomeworkCollection({ records, compact = false }: { records: HomeworkSubmission[]; compact?: boolean }) {
  const groups = compact ? [{ title: "", records }] : [
    { title: "和老师再试试", records: records.filter(item => homeworkAvailability(item) === "ready") },
    { title: "还在准备", records: records.filter(item => homeworkAvailability(item) !== "ready" && !completedStates.includes(homeworkAvailability(item))) },
    { title: "已经看过的作业", records: records.filter(item => completedStates.includes(homeworkAvailability(item))) },
  ];
  return <div className={`homework-library${compact ? " is-compact" : ""}`}>
    {!compact && <div className="homework-library-intro"><p>找到自己的作业，和老师一起再试试。</p><LearningListenButton cue="choose" label="听入口说明" /></div>}
    {groups.filter(group => group.records.length).map(group => <section className="homework-library-group" key={group.title || "compact"}>
      {group.title && <h2>{group.title}<span>{group.records.length} 份</span></h2>}
      <div className="homework-documents">{group.records.map(item => {
        const state = homeworkAvailability(item), page = item.pages[0];
        const remaining = item.items.filter(question => practiceReady(item, question)).length;
        const tutorCount = homeworkTutorQuestions(item).filter(question => question.tutorAvailable).length;
        const subject = subjectNames[item.subject] ?? "学习";
        return <Link key={item.id} className="homework-document" href={`/learning/homework/${item.id}`} aria-label={`${item.title}，${homeworkAvailabilityLabels[state]}`}>
          <span className="homework-document-cover">{page ? <HomeworkPaperImage submissionId={item.id} page={page} alt={`${item.title}的原作业照片`} allowRetry={false} /> : <SubjectPicture subject={item.subject === "chinese" ? "chinese" : item.subject === "english" ? "english" : "math"} />}<span className={`homework-document-state is-${state}`} aria-hidden="true">{state === "ready" ? <Play fill="currentColor" /> : state === "processing" ? <Clock3 /> : state === "self_reported" ? <PencilLine /> : completedStates.includes(state) ? <Check /> : <Hand />}</span></span>
          <span className="homework-document-details"><small>{subject} · {new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", timeZone: "Asia/Shanghai" }).format(item.createdAt)}</small><strong>{item.title}</strong><span>{state === "ready" ? remaining ? `${remaining} 道题，和老师再试试` : `${tutorCount} 道原题，可以问老师` : homeworkAvailabilityLabels[state]}</span><span className="homework-document-link">{state === "ready" ? remaining ? "看看哪里需要订正" : "请老师讲原题" : completedStates.includes(state) ? "查看作业" : "看看准备情况"}<ArrowRight /></span></span>
        </Link>;
      })}</div>
    </section>)}
  </div>;
}

export function HomeworkPaperOverview({ submission, onStart, onRefresh, onTutor, onData }: { submission: HomeworkSubmission; onStart: (id: string) => void; onRefresh: () => void; onTutor?: (id: string) => void; onData?: (value: HomeworkDetail) => void }) {
  return submission.analysisKind === "essay"
    ? <HomeworkEssayOverview submission={submission} onRefresh={onRefresh} onTutor={onTutor} />
    : <HomeworkQuestionOverview submission={submission} onStart={onStart} onRefresh={onRefresh} onTutor={onTutor} onData={onData} />;
}

function HomeworkQuestionOverview({ submission, onStart, onRefresh, onTutor, onData }: { submission: HomeworkSubmission; onStart: (id: string) => void; onRefresh: () => void; onTutor?: (id: string) => void; onData?: (value: HomeworkDetail) => void }) {
  const questions = homeworkTutorQuestions(submission).sort((a, b) => questionPriority(a) - questionPriority(b));
  const first = questions.find(item => item.tutorAvailable || practiceReady(submission, item)) ?? questions[0];
  const [selectedId, setSelectedId] = useState<string | undefined>(first?.id);
  const [pageId, setPageId] = useState(first?.reviewContext?.pageId ?? submission.pages[0]?.id);
  const page = submission.pages.find(page => page.id === pageId) ?? submission.pages[0];
  const selected = questions.find(item => item.id === selectedId && (!item.reviewContext || item.reviewContext.pageId === page?.id));
  const [loadedPageId, setLoadedPageId] = useState<string | null>(null);
  const [questionFilter, setQuestionFilter] = useState<"incorrect" | "all">("incorrect"), [questionPage, setQuestionPage] = useState(0);
  const [overlapIds, setOverlapIds] = useState<string[]>([]);
  const state = homeworkAvailability(submission);
  const remaining = submission.items.filter(item => practiceReady(submission, item)).length;
  const wrong = questions.filter(item => homeworkPaperDisplayJudgment(item) === "incorrect" && !correctionWorkflowDone(item));
  const unsupported = (submission.originalSummary?.unsupported ?? 0) + (submission.studentSummary?.unsupportedCorrection ?? 0);
  const tutorCount = questions.filter(item => item.tutorAvailable).length;
  // Only the current server-gated original-paper summary supplies totals.
  // Provisional marks help locate a question; they cannot replace that summary.
  const hasPendingVerification = questions.some(homeworkGradingNeedsReview);
  const hasProvisionalResults = questions.some(item => !!homeworkProvisionalVerdict(item));
  const studentCorrect = submission.originalPaperSummary?.correct ?? 0;
  const studentIncorrect = submission.originalPaperSummary?.incorrect ?? 0;
  const studentUnknown = submission.originalPaperSummary?.unknown ?? Math.max(questions.length, submission.originalSummary?.total ?? 0);
  const studentBlank = Math.min(studentUnknown, submission.originalPaperSummary?.blank ?? questions.filter(item => item.reviewContext?.answerState === "blank" || item.reviewContext?.grading?.answerState === "blank").length);
  const teacher = teacherForSubject(null, submission.subject);
  function selectPage(p: HomeworkPage) {
    const next = questions.find(item => item.reviewContext?.pageId === p.id);
    setPageId(p.id); setSelectedId(next?.id); setQuestionPage(0); setOverlapIds([]);
  }
  function select(item: HomeworkItem) { setSelectedId(item.id); setOverlapIds([]); if (item.reviewContext?.pageId) setPageId(item.reviewContext.pageId); }
  function teach(item: HomeworkItem) {
    select(item);
    if (item.tutorAvailable && onTutor) onTutor(item.id);
    else if (practiceReady(submission, item)) onStart(item.id);
  }
  const pageQuestions = questions.filter(item => item.reviewContext?.pageId === page?.id);
  const pageWrong = pageQuestions.filter(item => homeworkPaperDisplayJudgment(item) === "incorrect" && !correctionWorkflowDone(item));
  const pageHasProvisionalResults = pageQuestions.some(item => !!homeworkProvisionalVerdict(item));
  const filteredQuestions = questionFilter === "incorrect" && pageWrong.length ? pageWrong : pageQuestions;
  const lastQuestionPage = Math.max(0, Math.ceil(filteredQuestions.length / 6) - 1), currentQuestionPage = Math.min(questionPage, lastQuestionPage);
  const visibleQuestions = filteredQuestions.slice(currentQuestionPage * 6, currentQuestionPage * 6 + 6);
  return <div className="homework-paper-overview">
    <div className="homework-overview-heading"><div><p>{submission.title}</p><h2>{remaining || wrong.length ? "先看看，哪里需要再试试" : tutorCount ? "点原题，听老师讲" : homeworkAvailabilityLabels[state]}</h2></div><LearningListenButton cue="start" label="听听怎么开始" /></div>
    <div className="homework-paper-results" aria-label="原作业批改结果">
      {hasProvisionalResults && <span className="is-unknown"><BookOpen aria-hidden="true" />{homeworkStudentCopy.checkHeader}</span>}
      <span className="is-correct"><Check aria-hidden="true" />答对 {studentCorrect}</span>
      <span className="is-incorrect"><X aria-hidden="true" />再看看 {studentIncorrect}</span>
      {studentBlank > 0 && <span className="is-unknown"><BookOpen aria-hidden="true" />未作答 {studentBlank}</span>}
      <span className="is-unknown"><HelpCircle aria-hidden="true" />{hasPendingVerification || hasProvisionalResults ? "待核实" : "看原图"} {Math.max(0, studentUnknown - studentBlank)}</span>
      {!!submission.summary.selfReportedCompleted && <span className="is-unknown"><PencilLine aria-hidden="true" />纸上改好 {submission.summary.selfReportedCompleted}</span>}
    </div>
    <div className="homework-overview-layout">
      <section className="homework-paper-panel" aria-label="原作业错题位置">
        <div className="homework-paper-caption"><h3>我的原作业</h3><span>{page ? `第 ${page.order + 1} 页` : "等待照片"}</span></div>
        {page ? <div className="homework-paper-stage" style={{ aspectRatio: `${page.width} / ${page.height}` }}>
          <HomeworkPaperImage submissionId={submission.id} page={page} alt="上传的原作业照片" onImageState={loaded => setLoadedPageId(loaded ? page.id : null)} />
          {markerGroups(loadedPageId === page.id && homeworkImagePath(page.assetUrl, submission.id, page.id) ? pageQuestions : []).map(group => {
            const item = group.items[0], context = item.reviewContext!, region = group.region;
            const number = (context.answerCount ?? 0) > 1 ? `${context.sourceQuestionLabel?.trim() || context.originalOrdinal}·${context.answerIndex}` : context.sourceQuestionLabel?.trim() || context.originalOrdinal;
            const multiple = group.items.length > 1;
            return <button type="button" key={item.id} className="homework-paper-marker" data-status={multiple ? "unknown" : homeworkPaperDisplayJudgment(item)} data-provisional={!multiple && !!homeworkProvisionalVerdict(item)} data-group={multiple} data-selected={group.items.some(item => selected?.id === item.id)} aria-label={multiple ? `看看这一区域的 ${group.items.length} 个原作答` : `听老师讲${sourceQuestionTitle(item)}，${judgmentLabel(item)}`} onClick={() => { if (multiple) { setSelectedId(undefined); setOverlapIds(group.items.map(item => item.id)); } else teach(item); }} style={{ left: `${region.x * 100}%`, top: `${region.y * 100}%`, width: `${region.width * 100}%`, height: `${region.height * 100}%` }}><span className="homework-paper-question-number">{multiple ? group.items.length : number}</span><span className="homework-paper-judgment">{multiple ? <BookOpen aria-hidden="true" /> : <JudgmentPicture item={item} />}</span></button>;
          })}
        </div> : <div className="homework-paper-no-photo"><SubjectPicture subject="math" /><p>这份作业还没有可显示的原照片</p></div>}
        {submission.pages.length > 1 && <nav className="homework-paper-pages" aria-label="原作业页码">{submission.pages.map(p => <Button key={p.id} size="compact" variant={page?.id === p.id ? "primary" : "secondary"} aria-pressed={page?.id === p.id} onClick={() => selectPage(p)}>第 {p.order + 1} 页</Button>)}</nav>}
        <p className="homework-paper-note">{pageHasProvisionalResults ? homeworkStudentCopy.checkNotice : pageQuestions.some(item => !!markerRegion(item)) ? "点照片上的题号，老师陪你看这道原题。" : "原图保存在这里，点老师就能看图讲解。"}</p>
      </section>
      <section className="homework-selected-panel" aria-label="选中的错题">
        <div className="homework-overview-teacher"><Image src={teacher.avatarPath} width={56} height={56} alt={homeworkStudentCopy.teacherCorrectionAlt} /><div><h3>{wrong.length || remaining ? `还有 ${wrong.length || remaining} 道题，我们一起看` : tutorCount ? "这份原作业，可以问老师" : "你的作业记录已保存"}</h3><p>{submission.summary.corrected ? `已经订正 ${submission.summary.corrected} 道` : "看原图，听老师讲，自己再试一试"}</p></div></div>
        {overlapIds.length > 1 && <div className="homework-overlap-choices"><p>这一区域有几个原作答，点图片选一个请老师看</p><div className="homework-question-pictures" role="group" aria-label="这一区域的原作答">{questions.filter(item => overlapIds.includes(item.id)).map(item => <button className="homework-question-picture" key={item.id} type="button" aria-label={`请老师看${sourceQuestionTitle(item)}`} onClick={() => teach(item)}><HomeworkQuestionPicture submission={submission} item={item} allowRetry={false} /><span><JudgmentPicture item={item} />{sourceQuestionTitle(item)} · <HomeworkMathText text={item.reviewContext?.originalAnswer || "见原图"} /></span></button>)}</div></div>}
        {selected && <>{!!selected.reviewContext?.sourcePath?.length && <p className="homework-question-path"><HomeworkMathText text={selected.reviewContext.sourcePath.join(" › ")} /></p>}<div className="homework-selected-judgment" data-status={homeworkPaperDisplayJudgment(selected)} data-provisional={!!homeworkProvisionalVerdict(selected)}><JudgmentPicture item={selected} /><span>{judgmentLabel(selected)}</span>{correctionCompleted(selected) && <span className="homework-corrected-label">已订正</span>}{homeworkCorrectionSelfReported(selected.studentCorrection) && <span className="homework-self-reported-label"><PencilLine aria-hidden="true" />纸上已改好，未复测</span>}</div><HomeworkOriginalQuestion submission={submission} item={selected} />{!selected.reviewContext && <HomeworkQuestionPicture submission={submission} item={selected} />}
          {selected.tutorAvailable && onTutor ? <div className="homework-tutor-overview-entry"><p>{!homeworkReferenceAvailable(selected) ? "这道题暂时不能确认，可以先看原图或换一道题" : homeworkPaperJudgment(selected) === "unknown" ? "老师会直接看这张原图，再陪你讲解和解答" : homeworkPaperJudgment(selected) === "incorrect" ? "听原题讲解，还可以自己接着问" : "这道原题也可以请老师看，不会直接记成错题"}</p><Button onClick={() => teach(selected)}>{homeworkReferenceAvailable(selected) ? <Volume2 /> : <Pointer />}{!homeworkReferenceAvailable(selected) ? "看原图，圈一圈" : homeworkPaperJudgment(selected) === "incorrect" ? "老师带我订正原题" : homeworkStudentCopy.originalQuestionAction}</Button>{practiceReady(submission, selected) && <Button size="compact" variant="secondary" onClick={() => onStart(selected.id)}><Play fill="currentColor" />我自己再做一次</Button>}</div>
            : practiceReady(submission, selected) ? <Button onClick={() => onStart(selected.id)}><Play fill="currentColor" />和老师一起订正</Button> : <p className="homework-selected-status">{correctionCompleted(selected) ? "这道题已经订正好了" : "老师的原题讲解还在准备，可以先看原图"}</p>}
          <HomeworkGradingDetails item={selected} />
          <HomeworkPaperCompletion key={`${selected.id}:${selected.revision}`} submission={submission} item={selected} onData={onData} />
        </>}
        {!selected && page && !overlapIds.length && <p className="homework-selected-status">这一页还没有可打开的原题，老师正在整理</p>}
        {!remaining && !tutorCount && !completedStates.includes(state) && <Button size="compact" variant="secondary" onClick={onRefresh}><RefreshCw />再看看准备情况</Button>}
        {pageQuestions.length > 1 && <div className="homework-other-questions"><p>点原题图片，换一道</p><div className="homework-question-filters" role="group" aria-label="这页原题的显示范围"><Button size="compact" variant={questionFilter === "incorrect" && pageWrong.length ? "secondary" : "quiet"} disabled={!pageWrong.length} aria-pressed={questionFilter === "incorrect" && !!pageWrong.length} onClick={() => { setQuestionFilter("incorrect"); setQuestionPage(0); }}><X />{pageHasProvisionalResults ? homeworkStudentCopy.checkFilter : "先看错题"} {pageWrong.length}</Button><Button size="compact" variant={questionFilter === "all" || !pageWrong.length ? "secondary" : "quiet"} aria-pressed={questionFilter === "all" || !pageWrong.length} onClick={() => { setQuestionFilter("all"); setQuestionPage(0); }}><BookOpen />全部原题 {pageQuestions.length}</Button></div><div className="homework-question-pictures" role="group" aria-label="选择原作业题目">{visibleQuestions.map((item, index) => <button type="button" className="homework-question-picture" key={item.id} data-status={homeworkPaperDisplayJudgment(item)} data-provisional={!!homeworkProvisionalVerdict(item)} aria-label={`看看${sourceQuestionTitle(item, index + 1)}`} aria-pressed={selected?.id === item.id} onClick={() => select(item)}><HomeworkQuestionPicture submission={submission} item={item} allowRetry={false} /><span><JudgmentPicture item={item} />{sourceQuestionTitle(item, index + 1)}{correctionCompleted(item) ? " · 已订正" : homeworkCorrectionSelfReported(item.studentCorrection) ? " · 纸上已改好，未复测" : homeworkProvisionalVerdict(item) ? ` · ${homeworkPaperDisplayJudgment(item) === "incorrect" ? homeworkStudentCopy.checkIncorrect : homeworkStudentCopy.checkCorrect}` : homeworkPaperJudgment(item) === "incorrect" ? " · 再试试" : " · 听老师讲"}</span></button>)}</div>{lastQuestionPage > 0 && <nav className="homework-question-pagination" aria-label="原题图片翻页"><Button size="compact" variant="quiet" disabled={currentQuestionPage === 0} onClick={() => setQuestionPage(currentQuestionPage - 1)}><ArrowLeft />上一组</Button><span>{currentQuestionPage + 1} / {lastQuestionPage + 1}</span><Button size="compact" variant="secondary" disabled={currentQuestionPage === lastQuestionPage} onClick={() => setQuestionPage(currentQuestionPage + 1)}>下一组<ArrowRight /></Button></nav>}</div>}
        {unsupported > 0 && <p className="homework-scope-note">{tutorCount > 0 ? "能确认的原题可以听老师讲解和追问；待核实的题先看原图，听过讲解不算独立订正。" : `另外 ${unsupported} 道题的原题讲解尚未准备好，尚未计作订正。`}</p>}
      </section>
    </div>
  </div>;
}

function HomeworkEssayOverview({ submission, onRefresh, onTutor }: { submission: HomeworkSubmission; onRefresh: () => void; onTutor?: (id: string) => void }) {
  const [pageId, setPageId] = useState(submission.pages[0]?.id);
  const page = submission.pages.find(p => p.id === pageId) ?? submission.pages[0];
  const teacher = teacherForSubject(null, submission.subject);
  const item = submission.tutorItems.find(item => item.pageId === page?.id && item.tutorAvailable);
  return <div className="homework-paper-overview">
    <div className="homework-overview-heading"><div><p>{submission.title}</p><h2>和老师看看我的作文</h2></div><LearningListenButton cue="start" label="听听怎么开始" /></div>
    <div className="homework-overview-layout">
      <section className="homework-paper-panel" aria-label="我的原作文">
        <div className="homework-paper-caption"><h3>我的原作文</h3><span>{page ? `第 ${page.order + 1} 页` : "等待照片"}</span></div>
        {page ? <HomeworkPaperImage submissionId={submission.id} page={page} alt="上传的原作文照片" /> : <SubjectPicture subject={submission.subject === "english" ? "english" : "chinese"} />}
        {submission.pages.length > 1 && <nav className="homework-paper-pages" aria-label="选择作文图片">{submission.pages.map(p => <button className="homework-question-picture" type="button" key={p.id} aria-label={`看看作文第 ${p.order + 1} 页`} aria-pressed={page?.id === p.id} onClick={() => setPageId(p.id)}><HomeworkPaperImage submissionId={submission.id} page={p} alt={`作文第 ${p.order + 1} 页`} allowRetry={false} /></button>)}</nav>}
      </section>
      <section className="homework-selected-panel" aria-label="老师陪我修改作文">
        <div className="homework-overview-teacher"><Image src={teacher.avatarPath} width={56} height={56} alt={homeworkStudentCopy.teacherEssayAlt} /><div><h3>老师陪你看这一页</h3><p>看原图，听老师说，再问一问</p></div></div>
        {item && onTutor ? <Button onClick={() => onTutor(item.id)}><Volume2 />请老师看我的作文</Button> : <><p role="status">{submission.processing ? "老师正在看你的作文…" : "这一页的作文建议还没准备好"}</p><Button size="compact" variant="secondary" onClick={onRefresh}><RefreshCw />再看看</Button></>}
        <p className="homework-scope-note">和老师一起修改作文，不作为考试分数。</p>
      </section>
    </div>
  </div>;
}
