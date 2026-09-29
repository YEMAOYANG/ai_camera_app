"use client";

import { ArrowRight, BookOpen, Check, RefreshCw, Settings2 } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type MouseEvent } from "react";
import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { SchoolbagStage, useSchoolbagMotion, useSchoolbagMotionPreference } from "@/components/schoolbag/schoolbag-motion";
import type { SchoolSubject } from "@/components/schoolbag/motion-timeline";
import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/ui/disclosure";
import { SwitchField } from "@/components/ui/switch";
import { textbookContentsPath } from "@/features/learning/textbook-navigation";
import { useTextbookCatalog } from "@/features/learning/use-textbook-catalog";
import type { TextbookCatalog } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

const subjects = [
  { id: "chinese", name: "语文", sound: "yǔ wén" },
  { id: "math", name: "数学", sound: "shù xué" },
  { id: "english", name: "英语", sound: "yīng yǔ" },
  { id: "science", name: "科学", sound: "kē xué" },
] as const;
type Book = TextbookCatalog["books"][number];

export function LearningSchoolbag({ student }: { student: Student }) {
  const { data, error, refresh } = useTextbookCatalog(student);
  const [notice, setNotice] = useState<SchoolSubject | null>(null);
  const motion = useSchoolbagMotion();
  const { reduced, toggle } = useSchoolbagMotionPreference();
  const noteRef = useRef<HTMLDivElement>(null);
  const journey = data?.learningJourneys?.find(item => item.parentNeeded || item.reviewDue || ['learning', 'checking', 'reviewing'].includes(item.status)) ?? data?.learningJourneys?.[0];
  const books = data?.books.filter(book => book.selected) ?? [];

  function openBook(event: MouseEvent<HTMLAnchorElement>, book: Book) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    if (!motion.busy) motion.openBook(book.subject, textbookContentsPath(book));
  }
  function showNotice(subject: SchoolSubject) {
    setNotice(subject);
    window.requestAnimationFrame(() => noteRef.current?.focus({ preventScroll: true }));
  }
  function selectSubject(subject: SchoolSubject) {
    if (!data || motion.busy) return;
    const book = books.find(item => item.subject === subject);
    if (book) motion.openBook(subject, textbookContentsPath(book)); else showNotice(subject);
  }
  const noticeName = subjects.find(subject => subject.id === notice)?.name;
  const needsSelection = data?.subjects?.find(subject => subject.subject === notice)?.status === "selection_required";

  return <SchoolbagShell student={student} home className="schoolbag-home" tools={
    <Disclosure className="schoolbag-settings" title={<span><Settings2 size={16} aria-hidden="true" />家长与设置</span>}>
      <p>在家长 App「孩子资料 → 教材与课程」确认版本与学期。</p>
      {data && <p>{data.schoolYearStartYear}—{data.schoolYearStartYear + 1} 学年 · {data.semester === "upper" ? "上学期" : "下学期"}</p>}
      <div className="schoolbag-preferences"><SwitchField label="拿书动效" checked={!reduced} onCheckedChange={toggle} /><Button variant="quiet" onClick={() => { setNotice(null); refresh(); }}><RefreshCw size={16} aria-hidden="true" />刷新书包</Button></div>
    </Disclosure>
  }>
    <section className="schoolbag-hero" aria-labelledby="schoolbag-title">
      <div className="schoolbag-copy">
        <p className="schoolbag-eyebrow">你的学习时光</p>
        <h1 id="schoolbag-title">今天，想学哪一本？</h1>
        <p className="schoolbag-invitation">从书包里，拿出一本好奇。</p>
        {journey && <div className="schoolbag-next-lesson">
          <strong>{journey.reviewDue ? '到短复习时间啦' : journey.parentNeeded ? '休息好了，再来试试' : journey.status === 'retained' ? '隔了几天，也记得' : journey.reviewDueAt ? '今天的小任务完成啦' : '继续上次的小任务'}</strong>
          <p>《{journey.title}》{journey.reviewDue ? ' · 换个情境，再认一认' : journey.reviewDueAt ? ` · 下次复习 ${new Date(journey.reviewDueAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })}` : ''}</p>
          {(journey.reviewDue || !journey.reviewDueAt && journey.status !== 'retained' || journey.parentNeeded) && <Link href={`/learning/textbooks/courses/${journey.contentKey}`} className="mira-button mira-button--primary">{journey.reviewDue ? '开始短复习' : '继续小任务'}<ArrowRight size={18} aria-hidden="true" /></Link>}
        </div>}

      </div>
      <div className="schoolbag-book-space">
        <div className="schoolbag-stage schoolbag-stage--3d" aria-busy={!data && !error}>
          <SchoolbagStage pose="ready" label="打开的黄色书包，里面放着语文、数学、英语和科学课本" onSelect={selectSubject} />
        </div>
        <nav className="schoolbag-subjects" aria-label="选择课本">
          {subjects.map(subject => {
            const book = books.find(item => item.subject === subject.id);
            const selectionRequired = data?.subjects?.find(item => item.subject === subject.id)?.status === "selection_required";
            const status = !data ? "正在装入" : book ? "打开课本" : selectionRequired ? "等家长选书" : "教材暂未收录";
            const className = `schoolbag-subject schoolbag-subject--${subject.id}`;
            const content = <><small>{subject.sound}</small><strong>{subject.name}</strong><span>{status}{book && <ArrowRight size={14} aria-hidden="true" />}</span></>;
            const hover = { onPointerEnter: () => motion.hover(subject.id), onPointerLeave: () => motion.hover(null), onFocus: () => motion.hover(subject.id), onBlur: () => motion.hover(null) };
            return book ? <Link href={textbookContentsPath(book)} key={subject.id} className={className} aria-label={`拿出${subject.name}课本`} onClick={event => openBook(event, book)} {...hover}>{content}</Link>
              : <button key={subject.id} className={className} type="button" aria-label={`${subject.name}，${status}`} disabled={!data} onClick={() => showNotice(subject.id)} {...hover}>{content}</button>;
          })}
        </nav>
      </div>
    </section>
    <div className="schoolbag-feedback" aria-live="polite">
      {error ? <div className="schoolbag-notice" role="alert"><BookOpen size={22} aria-hidden="true" /><div><strong>课本暂时没装进来</strong><p>{error}</p></div><Button onClick={refresh}>再试一次</Button></div>
        : !data ? <p className="schoolbag-loading" role="status">正在整理你的书包…</p>
        : notice ? <div className="schoolbag-notice" ref={noteRef} tabIndex={-1}><BookOpen size={24} aria-hidden="true" /><div><strong>{needsSelection ? `请家长帮你放入${noticeName}课本` : `${noticeName}教材暂未收录`}</strong><p>{needsSelection ? "在家长 App 的「孩子资料 → 学校教材」确认用书，然后刷新书包。" : "请家长核对课本信息，也可以先学习已放入书包的课本。"}</p></div><button type="button" onClick={() => setNotice(null)}>知道啦<Check size={18} aria-hidden="true" /></button></div>
        : !books.length ? <p className="schoolbag-tip">请家长在 App 中确认学校课本，再开始学习。</p> : null}
    </div>
  </SchoolbagShell>;
}
