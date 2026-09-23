"use client";

import { ArrowRight, Check, ChevronDown, CircleDot, LockKeyhole, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { SpacePageHeading, SpaceShell } from "@/components/student/space-shell";
import { Button } from "@/components/ui/button";
import { LearningClientError } from "@/features/learning/learning-client";
import { LearningCourseStartButton } from "@/features/learning/learning-course-start-button";
import { gradeLabel } from "@/features/learning/learning-presenters";
import { learningSubjectSchema, type LearningSubject } from "@/lib/contracts/learning";
import { progressiveGradeSchema, progressiveLessonHasClassroom, progressivePathSchema, type ProgressiveGrade, type ProgressiveLesson, type ProgressivePath } from "@/lib/contracts/progressive-learning";
import type { Student } from "@/lib/contracts/student-session";

const subjects: { id: LearningSubject; label: string }[] = [
  { id: "chinese", label: "语文" }, { id: "math", label: "数学" }, { id: "english", label: "英语" },
];

async function loadPath(gradeCode: ProgressiveGrade, subject: LearningSubject, signal: AbortSignal) {
  const response = await fetch(`/api/learning/path?${new URLSearchParams({ subject, gradeCode })}`, { signal, cache: "no-store" });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = payload as { error?: string; message?: string };
    throw new LearningClientError(response.status, detail.error || "learning_path_unavailable", detail.message || "学习路线暂时没有加载成功");
  }
  const parsed = progressivePathSchema.safeParse(payload);
  if (!parsed.success || parsed.data.gradeCode !== gradeCode || parsed.data.subject !== subject) {
    throw new Error("学习路线暂时没有加载成功，请再试一次");
  }
  return parsed.data;
}

type LoadState = { key: string; data?: ProgressivePath; error?: string };

