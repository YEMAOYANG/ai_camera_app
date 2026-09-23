"use client";

import { BookOpen, Check, ChevronDown, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { z } from "zod";

import { SpacePageHeading, SpaceShell } from "@/components/student/space-shell";
import { Button } from "@/components/ui/button";
import { LearningClientError } from "@/features/learning/learning-client";
import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";
import { gradeLabel } from "@/features/learning/learning-presenters";
import { textbookCatalogSchema, textbookContentsSchema, type TextbookCatalog, type TextbookContents } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

type State<T> = { key: string; data?: T; error?: string };
const bookKey = (book: { editionId: string; revisionId: string }) => `${book.editionId}:${book.revisionId}`;
const subjectNames = { chinese: "语文", math: "数学", english: "英语" };
const volumeNames = { upper: "上册", lower: "下册", full: "全册" };

async function load<T>(path: string, schema: z.ZodType<T>, signal: AbortSignal) {
  const response = await fetch(path, { cache: "no-store", signal });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = payload as { error?: string; message?: string };
    throw new LearningClientError(response.status, detail.error || "textbook_unavailable", detail.message || "教材暂时没有加载成功");
  }
  return schema.parse(payload);
}

export function LearningTextbooks({ student }: { student: Student }) {
  const router = useRouter();
  const [refresh, setRefresh] = useState(0);
  const [catalog, setCatalog] = useState<State<TextbookCatalog>>({ key: "" });
  const [contents, setContents] = useState<State<TextbookContents>>({ key: "" });
  const [chosen, setChosen] = useState("");
  const catalogKey = `${student.id}:${student.gradeCode}:${refresh}`;
  const data = catalog.key === catalogKey ? catalog.data : undefined;
  const error = catalog.key === catalogKey ? catalog.error : undefined;
  const books = data?.books ?? [];
  const book = books.find(item => bookKey(item) === chosen) ?? books.find(item => item.selected) ?? books[0];
  const edition = book?.editionId;
  const revision = book?.revisionId;
  const contentsKey = `${catalogKey}:${edition}:${revision}`;
  const detail = contents.key === contentsKey ? contents.data : undefined;
  const detailError = contents.key === contentsKey ? contents.error : undefined;

  useEffect(() => {
    const controller = new AbortController();
    void load("/api/learning/textbooks", textbookCatalogSchema, controller.signal).then(result => {
      if (result.gradeCode !== student.gradeCode) throw new Error("年级资料已更新，请重新打开学习空间");
      if (!controller.signal.aborted) setCatalog({ key: catalogKey, data: result });
    }).catch((caught: unknown) => {
      if (controller.signal.aborted) return;
      if (caught instanceof LearningClientError && caught.status === 401) { router.replace("/unlock"); return; }
      setCatalog({ key: catalogKey, error: caught instanceof Error ? caught.message : "教材暂时没有加载成功" });
    });
    return () => controller.abort();
  }, [catalogKey, router, student.gradeCode]);

  useEffect(() => {
    if (!edition || !revision) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ alignmentRevisionId: revision });
    void load(`/api/learning/textbooks/${encodeURIComponent(edition)}/contents?${query}`, textbookContentsSchema, controller.signal).then(result => {
      if (result.book.editionId !== edition || result.book.revisionId !== revision || result.book.gradeCode !== student.gradeCode) throw new Error("教材资料已更新，请刷新目录");
      if (!controller.signal.aborted) setContents({ key: contentsKey, data: result });
    }).catch((caught: unknown) => {
      if (controller.signal.aborted) return;
      if (caught instanceof LearningClientError && caught.status === 401) { router.replace("/unlock"); return; }
      setContents({ key: contentsKey, error: caught instanceof Error ? caught.message : "目录暂时没有加载成功" });
    });
    return () => controller.abort();
  }, [contentsKey, edition, revision, router, student.gradeCode]);

  return <SpaceShell student={student} active="learning" className="space-textbooks">
    <SpacePageHeading title="学校教材" description={`${gradeLabel(student.gradeCode)}，跟着学校的课本学。`} backHref="/learning" backLabel="我的学习">
      <Button variant="secondary" onClick={() => setRefresh(value => value + 1)}><RefreshCw size={18} aria-hidden="true" />刷新教材</Button>
    </SpacePageHeading>
    {error ? <div className="textbook-state" role="alert"><p>{error}</p><Button onClick={() => setRefresh(value => value + 1)}>再试一次</Button></div>
      : !data ? <p className="textbook-state" role="status">正在打开教材目录…</p>
      : !books.length ? <div className="textbook-state"><BookOpen size={32} aria-hidden="true" /><h2>这个年级的教材正在准备</h2><p>准备好后，就能在这里看到学校的单元和课程。</p></div>
      : <div className="textbook-layout">
        <div className="textbook-choices">
        <label className="textbook-mobile-choice">选择教材版本
          <select value={bookKey(book!)} onChange={event => setChosen(event.target.value)}>
            {books.map(item => <option key={bookKey(item)} value={bookKey(item)}>{item.schoolSystem === "six_year" ? "六年制" : "五四制"} · {item.title} · {item.editionLabel}{item.selected ? " · 家长已确认" : ""}</option>)}
          </select>
        </label>
        <nav className="textbook-books" aria-label="选择教材目录">
          {books.map(item => <button key={bookKey(item)} type="button" className="textbook-book" aria-pressed={bookKey(item) === bookKey(book!)} onClick={() => setChosen(bookKey(item))}>
            <span className="textbook-book-subject">{subjectNames[item.subject]} · {volumeNames[item.volume]} · {item.schoolSystem === "six_year" ? "六年制" : "五四制"}</span>
            <strong>{item.title}</strong><span>{item.publisher}</span><small>{item.editionLabel}</small>
            {item.selected ? <span className="textbook-confirmed"><Check size={16} aria-hidden="true" />家长已确认</span> : <span>查看目录</span>}
          </button>)}
        </nav>
        </div>
        <section className="textbook-contents" aria-label="教材单元">
          {detailError ? <div className="textbook-state" role="alert"><p>{detailError}</p><Button onClick={() => setRefresh(value => value + 1)}>重试目录</Button></div>
            : !detail ? <p role="status">正在读取单元…</p>
            : <>
              <div className="textbook-intro"><h2>{detail.book.title}</h2><p>{detail.book.publisher} · {detail.book.editionLabel}</p>
                {!detail.selected ? <p className="textbook-notice">请家长在 App 的“学校教材”中确认用书。你可以先看看目录。</p> : null}
                {detail.book.coverage.status === "partial" ? <p className="textbook-notice">目前展示 {detail.book.unitCount} 个单元，其余目录正在补齐。</p> : null}
                {detail.book.coverage.status === "index_only" ? <p className="textbook-notice">教材版本已收录，单元和课次目录正在核对。</p> : null}
                <a className="focus-ring textbook-source" href={detail.book.sourceUrl} target="_blank" rel="noopener noreferrer">查看官方教材信息<span className="sr-only">（在新窗口打开）</span></a>
              </div>
              {detail.units.map((unit, index) => <details key={unit.unitId} className="textbook-unit" open={index === 0}>
                <summary><h3>{unit.title}</h3><ChevronDown size={22} aria-hidden="true" /></summary>
                <ol>{unit.lessons.map(lesson => <li key={lesson.nodeId} className="textbook-lesson" aria-current={detail.currentNodeId === lesson.nodeId ? "step" : undefined}>
                  <div><h4>{lesson.title}</h4><p>{lesson.printedPage ? `课本第 ${lesson.printedPage} 页` : "对应课本课程"}{detail.currentNodeId === lesson.nodeId ? " · 学校当前进度" : ""}</p></div>
                  {lesson.status === "ready" && lesson.course && detail.selected
                    ? <LearningCourseStartButton courseId={lesson.course.courseId} version={lesson.course.courseVersion} />
                    : <span className="textbook-lesson-status">{lesson.status === "locked" ? lesson.message || "请先完成前面的课程" : lesson.status === "reviewing" ? "教学内容核验中" : "课程准备中"}</span>}
                </li>)}</ol>
              </details>)}
            </>}
        </section>
      </div>}
  </SpaceShell>;
}
