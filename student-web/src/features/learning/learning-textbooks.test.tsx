import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningTextbooks } from "@/features/learning/learning-textbooks";
import { textbookContentsSchema } from "@/lib/contracts/textbooks";

const { router, startLearningCourse } = vi.hoisted(() => ({ router: { replace: vi.fn() }, startLearningCourse: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/learning/learning-client", async importOriginal => ({ ...await importOriginal<typeof import("@/features/learning/learning-client")>(), startLearningCourse }));
vi.mock("@/components/student/space-shell", () => ({
  SpaceShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
  SpacePageHeading: ({ title, children }: { title: string; children: ReactNode }) => <header><h1>{title}</h1>{children}</header>,
}));
const student = { id: "student-a", childId: "child-a", displayName: "乐乐", gradeCode: "primary_1" };
const book = { editionId: "pep-chinese-g1", revisionId: "review-1", title: "语文 一年级上册", publisher: "人民教育出版社", editionLabel: "测试目录", gradeCode: "primary_1", subject: "chinese", volume: "upper", schoolSystem: "six_year", coverage: { status: "partial", note: "仅首单元" }, sourceUrl: "https://basic.smartedu.cn/tchMaterial/detail?contentId=test", unitCount: 1, lessonCount: 1 };
const catalog = (selected = false) => ({ ok: true, schemaVersion: "mira.learning.textbooks.v1", gradeCode: "primary_1", schoolYearStartYear: 2026, semester: "upper", books: [{ ...book, selected, selectionRevision: selected ? 1 : 0, currentNodeId: null }] });
const detail = (selected = false) => ({ ok: true, schemaVersion: "mira.learning.textbooks.v1", book, selected, selectionRevision: selected ? 1 : 0, currentNodeId: null, units: [{ unitId: "u1", title: "第一单元 · 识字", sequence: 1, lessons: [{ nodeId: "u1-l1", title: "1 天地人", sequence: 1, printedPage: 8, pdfPage: 13, objectives: [], status: "reviewing", course: null }] }] });
const reply = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe("school textbooks", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("shows verified order/page and partial coverage without creating a course or choosing for parents", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply(catalog())).mockResolvedValueOnce(reply(detail()));
    vi.stubGlobal("fetch", fetch);
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("heading", { name: "1 天地人" })).toBeInTheDocument();
    expect(screen.getByText("课本第 8 页")).toBeInTheDocument();
    expect(screen.getByText(/目前展示 1 个单元/)).toBeInTheDocument();
    expect(screen.getByText(/请家长在 App/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始上课" })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
    expect(fetch.mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
  });

  it("re-reads changed parent selection on refresh", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply(catalog())).mockResolvedValueOnce(reply(detail()))
      .mockResolvedValueOnce(reply(catalog(true))).mockResolvedValueOnce(reply(detail(true)));
    vi.stubGlobal("fetch", fetch);
    render(<LearningTextbooks student={student} />);
    await screen.findByText(/请家长在 App/);
    fireEvent.click(screen.getByRole("button", { name: "刷新教材" }));
    expect(await screen.findByText("家长已确认")).toBeInTheDocument();
    await screen.findByRole("heading", { name: "1 天地人" });
    expect(screen.queryByText(/请家长在 App/)).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("labels an indexed edition without inventing lessons or reporting a completed directory", async () => {
    const indexed = { ...book, schoolSystem: "five_four", coverage: { status: "index_only", note: "目录待核验" }, unitCount: 0, lessonCount: 0 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply({ ...catalog(), books: [{ ...catalog().books[0], ...indexed }] }))
      .mockResolvedValueOnce(reply({ ...detail(), book: indexed, units: [] })));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByText("教材版本已收录，单元和课次目录正在核对。")).toBeInTheDocument();
    expect(screen.getByText("语文 · 上册 · 五四制")).toBeInTheDocument();
    expect(screen.queryByText(/目前展示/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始上课" })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("handles unavailable grades and retries failure without invented courses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply({ message: "服务暂时不可用" }, 503))
      .mockResolvedValueOnce(reply({ ...catalog(), books: [] })));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("服务暂时不可用");
    fireEvent.click(screen.getByRole("button", { name: "再试一次" }));
    expect(await screen.findByText("这个年级的教材正在准备")).toBeInTheDocument();
  });

  it("rejects content for another edition instead of showing its lessons", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(catalog()))
      .mockResolvedValueOnce(reply({ ...detail(), book: { ...book, editionId: "other" } })));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("教材资料已更新");
    expect(screen.queryByRole("heading", { name: "1 天地人" })).not.toBeInTheDocument();
  });

  it("requires both ready status and a parent selection for playable contracts", () => {
    const data = detail();
    const lesson = { ...data.units[0].lessons[0], status: "ready", course: { courseId: "fixed", courseVersion: "1", contentKey: "a".repeat(64) } };
    const units = [{ ...data.units[0], lessons: [lesson] }];
    expect(textbookContentsSchema.safeParse({ ...data, units }).success).toBe(false);
    expect(textbookContentsSchema.safeParse({ ...data, selected: true, units }).success).toBe(true);
    expect(textbookContentsSchema.safeParse({ ...data, selected: true, units: [{ ...units[0], lessons: [{ ...lesson, course: null }] }] }).success).toBe(false);
  });

  it("sends expired students to unlock", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({ error: "student_session_required" }, 401)));
    render(<LearningTextbooks student={student} />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/unlock"));
  });
});