export function LearningPath({ student, navigate }: { student: Student; navigate?: (path: string) => void }) {
  const router = useRouter();
  const initialGrade = progressiveGradeSchema.safeParse(student.gradeCode);
  const [grade, setGrade] = useState<ProgressiveGrade>(initialGrade.success ? initialGrade.data : "primary_1");
  // The session gate mounts this view only after browser authentication. Keep
  // the selected subject in the URL so a reload returns to the same route.
  const [subject, setSubject] = useState<LearningSubject>(() => {
    const query = typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("subject");
    const parsed = learningSubjectSchema.safeParse(query);
    return parsed.success ? parsed.data : "chinese";
  });
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<LoadState>({ key: "" });
  const [selected, setSelected] = useState<{ key: string; lessonId: string } | null>(null);
  const focusHeading = useRef<HTMLHeadingElement>(null);
  const queryKey = `${grade}:${subject}:${revision}`;

  useEffect(() => {
    const controller = new AbortController();
    void loadPath(grade, subject, controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ key: queryKey, data });
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      if (error instanceof LearningClientError && error.status === 401) {
        router.replace("/unlock");
        return;
      }
      setState({ key: queryKey, error: error instanceof Error ? error.message : "学习路线暂时没有加载成功" });
    });
    return () => controller.abort();
  }, [grade, subject, queryKey, router]);

  const loaded = state.key === queryKey;
  const data = loaded ? state.data : undefined;
  const error = loaded ? state.error : undefined;
  const browsingOtherGrade = grade !== student.gradeCode;
  const allRows = data?.currentGradeLessons ?? [];
  const byId = new Map(allRows.map(lesson => [lesson.lessonId, lesson]));
  const selectedLesson = selected?.key === queryKey ? byId.get(selected.lessonId) : undefined;
  const currentLesson = browsingOtherGrade ? undefined : selectedLesson ?? data?.nextLesson ?? undefined;
  const completed = data?.currentGradeLessons.filter(lesson => lesson.status === "mastered").length ?? 0;

  function chooseLesson(lesson: ProgressiveLesson) {
    if (browsingOtherGrade || !progressiveLessonHasClassroom(lesson) || lesson.gradeCode !== student.gradeCode) return;
    setSelected({ key: queryKey, lessonId: lesson.lessonId });
    focusHeading.current?.focus();
  }

  function chooseSubject(value: LearningSubject) {
    setSubject(value);
    const url = new URL(window.location.href);
    url.searchParams.set("subject", value);
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }

  return <SpaceShell student={student} active="learning" className="space-learning-path">
    <SpacePageHeading title="我的学习路线" description={`${gradeLabel(student.gradeCode)}课程，从本年级入门一步一步学起。`} backHref="/learning" backLabel="我的学习">
      <Button variant="secondary" onClick={() => setRevision(value => value + 1)} aria-label="刷新学习路线"><RefreshCw size={18} aria-hidden="true" />刷新</Button>
    </SpacePageHeading>

    <div className="learning-path-filters">
      <div className="learning-path-subjects" role="group" aria-label="选择学科">
        {subjects.map(item => <button className="focus-ring" type="button" key={item.id} aria-pressed={subject === item.id} onClick={() => chooseSubject(item.id)}>{item.label}</button>)}
      </div>
      <label className="learning-path-grade">查看年级<select className="focus-ring" value={grade} onChange={event => setGrade(event.target.value as ProgressiveGrade)}>
        {progressiveGradeSchema.options.map(code => <option value={code} key={code}>{gradeLabel(code)}{code === student.gradeCode ? " · 我的年级" : ""}</option>)}
      </select></label>
    </div>

    {browsingOtherGrade && <p className="learning-path-browse-note" role="status">{`正在预览${gradeLabel(grade)}课程目录。你的学习仍按${gradeLabel(student.gradeCode)}课程推进。`}</p>}

    {!loaded && <section className="learning-path-state" role="status"><CircleDot size={28} aria-hidden="true" /><h2>正在整理你的学习路线</h2><p>正在读取已经学会的内容。</p></section>}
    {error && <section className="learning-path-state" role="alert"><h2>暂时没有连接上</h2><p>{error}</p><Button onClick={() => setRevision(value => value + 1)}>再试一次</Button></section>}

    {data && <>
      {currentLesson ? <section className="learning-path-next" aria-labelledby="path-next-title">
        <div className="learning-path-next__rail" aria-hidden="true"><CircleDot /></div>
        <div className="learning-path-next__body">
          <p className="space-eyebrow">{selectedLesson ? "你选择的这一步" : `${gradeLabel(grade)} · 接下来学这一课`}</p>
          <h2 id="path-next-title" tabIndex={-1} ref={focusHeading}>{currentLesson.title}</h2>
          <p className="learning-path-context">{gradeLabel(currentLesson.gradeCode)} · {currentLesson.unitTitle}</p>
          <EvidenceNote lesson={currentLesson} />
          {!progressiveLessonHasClassroom(currentLesson) && <p className="learning-path-preparing">这节课正在准备。准备好后从这里继续，不会跳到后面的新知识。</p>}
          <div className="learning-path-next__actions">
            {progressiveLessonHasClassroom(currentLesson) && currentLesson.course ? <LearningCourseStartButton
              key={`${currentLesson.course.courseId}:${currentLesson.course.courseVersion}`}
              courseId={currentLesson.course.courseId} version={currentLesson.course.courseVersion}
              label={currentLesson.status === "mastered" ? "复习这一步" : "开始这一步"}
              navigate={navigate}
              progression={{ schemaVersion: "mira.learning.progression.v1", curriculumVersion: data.curriculumVersion,
                granularity: "lesson", lessonId: currentLesson.lessonId, skillId: currentLesson.lessonId,
                sequence: currentLesson.sequence, learningStatus: currentLesson.status, canStart: currentLesson.canStart,
                blockedBySkillIds: currentLesson.blockedByLessonIds, message: currentLesson.message }}
            /> : <Button disabled>课程准备中</Button>}
            {selectedLesson && data.nextLesson && selectedLesson.lessonId !== data.nextLesson.lessonId && <button className="focus-ring learning-path-text-button" onClick={() => setSelected(null)}>回到推荐课</button>}
          </div>
        </div>
      </section> : !browsingOtherGrade && <section className="learning-path-state"><h2>{data.currentGradeLessons.length > 0 && completed === data.currentGradeLessons.length ? "这一阶段已经学会了" : "按本年级的课次继续"}</h2><p>{data.currentGradeLessons.length ? "查看下面的具体步骤，已掌握的内容可以继续复习。" : "这个阶段的路线暂时没有返回，请刷新后再试。"}</p></section>}

      <section className="learning-path-map" aria-labelledby="path-map-title">
        <div className="learning-path-section-heading"><div><h2 id="path-map-title">{gradeLabel(grade)} · {subjects.find(item => item.id === subject)?.label}路线</h2><p>展开单元，看看每一步要学什么。</p></div><span className="learning-path-total">已掌握 {completed} / {data.currentGradeLessons.length} 步</span></div>
        {(["upper", "lower"] as const).map(phase => <div className="learning-path-phase" key={phase}>
          <h3>{phase === "upper" ? "上阶段" : "下阶段"}<span>按学习进度推进</span></h3>
          <UnitGroups lessons={data.currentGradeLessons.filter(lesson => lesson.phase === phase)} byId={byId} onChoose={chooseLesson} disableStart={browsingOtherGrade} activeId={currentLesson?.lessonId} />
        </div>)}
      </section>
      <p className="learning-path-footer">完成一节课和独立学会是两回事。不同练习与后续复习会帮助确认掌握情况。<Link href="/learning/practice">复习学过的内容<ArrowRight size={16} aria-hidden="true" /></Link></p>
    </>}
  </SpaceShell>;
}

