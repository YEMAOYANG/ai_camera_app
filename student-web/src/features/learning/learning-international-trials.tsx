"use client";

import { ArrowUpRight, Backpack, BookOpen, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SchoolbagShell } from "@/components/student/schoolbag-shell";
import { Button } from "@/components/ui/button";
import { internationalTrialsSchema, type InternationalTrials, type InternationalTrialTextbook } from "@/lib/contracts/international-trials";
import type { Student } from "@/lib/contracts/student-session";
import styles from "./learning-international-trials.module.css";

function TextbookTrial({ book }: { book: InternationalTrialTextbook }) {
  const chinese = book.subject === "chinese";
  return <article className={styles.book} aria-labelledby={`${book.id}-title`}>
    <div className={`${styles.subject} ${chinese ? styles.chinese : styles.english}`}>
      <BookOpen aria-hidden="true" />
      <strong>{chinese ? "语文" : "英语"}</strong>
      <span>{chinese ? "五年级 · 下学期" : "六年级 · 上学期"}</span>
    </div>
    <div className={styles.bookContent}>
      <header className={styles.bookHeading}>
        <div><p className={styles.label}>申请测试的教材</p><h2 id={`${book.id}-title`}>{book.requestedTitle}</h2></div>
        <span className={styles.status}>{book.editionStatus === "catalog_verified" ? "已核对官方书目" : "版本待确认"}</span>
      </header>
      <div className={styles.bookDetails}>
        <div className={styles.verification}>
          {book.matchedTitle && <dl className={styles.metadata}><div><dt>对应书名</dt><dd>{book.matchedTitle}</dd></div>{book.publisher && <div><dt>出版社</dt><dd>{book.publisher}</dd></div>}</dl>}
          <p>{book.editionNote}</p>
          {book.candidates.length > 0 && <div className={styles.candidates}><h3>相关书目，尚未确定对应版本</h3><ul>{book.candidates.map(candidate => <li key={`${candidate.title}:${candidate.url}`}><a href={candidate.url} target="_blank" rel="noopener noreferrer">{candidate.title}<ArrowUpRight aria-hidden="true" /></a><p>{candidate.publisher} · {candidate.editionNote}</p></li>)}</ul></div>}
        </div>
        <section className={styles.materials} aria-labelledby={`${book.id}-materials`}>
          <h3 id={`${book.id}-materials`}>还需要的教材资料</h3>
          {book.requiredMaterials.length ? <ul>{book.requiredMaterials.map(material => <li key={material}>{material}</li>)}</ul> : <p>教材资料要求仍在核对，暂时不能生成课件。</p>}
        </section>
      </div>
      <div className={styles.evidence}><h3>核验来源</h3>{book.evidence.length ? <ul>{book.evidence.map(source => <li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.label}<ArrowUpRight aria-hidden="true" /></a><p>{source.detail}</p></li>)}</ul> : <p>暂未提供可核验来源。</p>}</div>
    </div>
  </article>;
}

export function LearningInternationalTrials({ student }: { student: Student }) {
  const router = useRouter();
  const [revision, setRevision] = useState(0);
  const key = `${student.id}:${revision}`;
  const [result, setResult] = useState<{ key: string; data?: InternationalTrials; error?: string }>({ key: "" });
  const data = result.key === key ? result.data : undefined;
  const error = result.key === key ? result.error : undefined;

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch("/api/learning/international-trials", { cache: "no-store", signal: controller.signal });
        if (controller.signal.aborted) return;
        if (response.status === 401) { router.replace("/unlock"); return; }
        if (!response.ok) throw new Error("load_failed");
        const payload: unknown = await response.json();
        const next = internationalTrialsSchema.parse(payload);
        if (!controller.signal.aborted) setResult({ key, data: next });
      } catch {
        if (!controller.signal.aborted) setResult({ key, error: "教材测试暂时没有加载成功，请再试一次。" });
      }
    }
    void load();
    return () => controller.abort();
  }, [key, router]);

  const refresh = () => setRevision(value => value + 1);
  return <SchoolbagShell student={student}>
    <div className={styles.page}>
      <header className={styles.heading}>
        <div><p className={styles.eyebrow}>家长与设置</p><h1>国际教材测试</h1><p>分别核对语文五年级下学期、英语六年级上学期的教材与课件。</p></div>
        <Button asChild variant="quiet" size="compact"><Link href="/learning"><Backpack aria-hidden="true" />回到书包</Link></Button>
      </header>
      {error ? <section className={styles.message} role="alert"><h2>教材测试暂时没打开</h2><p>{error}</p><Button variant="secondary" size="compact" onClick={refresh}><RefreshCw aria-hidden="true" />再试一次</Button></section>
        : !data ? <section className={styles.message} role="status" aria-live="polite"><BookOpen aria-hidden="true" /><p>正在核对教材与课件状态…</p></section>
          : <>
            <section className={styles.school} aria-label="测试学校">
              <div><p className={styles.label}>测试学校</p><h2>{data.school.requestedName}</h2><p>学校用书尚待确认 · <a href={data.school.website} target="_blank" rel="noopener noreferrer">{data.school.name}官网<ArrowUpRight aria-hidden="true" /></a></p></div>
              <div className={styles.refresh}><span>核验日期 {data.checkedAt}</span><Button variant="secondary" size="compact" onClick={refresh}><RefreshCw aria-hidden="true" />刷新状态</Button></div>
            </section>
            <section className={styles.notice} aria-label="课件生成状态"><BookOpen aria-hidden="true" /><div><h2>待补教材资料</h2><p><strong>尚未生成课件。</strong>需要先确认准确版本、目录和试讲课文页，才能生成与这套教材对应的课程。</p></div></section>
            {data.textbooks.length ? <div className={styles.books}>{data.textbooks.map(book => <TextbookTrial key={book.id} book={book} />)}</div>
              : <section className={styles.message}><h2>暂无待测试的教材</h2><p>教材资料核对后会显示在这里。</p></section>}
          </>}
    </div>
  </SchoolbagShell>;
}
