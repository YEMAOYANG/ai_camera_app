"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { textbookCatalogSchema, type TextbookCatalog } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

const FOCUS_REVALIDATE_AFTER_MS = 30_000;

export function useTextbookCatalog(student: Student) {
  const router = useRouter();
  const [revision, refresh] = useState(0);
  const studentKey = `${student.id}:${student.gradeCode}`;
  const lastAttempt = useRef({ key: "", at: 0 });
  useEffect(() => {
    const sync = () => {
      const last = lastAttempt.current;
      if (document.visibilityState === "hidden" || (last.key === studentKey && Date.now() - last.at < FOCUS_REVALIDATE_AFTER_MS)) return;
      refresh(value => value + 1);
    };
    window.addEventListener("focus", sync);
    return () => window.removeEventListener("focus", sync);
  }, [studentKey]);
  const key = studentKey;
  const [result, setResult] = useState<{ key: string; data?: TextbookCatalog; error?: string }>({ key: "" });
  useEffect(() => {
    const controller = new AbortController();
    lastAttempt.current = { key, at: Date.now() };
    async function read() {
      try {
        const response = await fetch("/api/learning/textbooks", { cache: "no-store", signal: controller.signal });
        if (response.status === 401) { router.replace("/unlock"); return; }
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.message || "课本暂时没有加载成功");
        const data = textbookCatalogSchema.parse(payload);
        if (data.gradeCode !== student.gradeCode) throw new Error("年级资料已更新，请重新打开学习空间");
        if (!controller.signal.aborted) setResult({ key, data });
      } catch (error) {
        if (!controller.signal.aborted) setResult(current => current.key === key && current.data
          ? current
          : { key, error: error instanceof Error ? error.message : "课本暂时没有加载成功" });
      }
    }
    void read();
    return () => controller.abort();
  }, [key, revision, router, student.gradeCode]);
  return {
    key,
    revalidationRevision: revision,
    data: result.key === key ? result.data : undefined,
    error: result.key === key ? result.error : undefined,
    refresh: () => refresh(value => value + 1),
  };
}