function EvidenceNote({ lesson }: { lesson: ProgressiveLesson }) {
  if (lesson.assessmentMode === "observed") return <p className="learning-path-evidence">这节课需要实际表现确认，答对选择题不代表已经掌握。</p>;
  return <p className="learning-path-evidence">{lesson.independentEvidenceCount > 0
    ? `独立作答 ${lesson.independentEvidenceCount} 次 · 答对 ${lesson.independentCorrectCount} 次 · ${lesson.distinctAssessmentSets} 组不同练习`
    : "从老师示范开始，再自己试一试。"}{lesson.stabilityStatus === "due" ? " · 到复习的时候了" : lesson.stabilityStatus === "stable" ? " · 延后复习已通过" : ""}</p>;
}

function UnitGroups({ lessons, byId, onChoose, disableStart, activeId }: {
  lessons: ProgressiveLesson[]; byId: Map<string, ProgressiveLesson>;
  onChoose: (lesson: ProgressiveLesson) => void; disableStart: boolean; activeId?: string;
}) {
  const groups = new Map<string, ProgressiveLesson[]>();
  for (const lesson of lessons) groups.set(lesson.unitId, [...(groups.get(lesson.unitId) ?? []), lesson]);
  return <div className="learning-path-units">{[...groups].map(([unitId, rows]) => {
    const complete = rows.filter(row => row.status === "mastered").length;
    return <details className="learning-path-unit" key={unitId} open={activeId ? rows.some(row => row.lessonId === activeId) : undefined}>
      <summary className="focus-ring"><span className="learning-path-unit__marker" aria-hidden="true">{complete === rows.length ? <Check size={18} /> : rows[0].unitId.slice(-2)}</span><span className="learning-path-unit__title">{rows[0].unitTitle}<small>{rows.length} 个小步骤 · 已掌握 {complete} 个</small></span><ChevronDown size={20} className="learning-path-chevron" aria-hidden="true" /></summary>
      <ol>{rows.map(lesson => {
        const locked = disableStart || !lesson.canStart || lesson.status === "locked";
        const ready = !locked && progressiveLessonHasClassroom(lesson);
        const blockers = lesson.blockedByLessonIds.slice(0, 2).map(id => byId.get(id)?.title ?? "前面的基础课");
        const label = disableStart ? "目录预览" : locked ? "暂未解锁" : !ready ? "课程准备中" : lesson.status === "mastered" ? "复习这一步" : "选这一步";
        return <li key={lesson.lessonId} className={`learning-path-step${lesson.lessonId === activeId ? " is-current" : ""}`}>
          <span className={`learning-path-step__marker ${lesson.status === "mastered" ? "is-mastered" : ""}`} aria-hidden="true">{locked ? <LockKeyhole size={17} /> : lesson.status === "mastered" ? <Check size={18} /> : lesson.sequence}</span>
          <div className="learning-path-step__text"><h4>{lesson.title}</h4>
            <p>{disableStart ? "仅查看本年级课程顺序。" : locked ? blockers.length ? `先完成：${blockers.join("、")}${lesson.blockedByLessonIds.length > 2 ? `等 ${lesson.blockedByLessonIds.length} 项基础` : ""}` : "先完成本年级前面的课次。"
              : lesson.status === "mastered" ? "已掌握" : lesson.status === "needs_practice" ? "再独立练习，学稳这一步" : "前面的基础已就绪"}</p>
            {lesson.assessmentMode === "observed" && <small>需要实际表现确认</small>}
            {lesson.independentEvidenceCount > 0 && <small>独立作答 {lesson.independentEvidenceCount} 次 · 答对 {lesson.independentCorrectCount} 次</small>}
          </div>
          <button type="button" className="focus-ring learning-path-step__action" disabled={!ready} onClick={() => onChoose(lesson)} aria-label={`${lesson.title}：${label}`}>{label}</button>
        </li>;
      })}</ol>
    </details>;
  })}</div>;
}
