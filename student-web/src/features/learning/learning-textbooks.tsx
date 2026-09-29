"use client";

import { ArrowLeft, ArrowRight, BookOpen, Check, Compass, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { z } from "zod";

import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { useSchoolbagMotion, useSchoolbagBook } from "@/components/schoolbag/schoolbag-motion";
import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/ui/disclosure";
import { SelectField } from "@/components/ui/select";
import { LearningClientError } from "@/features/learning/learning-client";
import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";
import { LearningTextbookIntroduction } from "@/features/learning/learning-textbook-introduction";
import { TextbookPicture } from "@/features/learning/textbook-picture";
import { textbookIntroductionPath, type TextbookLocation } from "@/features/learning/textbook-navigation";
import { useTextbookCatalog } from "@/features/learning/use-textbook-catalog";
import { textbookContentsSchema, type TextbookContents } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

type State<T> = { key: string; data?: T; error?: string };
const bookKey = (book: { editionId: string; revisionId: string }) => `${book.editionId}:${book.revisionId}`;
const subjectNames = { chinese: "语文", math: "数学", english: "英语", science: "科学" };

async function load<T>(path: string, schema: z.ZodType<T>, signal: AbortSignal) {
  const response = await fetch(path, { cache: "no-store", signal });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = payload as { error?: string; message?: string };
    throw new LearningClientError(response.status, detail.error || "textbook_unavailable", detail.message || "教材暂时没有加载成功");
  }
  return schema.parse(payload);
}

