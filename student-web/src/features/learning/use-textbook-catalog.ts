"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { textbookCatalogSchema, type TextbookCatalog } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

export function useTextbookCatalog(student: Student) {
  const router = useRouter();
  const [revision, refresh] = useState(0);
  useEffect(() => {
    const sync = () => refresh(value => value + 1);
    window.addEventListener("focus", sync);
    return () => window.removeEventListener("focus", sync);
  }, []);
  const key = `${student.id}:${student.gradeCode}:${revision}`;
  const [result, setResult] = useState<{ key: string; data?: TextbookCatalog; error?: string }>({ key: "" });
  useEffect(() => {
    const controller = new AbortController();
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
        if (!controller.signal.aborted) setResult({ key, error: error instanceof Error ? error.message : "课本暂时没有加载成功" });
      }
    }
    void read();
    return () => controller.abort();
  }, [key, router, student.gradeCode]);
  return { key, data: result.key === key ? result.data : undefined, error: result.key === key ? result.error : undefined, refresh: () => refresh(value => value + 1) };
}
