import { LearningClientError } from "@/features/learning/learning-client";
import { textbookContentsSchema, type TextbookContents } from "@/lib/contracts/textbooks";
import type { Student } from "@/lib/contracts/student-session";

type TextbookIdentity = { editionId: string; revisionId: string };
type StudentIdentity = Pick<Student, "id" | "gradeCode">;
type Preload = {
  expiresAt: number;
  fetcher: typeof globalThis.fetch;
  request: Promise<TextbookContents>;
};

const PRELOAD_TTL_MS = 15_000;
const preloads = new Map<string, Preload>();

function requestKey(student: StudentIdentity, book: TextbookIdentity) {
  return `${student.id}:${student.gradeCode}:${book.editionId}:${book.revisionId}`;
}

export function textbookContentsRequestPath(book: TextbookIdentity) {
  const query = new URLSearchParams({ alignmentRevisionId: book.revisionId });
  return `/api/learning/textbooks/${encodeURIComponent(book.editionId)}/contents?${query}`;
}

async function requestContents(book: TextbookIdentity, signal?: AbortSignal) {
  const response = await fetch(textbookContentsRequestPath(book), { cache: "no-store", signal });
  const payload: unknown = await response.json();
  if (!response.ok) {
    const detail = payload as { error?: string; message?: string };
    throw new LearningClientError(response.status, detail.error || "textbook_unavailable", detail.message || "教材暂时没有加载成功");
  }
  return textbookContentsSchema.parse(payload);
}

function findPreload(student: StudentIdentity, book: TextbookIdentity) {
  const key = requestKey(student, book);
  const preload = preloads.get(key);
  if (!preload) return;
  if (preload.fetcher !== globalThis.fetch || preload.expiresAt <= Date.now()) {
    preloads.delete(key);
    return;
  }
  return { key, preload };
}

// The book-opening motion gives the directory request a useful head start. The
// destination consumes this exact request once, so preloading never duplicates
// the authenticated API call or creates a second source of textbook data.
export function preloadTextbookContents(student: StudentIdentity, book: TextbookIdentity) {
  if (findPreload(student, book)) return;
  for (const [key, preload] of preloads) {
    if (preload.fetcher !== globalThis.fetch || preload.expiresAt <= Date.now()) preloads.delete(key);
  }
  const key = requestKey(student, book);
  const request = requestContents(book);
  preloads.set(key, { expiresAt: Date.now() + PRELOAD_TTL_MS, fetcher: globalThis.fetch, request });
  void request.catch(() => {});
}

export function loadTextbookContents(student: StudentIdentity, book: TextbookIdentity, signal: AbortSignal) {
  const found = findPreload(student, book);
  if (!found) return requestContents(book, signal);
  preloads.delete(found.key);
  return found.preload.request;
}
