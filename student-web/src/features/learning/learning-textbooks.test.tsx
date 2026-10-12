import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LearningTextbooks } from "@/features/learning/learning-textbooks";
import { textbookContentsSchema } from "@/lib/contracts/textbooks";

const { router, startLearningCourse } = vi.hoisted(() => ({ router: { replace: vi.fn(), push: vi.fn() }, startLearningCourse: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/learning/learning-client", async importOriginal => ({ ...await importOriginal<typeof import("@/features/learning/learning-client")>(), startLearningCourse }));
vi.mock("@/components/student/space-shell", () => ({
  SpaceShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
  SpacePageHeading: ({ title, children }: { title: string; children: ReactNode }) => <header><h1>{title}</h1>{children}</header>,
}));
const student = { id: "student-a", childId: "child-a", displayName: "乐乐", gradeCode: "primary_1" };
const book = { editionId: "pep-chinese-g1", revisionId: "review-1", title: "语文 一年级上册", publisher: "人民教育出版社", editionLabel: "测试目录", gradeCode: "primary_1", subject: "chinese", volume: "upper", schoolSystem: "six_year", coverage: { status: "partial", note: "仅首单元" }, sourceUrl: "https://basic.smartedu.cn/tchMaterial/detail?contentId=test", unitCount: 1, lessonCount: 1 };
const catalog = (selected = true) => ({ ok: true, schemaVersion: "mira.learning.textbooks.v1", gradeCode: "primary_1", schoolYearStartYear: 2026, semester: "upper", books: [{ ...book, selected, selectionRevision: selected ? 1 : 0, currentNodeId: null }] });
const detail = (selected = true) => ({ ok: true, schemaVersion: "mira.learning.textbooks.v1", book, selected, selectionRevision: selected ? 1 : 0, currentNodeId: null, units: [{ unitId: "u1", title: "第一单元 · 识字", sequence: 1, lessons: [{ nodeId: "u1-l1", title: "1 天地人", sequence: 1, printedPage: 8, pdfPage: 13, objectives: [], status: "reviewing", course: null }] }] });
const reply = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

describe("school textbooks", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("opens an available edition through its original directory without changing the parent's school book", async () => {
    const other = { ...book, editionId: "other-chinese-g1", revisionId: "published-v1", volume: "lower" };
    const guide = { courseId: "guide", courseVersion: "1", contentKey: "a".repeat(64), delivery: "fixed_textbook", title: "看图找春天", nodeId: "guide-u1", kind: "unit_guide", assessmentMode: "ungraded" };
    const contents = { ...detail(false), book: other, accessMode: "published", units: [{ ...detail().units[0], guideCourse: guide }] };
    const fetch = vi.fn().mockResolvedValueOnce(reply({ ...catalog(), books: [...catalog().books, { ...other, selected: false, accessMode: "published", selectionRevision: 0, currentNodeId: null }] }))
      .mockResolvedValueOnce(reply(contents));
    vi.stubGlobal("fetch", fetch);
    render(<LearningTextbooks student={student} location={{ editionId: other.editionId, revisionId: other.revisionId }} />);
    expect(await screen.findByRole("link", { name: "看图找春天" })).toHaveAttribute("href", `/learning/textbooks/courses/${guide.contentKey}`);
    expect(textbookContentsSchema.safeParse(contents).success).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "查看其他教材版本与册次" }));
    expect(screen.getByRole("combobox", { name: "选择教材目录（请家长帮忙）" })).toBeVisible();
    expect(screen.queryByText("家长已确认")).not.toBeInTheDocument();
    expect(fetch.mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("opens released exploration and unit guide from the selected book without treating them as lesson mastery", async () => {
    const guide = { courseId: "guide", courseVersion: "1", contentKey: "a".repeat(64), delivery: "fixed_textbook", title: "看图找朋友", nodeId: "guide-u1", kind: "unit_guide", assessmentMode: "ungraded" };
    const exploration = { ...guide, contentKey: "b".repeat(64), nodeId: "explore-book", kind: "book_exploration" };
    const response = { ...detail(), explorationCourse: exploration, units: [{ ...detail().units[0], guideCourse: guide }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(catalog())).mockResolvedValueOnce(reply(response)));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("link", { name: "看图找朋友" })).toHaveAttribute("href", `/learning/textbooks/courses/${guide.contentKey}`);
    expect(screen.getByRole("link", { name: "先认识语文" })).toHaveAttribute("href", `/learning/textbooks/courses/${exploration.contentKey}`);
    fireEvent.click(screen.getByRole("button", { name: "完整目录" }));
    expect(screen.getByRole("link", { name: "开始探索" })).toHaveAttribute("href", `/learning/textbooks/courses/${guide.contentKey}`);
    expect(screen.queryByRole("link", { name: "开始上课" })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
    expect(textbookContentsSchema.safeParse({ ...response, selected: false }).success).toBe(false);
    expect(textbookContentsSchema.safeParse({ ...response, explorationCourse: guide }).success).toBe(false);
  });

  it("shows verified order/page and partial coverage without creating a course or choosing for parents", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply(catalog())).mockResolvedValueOnce(reply(detail()));
    vi.stubGlobal("fetch", fetch);
    render(<LearningTextbooks student={student} />);
    const welcome = await screen.findByRole("region", { name: "走进这门学科" });
    expect(within(welcome).getByRole("heading", { level: 1 })).toHaveTextContent(book.title);
    expect(welcome).toBeVisible();
    expect(screen.getByRole("button", { name: "图片学习" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("region", { name: "完整目录" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "完整目录" }));
    expect(screen.queryByRole("region", { name: "图片选课" })).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "1 天地人" })).toBeInTheDocument();
    expect(screen.getByText("课本第 8 页")).toBeInTheDocument();
    expect(screen.getByText(/目前展示 1 个单元/)).toBeInTheDocument();
    expect(screen.getByText("家长已确认")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "选择教材版本" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始上课" })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
    expect(fetch.mock.calls.every(([, options]) => !options?.method || options.method === "GET")).toBe(true);
  });

  it("re-reads changed parent selection on refresh", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply({ ...catalog(), books: [] }))
      .mockResolvedValueOnce(reply(catalog(true))).mockResolvedValueOnce(reply(detail(true)));
    vi.stubGlobal("fetch", fetch);
    render(<LearningTextbooks student={student} />);
    await screen.findByText("请家长帮你放入课本");
    fireEvent.click(screen.getByRole("button", { name: "刷新教材" }));
    fireEvent.click(await screen.findByRole("button", { name: "完整目录" }));
    expect(screen.getByText("家长已确认")).toBeInTheDocument();
    await screen.findByRole("heading", { name: "1 天地人" });
    expect(screen.queryByText(/请家长在 App/)).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("labels an indexed edition without inventing lessons or reporting a completed directory", async () => {
    const indexed = { ...book, schoolSystem: "five_four", coverage: { status: "index_only", note: "目录待核验" }, unitCount: 0, lessonCount: 0 };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply({ ...catalog(), books: [{ ...catalog().books[0], ...indexed }] }))
      .mockResolvedValueOnce(reply({ ...detail(), book: indexed, units: [] })));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByText("教材版本已确认，目录待补齐。")).toBeInTheDocument();
    expect(screen.queryByText(/五四制|六年制/)).not.toBeInTheDocument();
    expect(screen.queryByText(/目前展示/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "开始上课" })).not.toBeInTheDocument();
    expect(startLearningCourse).not.toHaveBeenCalled();
  });

  it("pages large units and keeps picture selection and the complete directory in sync", async () => {
    const readyLesson = (index: number, unit = "u1") => ({ ...detail().units[0].lessons[0], nodeId: `${unit}-l${index}`, title: `${unit} 课程 ${index}`, sequence: index,
      status: "ready", course: { courseId: `${unit}-course-${index}`, courseVersion: "1", contentKey: index.toString(16).padStart(64, "0"), delivery: "fixed_textbook" } });
    const contents = { ...detail(), book: { ...book, unitCount: 2, lessonCount: 10 }, units: [
      { ...detail().units[0], lessons: Array.from({ length: 8 }, (_, index) => readyLesson(index + 1)) },
      { unitId: "u2", title: "第二单元 · 拼音", sequence: 2, lessons: [readyLesson(9, "u2"), { ...detail().units[0].lessons[0], nodeId: "u2-pending", title: "还在准备的课程" }] },
    ] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(catalog())).mockResolvedValueOnce(reply(contents)));
    render(<LearningTextbooks student={student} />);
    const pictures = within(await screen.findByRole("region", { name: "图片选课" }));
    expect(pictures.getAllByRole("link", { name: /开始上课/ })).toHaveLength(6);
    expect(pictures.queryByRole("link", { name: "开始上课，u1 课程 7" })).not.toBeInTheDocument();
    fireEvent.click(pictures.getByRole("button", { name: "下一组" }));
    expect(pictures.getAllByRole("link", { name: /开始上课/ })).toHaveLength(2);
    expect(pictures.getByRole("link", { name: "开始上课，u1 课程 8" })).toHaveAttribute("href", `/learning/textbooks/courses/${"8".padStart(64, "0")}`);
    expect(pictures.getByRole("button", { name: "下一组" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "完整目录" }));
    expect(screen.queryByRole("region", { name: "图片选课" })).not.toBeInTheDocument();
    const directoryUnits = within(screen.getByRole("navigation", { name: "教材单元" }));
    fireEvent.click(directoryUnits.getByRole("button", { name: /第二单元/ }));
    expect(screen.getByRole("heading", { name: "还在准备的课程" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "图片学习" }));
    const second = within(screen.getByRole("region", { name: "图片选课" }));
    expect(second.getAllByRole("link", { name: /开始上课/ })).toHaveLength(1);
    expect(second.getByRole("link", { name: "开始上课，u2 课程 9" })).toBeVisible();
    expect(second.queryByText(/u1 课程/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "换个单元" }));
    expect(screen.queryByRole("region", { name: "图片选课" })).not.toBeInTheDocument();
    const pictureUnits = within(screen.getByRole("region", { name: "图片单元" }));
    expect(pictureUnits.getByRole("button", { name: /第二单元/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(pictureUnits.getByRole("button", { name: /第一单元/ }));
    const first = within(screen.getByRole("region", { name: "图片选课" }));
    expect(first.getAllByRole("link", { name: /开始上课/ })).toHaveLength(6);
    expect(first.getByRole("button", { name: "上一组" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "完整目录" }));
    expect(within(screen.getByRole("navigation", { name: "教材单元" })).getByRole("button", { name: /第一单元/ })).toHaveAttribute("aria-current", "true");
  });

  it.each([null, "u1-l1"])("opens a playable unit unless school progress already selects one (%s)", async currentNodeId => {
    const contents = { ...detail(), currentNodeId, book: { ...book, unitCount: 2, lessonCount: 2 }, units: [detail().units[0],
      { unitId: "u2", title: "第二单元", sequence: 2, lessons: [{ ...detail().units[0].lessons[0], nodeId: "u2-l1", status: "ready",
        course: { courseId: "playable", courseVersion: "1", contentKey: "b".repeat(64), delivery: "fixed_textbook" } }] },
    ] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(catalog())).mockResolvedValueOnce(reply(contents)));
    render(<LearningTextbooks student={student} />);
    fireEvent.click(await screen.findByRole("button", { name: "换个单元" }));
    const units = within(screen.getByRole("region", { name: "图片单元" }));
    expect(units.getByRole("button", { name: currentNodeId ? /第一单元/ : /第二单元/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("handles unavailable grades and retries failure without invented courses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply({ message: "服务暂时不可用" }, 503))
      .mockResolvedValueOnce(reply({ ...catalog(), books: [] })));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("服务暂时不可用");
    fireEvent.click(screen.getByRole("button", { name: "再试一次" }));
    expect(await screen.findByText("请家长帮你放入课本")).toBeInTheDocument();
  });

  it("rejects content for another edition instead of showing its lessons", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(reply(catalog()))
      .mockResolvedValueOnce(reply({ ...detail(), book: { ...book, editionId: "other" } })));
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("教材资料已更新");
    expect(screen.queryByRole("heading", { name: "1 天地人" })).not.toBeInTheDocument();
  });

  it("requires both ready status and a parent selection for playable contracts", () => {
    const data = detail(false);
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
