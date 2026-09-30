"use client";

import { ArrowLeft, ArrowRight, Backpack, BookOpen, Check, ChevronLeft, ChevronRight, Compass, LayoutGrid, List, Play, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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
import { LearningListenButton, LessonPicture } from "./learning-picture-navigation";

type State<T> = { key: string; data?: T; error?: string };
const bookKey = (book: { editionId: string; revisionId: string }) => `${book.editionId}:${book.revisionId}`;
const subjectNames = { chinese: "语文", math: "数学", english: "英语", science: "科学" };
type TextbookUnit = TextbookContents["units"][number];
const PICTURE_PAGE_SIZE = 6;
const isPictureLesson = (lesson: TextbookUnit["lessons"][number]) => lesson.status === "ready" && lesson.course?.delivery === "fixed_textbook";

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
  const [view, setView] = useState<"pictures" | "directory">("pictures");
  const [choosingUnit, setChoosingUnit] = useState(false);
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
  const pictureFirst = ["primary_1", "primary_2"].includes(student.gradeCode ?? "");
  useSchoolbagBook(detail?.book.subject);
  const activeUnit = detail?.units.find(unit => unit.unitId === (chosenUnit?.book === `${edition}:${revision}` ? chosenUnit.unit : location?.unitId))
    ?? detail?.units.find(unit => unit.lessons.some(lesson => lesson.nodeId === detail.currentNodeId))
    ?? (pictureFirst ? detail?.units.find(unit => unit.lessons.some(isPictureLesson)) : undefined)
    ?? detail?.units[0];
  const showPictures = pictureFirst && view === "pictures";
  function chooseUnit(unit: string) {
    setChosenUnit({ book: `${edition}:${revision}`, unit });
    setChoosingUnit(false);
  }

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

  return <SchoolbagShell student={student} className="space-textbooks storybook-directory textbook-browser"
    navigation={<Link href="/learning" onClick={goHome}><Backpack size={32} aria-hidden="true" /><span>回到书包</span></Link>}>
    {(!detail || error || detailError) && <header className="textbook-empty-heading"><h1>{book ? `我的${subjectNames[book.subject]}课本` : "我的课本"}</h1><Button variant="quiet" size="compact" onClick={refresh}><RefreshCw aria-hidden="true" />刷新教材</Button></header>}
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
            {pictureFirst && <div className="textbook-view-switch" role="group" aria-label="课程显示方式">
              <button type="button" aria-pressed={view === "pictures"} onClick={() => { setView("pictures"); setChoosingUnit(false); }}><LayoutGrid size={21} aria-hidden="true" />图片学习</button>
              <button type="button" aria-pressed={view === "directory"} onClick={() => { setView("directory"); setChoosingUnit(false); }}><List size={21} aria-hidden="true" />完整目录</button>
            </div>}
            {showPictures && activeUnit ? choosingUnit
              ? <PictureUnitPicker key={`${contentsKey}:${activeUnit.unitId}`} units={detail.units} activeUnit={activeUnit} onChoose={chooseUnit} onCancel={() => setChoosingUnit(false)} />
              : <PictureLessons key={`${contentsKey}:${activeUnit.unitId}`} detail={detail} unit={activeUnit} onChooseUnits={() => setChoosingUnit(true)} />
              : <>
            <section className="textbook-full-directory" aria-label="完整目录">
            {detail.book.coverage.status === "partial" ? <p className="textbook-notice">目前展示 {detail.book.unitCount} 个单元，其余目录正在补齐。</p> : null}
            {detail.book.coverage.status === "index_only" ? <p className="textbook-notice">教材版本已确认，目录待补齐。</p> : null}
            {activeUnit ? <div className="textbook-layout">
              <aside className="textbook-unit-sidebar"><h3>目录</h3><p>{detail.book.unitCount} 个板块 · {detail.book.lessonCount} 个课次</p>
                <div className="textbook-mobile-choice"><span>选择单元</span><SelectField label="选择单元" value={activeUnit.unitId} onValueChange={chooseUnit} options={detail.units.map(unit => ({ value: unit.unitId, label: unit.title }))} /></div>
                <nav className="textbook-unit-nav" aria-label="教材单元">{detail.units.map(unit => <button key={unit.unitId} type="button" aria-current={activeUnit.unitId === unit.unitId ? "true" : undefined} onClick={() => chooseUnit(unit.unitId)}>
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
            </section>
            <Disclosure className="textbook-book-info" title="教材信息与学习说明">
              <p>{detail.book.publisher} · {detail.selected ? <span className="textbook-confirmed"><Check size={16} aria-hidden="true" />家长已确认</span> : "教材同步"}</p>
              <p>{detail.book.editionLabel}</p><p>{detail.book.coverage.note}</p><p>目录按教材编排，课件完成后开放。导学是原创的课前探索，学习进度单独记录。</p>
              <div className="textbook-info-actions"><a className="focus-ring textbook-source" href={detail.book.sourceUrl} target="_blank" rel="noopener noreferrer">查看官方教材信息<span className="sr-only">（在新窗口打开）</span></a><Button variant="quiet" size="compact" onClick={refresh}><RefreshCw aria-hidden="true" />刷新教材</Button></div>
            </Disclosure>
            </>}
          </>}
      </>}
  </SchoolbagShell>;
}

function PictureUnitPicker({ units, activeUnit, onChoose, onCancel }: { units: TextbookUnit[]; activeUnit: TextbookUnit; onChoose(unit: string): void; onCancel(): void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);
  const pageSize = 9;
  const [page, setPage] = useState(() => Math.floor(Math.max(0, units.findIndex(unit => unit.unitId === activeUnit.unitId)) / pageSize));
  const pages = Math.ceil(units.length / pageSize);
  return <section className="picture-unit-picker" aria-label="图片单元">
    <header><div><h2 ref={heading} tabIndex={-1}>想去哪个单元？</h2><p>点一张图片，看看里面的课程。</p></div><Button variant="secondary" size="compact" type="button" onClick={onCancel}><ArrowLeft aria-hidden="true" />回到课程</Button></header>
    <div className="picture-unit-grid">
      {units.slice(page * pageSize, (page + 1) * pageSize).map(unit => <button key={unit.unitId} type="button" className="picture-unit-choice" aria-label={unit.title} aria-pressed={unit.unitId === activeUnit.unitId} onClick={() => onChoose(unit.unitId)}>
        <span className="picture-unit-art">{unit.introduction?.presentation ? <TextbookPicture art={unit.introduction.presentation.scenes[0].art} thumbnail /> : <BookOpen size={48} aria-hidden="true" />}
          {unit.unitId === activeUnit.unitId && <span className="picture-unit-selected"><Check size={20} aria-hidden="true" /><span>正在这里</span></span>}
        </span>
        <span className="picture-unit-label"><strong>{unit.title}</strong><ArrowRight size={20} aria-hidden="true" /></span>
      </button>)}
    </div>
    {pages > 1 && <DirectoryPagination page={page} pages={pages} count={units.length} label="单元翻页" onChange={setPage} />}
  </section>;
}

function PictureLessons({ detail, unit, onChooseUnits }: { detail: TextbookContents; unit: TextbookUnit; onChooseUnits(): void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);
  const lessons = unit.lessons.filter(isPictureLesson);
  const guide = unit.introduction?.presentation ? unit.introduction : undefined;
  const guideCount = guide ? 1 : 0;
  const [chosenPage, setPage] = useState(() => Math.floor(Math.max(0, lessons.findIndex(lesson => lesson.nodeId === detail.currentNodeId) + guideCount) / PICTURE_PAGE_SIZE));
  const count = lessons.length + guideCount;
  const pages = Math.max(1, Math.ceil(count / PICTURE_PAGE_SIZE));
  const page = Math.min(chosenPage, pages - 1);
  const first = page * PICTURE_PAGE_SIZE;
  const last = first + PICTURE_PAGE_SIZE;
  return <section className="picture-lesson-directory" aria-label="图片选课">
    <header><div><h2 ref={heading} tabIndex={-1}>{unit.title}</h2><p>点图片，开始玩</p></div><div className="picture-lesson-tools"><Button variant="secondary" size="compact" type="button" onClick={onChooseUnits}><LayoutGrid aria-hidden="true" />换个单元</Button><LearningListenButton cue={count ? "choose" : "unavailable"} /></div></header>
    <div className="picture-lesson-choices" data-size={count <= 2 ? "small" : "large"}>
      {guide?.presentation && page === 0 && <Link className="learning-picture-launch" href={textbookIntroductionPath(detail.book, guide.introductionId)} aria-label={guide.title}>
        <span className="picture-course-art"><TextbookPicture art={guide.presentation.scenes[0].art} thumbnail /><span className="learning-picture-play"><Play size={30} fill="currentColor" aria-hidden="true" /></span></span>
        <span className="learning-picture-caption"><span>单元探索 · 约 {guide.estimatedMinutes} 分钟</span><strong>{guide.title}</strong></span>
      </Link>}
      {lessons.slice(Math.max(0, first - guideCount), last - guideCount).map(lesson => <Link className="learning-picture-launch" prefetch={false} key={lesson.nodeId}
        href={`/learning/textbooks/courses/${lesson.course!.contentKey}`} aria-label={`开始上课，${lesson.title}`}>
        <span className="picture-course-art"><LessonPicture title={lesson.title} subject={detail.book.subject} /><span className="learning-picture-play"><Play size={30} fill="currentColor" aria-hidden="true" /></span></span>
        <span className="learning-picture-caption"><span>互动课堂</span><strong>{lesson.title}</strong></span>
      </Link>)}
    </div>
    {pages > 1 && <DirectoryPagination page={page} pages={pages} count={count} label="图片课程翻页" onChange={setPage} />}
    {!lessons.length && <p className="textbook-notice">本单元课件正在准备{guide ? "，可以先探索图片导学。" : "，可以切换单元看看。"}</p>}
  </section>;
}

function DirectoryPagination({ page, pages, count, label, onChange }: { page: number; pages: number; count: number; label: string; onChange(page: number): void }) {
  return <nav className="picture-lesson-pagination" aria-label={label}>
    <Button variant="secondary" size="icon" type="button" aria-label="上一组" disabled={page === 0} onClick={() => onChange(page - 1)}><ChevronLeft aria-hidden="true" /></Button>
    <span role="status" aria-live="polite">{page + 1} / {pages}<span>共 {count} 项</span></span>
    <Button variant="secondary" size="icon" type="button" aria-label="下一组" disabled={page === pages - 1} onClick={() => onChange(page + 1)}><ChevronRight aria-hidden="true" /></Button>
  </nav>;
}

function TextbookLoading({ label }: { label: string }) {
  return <div className="textbook-loading" role="status"><span>{label}…</span><div aria-hidden="true" /><div aria-hidden="true" /><div aria-hidden="true" /></div>;
}
