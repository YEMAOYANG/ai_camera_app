"use client";

import { Check, LoaderCircle } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useState } from "react";

import { getLearningTeachers, setLearningTeacher } from "@/features/learning/learning-client";
import {
  teacherStyleDescription,
  teacherTone,
} from "@/features/learning/teacher-registry";
import type {
  LearningSubject,
  LearningTeacherProfile,
  LearningTeachersResponse,
} from "@/lib/contracts/learning";

const subjectChoices: Array<{ id: LearningSubject; label: string }> = [
  { id: "chinese", label: "语文" },
  { id: "math", label: "数学" },
  { id: "english", label: "英语" },
];

export function TeacherPicker({ compact = false, subject }: { compact?: boolean; subject?: LearningSubject }) {
  const [selectedSubject, setSelectedSubject] = useState<LearningSubject>(subject || "chinese");
  const activeSubject = subject || selectedSubject;
  const [data, setData] = useState<LearningTeachersResponse | null>(null);
  const [savingId, setSavingId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await getLearningTeachers(activeSubject));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "老师列表暂时没有加载成功");
    }
  }, [activeSubject]);

  useEffect(() => {
    let active = true;
    getLearningTeachers(activeSubject)
      .then((value) => { if (active) setData(value); })
      .catch((caught: unknown) => {
        if (active) setError(caught instanceof Error ? caught.message : "老师列表暂时没有加载成功");
      });
    return () => { active = false; };
  }, [activeSubject]);

  async function select(teacher: LearningTeacherProfile) {
    if (savingId || teacher.id === data?.selected?.id) return;
    setSavingId(teacher.id);
    setError("");
    try {
      const saved = await setLearningTeacher(activeSubject, teacher.id, teacher.version);
      setData((current) => current ? {
        ...current,
        items: current.items.map((item) => item.id === saved.teacher.id ? saved.teacher : item),
        selected: { id: saved.teacher.id, version: saved.teacher.version },
      } : current);
    } catch (caught) {
      // Keep the last server-confirmed selection visible. A failed request must
      // never look like the child's preference was saved.
      setError(caught instanceof Error ? caught.message : "老师偏好暂时没有保存成功");
    } finally {
      setSavingId("");
    }
  }

  return (
    <section className={`learning-teacher-picker ${compact ? "is-compact" : ""}`} aria-labelledby="teacher-picker-title">
      <div className="learning-teacher-intro">
        <p>课堂老师</p>
        <h2 id="teacher-picker-title">今天想和谁一起学？</h2>
        <span>按学科选择老师；发布后的讲解声音会跟随课程正式音频。</span>
      </div>
      <div className="learning-teacher-chooser">
        {!subject ? (
          <div className="learning-teacher-subjects" role="group" aria-label="选择老师学科">
            {subjectChoices.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`focus-ring ${activeSubject === item.id ? "is-active" : ""}`}
                aria-pressed={activeSubject === item.id}
                onClick={() => { setData(null); setError(""); setSelectedSubject(item.id); }}
              >
                {item.label}
              </button>
            ))}
          </div>
        ) : null}
        {!data && !error ? (
          <div className="learning-teacher-loading" aria-live="polite"><LoaderCircle className="size-5 animate-spin" />正在叫老师来</div>
        ) : null}
        {data ? (
          <div className="learning-teacher-options" role="radiogroup" aria-label="选择课堂老师">
            {data.items.map((teacher) => {
              const selected = teacher.id === data.selected?.id && teacher.version === data.selected.version;
              return (
                <button
                  key={`${teacher.id}:${teacher.version}`}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  className={`focus-ring learning-teacher-option tone-${teacherTone(teacher)} ${selected ? "is-selected" : ""}`}
                  onClick={() => void select(teacher)}
                  disabled={Boolean(savingId)}
                >
                  <span className="learning-teacher-avatar"><Image src={teacher.avatarPath} width={64} height={64} alt={`${teacher.displayName}头像`} priority={false} /></span>
                  <span><strong>{teacher.displayName}</strong><small>{teacherStyleDescription(teacher)}</small></span>
                  <i aria-hidden="true">{savingId === teacher.id ? <LoaderCircle className="size-4 animate-spin" /> : selected ? <Check className="size-4" /> : null}</i>
                </button>
              );
            })}
          </div>
        ) : null}
        {data && !data.items.length ? <p className="learning-inline-error">这个学科的老师还在准备中。</p> : null}
        {error ? <p className="learning-inline-error" role="alert">{error} <button type="button" onClick={() => void load()}>再试一次</button></p> : null}
      </div>
    </section>
  );
}