export function LearningTextbooks({ student, location }: { student: Student; location?: TextbookLocation }) {
  const router = useRouter();
  const { returnHome, busy } = useSchoolbagMotion();
  function goHome(event: React.MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); if (!busy) returnHome();
  }
  const { key: catalogKey, data, error, refresh } = useTextbookCatalog(student);
  const [contents, setContents] = useState<State<TextbookContents>>({ key: "" });
  const [chosenUnit, setChosenUnit] = useState<{ book: string; unit: string }>();
  const books = data?.books.filter(item => item.selected) ?? [];
  const requestedKey = location?.editionId && location?.revisionId ? `${location.editionId}:${location.revisionId}` : "";
  const book = requestedKey ? books.find(item => bookKey(item) === requestedKey) : books[0];
  // Direct links also pass the server's parent-selection check. Never silently
  // replace an outdated URL with a different book or a different revision.
  const edition = location?.editionId ?? book?.editionId;
  const revision = location?.revisionId ?? book?.revisionId;
  const contentsKey = `${catalogKey}:${edition}:${revision}`;
  const detail = contents.key === contentsKey ? contents.data : undefined;
  const detailError = contents.key === contentsKey ? contents.error : undefined;
  useSchoolbagBook(detail?.book.subject);
  const activeUnit = detail?.units.find(unit => unit.unitId === (chosenUnit?.book === `${edition}:${revision}` ? chosenUnit.unit : location?.unitId))
    ?? detail?.units.find(unit => unit.lessons.some(lesson => lesson.nodeId === detail.currentNodeId)) ?? detail?.units[0];

  useEffect(() => {
    if (!data || !edition || !revision) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ alignmentRevisionId: revision });
    void load(`/api/learning/textbooks/${encodeURIComponent(edition)}/contents?${query}`, textbookContentsSchema, controller.signal).then(result => {
      if (!result.selected || result.book.editionId !== edition || result.book.revisionId !== revision || result.book.gradeCode !== student.gradeCode) throw new Error("教材资料已更新，请刷新目录");
      if (!controller.signal.aborted) setContents({ key: contentsKey, data: result });
    }).catch((caught: unknown) => {
      if (controller.signal.aborted) return;
      if (caught instanceof LearningClientError && caught.status === 401) { router.replace("/unlock"); return; }
      setContents({ key: contentsKey, error: caught instanceof Error ? caught.message : "目录暂时没有加载成功" });
    });
    return () => controller.abort();
  }, [contentsKey, data, edition, revision, router, student.gradeCode]);

  const introUnit = detail?.units.find(unit => unit.introduction?.introductionId === location?.introductionId);
  const introduction = location?.introductionId ? (detail?.introduction?.introductionId === location.introductionId ? detail.introduction : introUnit?.introduction) : null;
  if (detail && introduction) return <LearningTextbookIntroduction key={`${contentsKey}:${introduction.contentSha256}`} student={student} contents={detail} introduction={introduction} unitId={introUnit?.unitId} />;

  return <SchoolbagShell student={student} className="space-textbooks storybook-directory"
    navigation={<Link href="/learning" onClick={goHome}><ArrowLeft size={21} aria-hidden="true" /><span>回到书包</span></Link>}>
    {(!detail || error || detailError) && <header className="textbook-empty-heading"><h1>{book ? `我的${subjectNames[book.subject]}课本` : "我的课本"}</h1><Button variant="quiet" onClick={refresh}><RefreshCw size={18} aria-hidden="true" />刷新教材</Button></header>}
    {error ? <div className="textbook-state" role="alert"><p>{error}</p><Button onClick={refresh}>再试一次</Button></div>
      : !data ? <TextbookLoading label="正在打开教材目录" />
      : !books.length && !edition ? <div className="textbook-state"><BookOpen size={32} aria-hidden="true" /><h2>请家长帮你放入课本</h2><p>在家长 App 的“学校教材”中确认用书，再回到书包刷新。</p><Button asChild><Link href="/learning">回到书包</Link></Button></div>
      : <>
        {detailError ? <div className="textbook-state" role="alert"><p>{detailError}</p><Button onClick={refresh}>重试目录</Button><Button asChild variant="quiet"><Link href="/learning">回到书包</Link></Button></div>
          : !detail ? <TextbookLoading label="正在读取单元" />
          : location?.introductionId ? <div className="textbook-state" role="alert"><h2>这份导学还没有准备好</h2><Button asChild><Link href="/learning/textbooks">回到教材目录</Link></Button></div>
          : <>
            <section className="textbook-welcome" aria-label="走进这门学科">
              <div><p className="textbook-bookline">我的学校课本</p>
                <h1>{detail.book.title.split(/\s+/).map((part, index) => <span key={`${index}-${part}`}>{index > 0 ? " " : ""}{part}</span>)}</h1>
                {detail.introduction ? <Link className="textbook-discover-link" href={textbookIntroductionPath(detail.book, detail.introduction.introductionId)}><Compass size={20} aria-hidden="true" />先认识{subjectNames[detail.book.subject]}<ArrowRight size={20} aria-hidden="true" /></Link> : null}
              </div>{detail.introduction?.presentation ? <div className="textbook-welcome-art"><TextbookPicture art={detail.introduction.presentation.scenes[0].art} thumbnail /></div> : null}
            </section>
            {detail.book.coverage.status === "partial" ? <p className="textbook-notice">目前展示 {detail.book.unitCount} 个单元，其余目录正在补齐。</p> : null}
            {detail.book.coverage.status === "index_only" ? <p className="textbook-notice">教材版本已确认，目录待补齐。</p> : null}
            {activeUnit ? <div className="textbook-layout">
              <aside className="textbook-unit-sidebar"><h3>目录</h3><p>{detail.book.unitCount} 个板块 · {detail.book.lessonCount} 个课次</p>
                <div className="textbook-mobile-choice"><span>选择单元</span><SelectField label="选择单元" value={activeUnit.unitId} onValueChange={unit => setChosenUnit({ book: `${edition}:${revision}`, unit })} options={detail.units.map(unit => ({ value: unit.unitId, label: unit.title }))} /></div>
                <nav className="textbook-unit-nav" aria-label="教材单元">{detail.units.map(unit => <button key={unit.unitId} type="button" aria-current={activeUnit.unitId === unit.unitId ? "true" : undefined} onClick={() => setChosenUnit({ book: `${edition}:${revision}`, unit: unit.unitId })}>
                  <span>{unit.title}</span><small>{unit.lessons.length}</small>
                </button>)}</nav>
              </aside>
              <section className="textbook-unit-content" key={activeUnit.unitId} aria-label={activeUnit.title}>
                <header className="textbook-unit-heading"><h3>{activeUnit.title}</h3></header>
                {activeUnit.introduction ? <div className="textbook-unit-introduction">
                  {activeUnit.introduction.presentation && <div className="textbook-unit-art"><TextbookPicture art={activeUnit.introduction.presentation.scenes[0].art} thumbnail /></div>}
                  <div className="textbook-unit-invitation"><p>单元导学 · 约 {activeUnit.introduction.estimatedMinutes} 分钟</p><h4>{activeUnit.introduction.title}</h4><Button asChild><Link href={textbookIntroductionPath(detail.book, activeUnit.introduction.introductionId)}>开始探索<ArrowRight size={20} aria-hidden="true" /></Link></Button></div>
                </div> : null}
                <h4 className="textbook-lessons-heading">课本里的课程</h4>
                <ol className="textbook-lessons">{activeUnit.lessons.map(lesson => <li key={lesson.nodeId} className="textbook-lesson" aria-current={detail.currentNodeId === lesson.nodeId ? "step" : undefined}>
                  <div>{lesson.sectionTitle ? <p>{lesson.sectionTitle}</p> : null}<h4>{lesson.title}</h4><p>{lesson.printedPage ? `课本第 ${lesson.printedPage} 页` : "对应课本课程"}{detail.currentNodeId === lesson.nodeId ? " · 学校当前进度" : ""}</p></div>
                  {lesson.status === "ready" && lesson.course && detail.selected ? lesson.course.delivery === "fixed_textbook"
                    ? <Button asChild><Link prefetch={false} href={`/learning/textbooks/courses/${lesson.course.contentKey}`}>开始上课<ArrowRight size={20} aria-hidden="true" /></Link></Button>
                    : <LearningCourseStartButton courseId={lesson.course.courseId} version={lesson.course.courseVersion} />
                    : <span className="textbook-lesson-status">{lesson.status === "locked" ? lesson.message || "请先完成前面的课程" : "课件待生成"}</span>}
                </li>)}</ol>
              </section>
            </div> : null}
            <Disclosure className="textbook-book-info" title="教材信息与学习说明">
              <p>{detail.book.publisher} · {detail.selected ? <span className="textbook-confirmed"><Check size={16} aria-hidden="true" />家长已确认</span> : "教材同步"}</p>
              <p>{detail.book.editionLabel}</p><p>{detail.book.coverage.note}</p><p>目录按教材编排，课件完成后开放。导学是原创的课前探索，学习进度单独记录。</p>
              <div className="textbook-info-actions"><a className="focus-ring textbook-source" href={detail.book.sourceUrl} target="_blank" rel="noopener noreferrer">查看官方教材信息<span className="sr-only">（在新窗口打开）</span></a><Button variant="quiet" onClick={refresh}><RefreshCw size={16} aria-hidden="true" />刷新教材</Button></div>
            </Disclosure>
          </>}
      </>}
  </SchoolbagShell>;
}

function TextbookLoading({ label }: { label: string }) {
  return <div className="textbook-loading" role="status"><span>{label}…</span><div aria-hidden="true" /><div aria-hidden="true" /><div aria-hidden="true" /></div>;
}
