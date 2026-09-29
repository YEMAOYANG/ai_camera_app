import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LearningSchoolbag } from "./learning-schoolbag";

const { router } = vi.hoisted(() => ({ router: { push: vi.fn(), replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/components/student/schoolbag-shell", () => ({ SchoolbagShell: ({ children, tools }: { children: ReactNode; tools?: ReactNode }) => <><header>{tools}</header><main>{children}</main></> }));
const student = { id: "student-a", childId: "child-a", displayName: "小读者", gradeCode: "primary_1" };
const book = { editionId: "pep-chinese-g1", revisionId: "review-1", title: "语文 一年级上册", publisher: "人民教育出版社", editionLabel: "测试目录", gradeCode: "primary_1", subject: "chinese", volume: "upper", schoolSystem: "six_year", coverage: { status: "complete", note: "" }, sourceUrl: "https://basic.smartedu.cn/tchMaterial/detail?contentId=test", unitCount: 1, lessonCount: 1, selected: true, selectionRevision: 1, currentNodeId: null };
const catalog = { ok: true, schemaVersion: "mira.learning.textbooks.v1", gradeCode: "primary_1", schoolYearStartYear: 2026, semester: "upper", books: [book], subjects: [{ subject: "chinese", status: "confirmed" }, { subject: "math", status: "unavailable" }, { subject: "english", status: "unavailable" }] };
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
beforeEach(() => { vi.clearAllMocks(); window.localStorage.clear(); vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false }))); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("shared textbook schoolbag", () => {
  it("surfaces a due review from server evidence with the real classroom entry", async () => {
    const journey = { contentKey: "a".repeat(64), title: "天地人", status: "session_passed",
      parentNeeded: false, nextStep: "打开课堂", independentBefore: 4, verifiedCount: 6,
      remainingSkills: [], reviewDueAt: Date.now() - 1000, reviewDue: true, reviewLevel: 0,
      diagnoses: [], skippedCount: 4, updatedAt: Date.now() };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...catalog, learningJourneys: [journey] })));
    render(<LearningSchoolbag student={student} />);
    expect(await screen.findByText("到短复习时间啦")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "开始短复习" })).toHaveAttribute("href", `/learning/textbooks/courses/${journey.contentKey}`);
  });

  it("adds science to the same confirmation gate and opens the selected science revision", async () => {
    const science = { ...book, subject: "science", editionId: "science-g1", title: "科学 一年级上册" };
    const fetch = vi.fn().mockResolvedValueOnce(response({ ...catalog, books: [], subjects: [{ subject: "science", status: "selection_required" }] }))
      .mockResolvedValueOnce(response({ ...catalog, books: [science], subjects: [{ subject: "science", status: "confirmed" }] }));
    vi.stubGlobal("fetch", fetch);
    render(<LearningSchoolbag student={student} />);
    fireEvent.click(await screen.findByRole("button", { name: "科学，等家长选书" }));
    expect(await screen.findByText("请家长帮你放入科学课本")).toBeInTheDocument();
    expect(router.push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "家长与设置" }));
    fireEvent.click(screen.getByRole("button", { name: "刷新书包" }));
    const link = await screen.findByRole("link", { name: "拿出科学课本" });
    fireEvent.click(link);
    expect(router.push).toHaveBeenCalledExactlyOnceWith("/learning/textbooks?editionId=science-g1&revisionId=review-1");
    expect(fetch.mock.calls.every(([, options]) => !options.method)).toBe(true);
  });
  it("opens only the parent's book when the 3D host is unavailable, without generating or writing", async () => {
    const fetch = vi.fn().mockResolvedValue(response(catalog)); vi.stubGlobal("fetch", fetch);
    render(<LearningSchoolbag student={student} />);
    const link = await screen.findByRole("link", { name: "拿出语文课本" });
    expect(link).toHaveAttribute("href", "/learning/textbooks?editionId=pep-chinese-g1&revisionId=review-1");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/六年制|五四制/)).not.toBeInTheDocument();
    fireEvent.click(link);
    expect(router.push).toHaveBeenCalledTimes(1);
    expect(router.push).toHaveBeenCalledWith(link.getAttribute("href"));
    expect(fetch.mock.calls.every(([, options]) => !options.method)).toBe(true);
  });

  it("keeps math and English honest and explains their unavailable state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(catalog)));
    render(<LearningSchoolbag student={student} />);
    fireEvent.click(await screen.findByRole("button", { name: "数学，教材暂未收录" }));
    expect(await screen.findByText("数学教材暂未收录")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "英语，教材暂未收录" })).toBeEnabled();
    expect(router.push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "知道啦" }));
    expect(screen.queryByText("数学教材暂未收录")).not.toBeInTheDocument();
  });

  it("refreshes after a parent's confirmation and never exposes unselected editions", async () => {
    const unselected = { ...catalog, books: [{ ...book, selected: false }], subjects: [{ subject: "chinese", status: "selection_required" }] };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response(unselected)).mockResolvedValueOnce(response(catalog)));
    render(<LearningSchoolbag student={student} />);
    fireEvent.click(await screen.findByRole("button", { name: "语文，等家长选书" }));
    expect(await screen.findByText("请家长帮你放入语文课本")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "拿出语文课本" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "家长与设置" }));
    fireEvent.click(screen.getByRole("button", { name: "刷新书包" }));
    expect(await screen.findByRole("link", { name: "拿出语文课本" })).toBeInTheDocument();
  });

  it("uses the parent's semester after focus and keeps first-grade English selectable", async () => {
    const english = { ...book, editionId: "beijing-english-g1-upper-2022", title: "英语 一年级上册", publisher: "北京出版社", editionLabel: "北京版 · 一年级起点（2022 目录）", subject: "english", sourceUrl: "https://bph.com.cn/news/detail/2726.html", coverage: { status: "index_only", note: "目录核验" }, lessonCount: 0, unitCount: 0 };
    const fetch = vi.fn().mockResolvedValueOnce(response({ ...catalog, books: [english], subjects: [{ subject: "english", status: "confirmed" }] })).mockResolvedValueOnce(response({ ...catalog, semester: "lower", termSource: "parent", books: [], subjects: [{ subject: "english", status: "selection_required" }] }));
    vi.stubGlobal("fetch", fetch);
    render(<LearningSchoolbag student={student} />);
    expect(await screen.findByRole("link", { name: "拿出英语课本" })).toBeInTheDocument();
    fireEvent(window, new Event("focus"));
    expect(await screen.findByRole("button", { name: "英语，等家长选书" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "拿出英语课本" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "家长与设置" }));
    expect(screen.getByText(/下学期/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls.every(([, options]) => !options.method)).toBe(true);
  });

  it.each(["system", "toggle"])("skips extraction with %s reduced motion", async mode => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(catalog)));
    if (mode === "system") vi.stubGlobal("matchMedia", () => ({ matches: true }));
    render(<LearningSchoolbag student={student} />);
    const link = await screen.findByRole("link", { name: "拿出语文课本" });
    if (mode === "toggle") {
      fireEvent.click(screen.getByRole("button", { name: "家长与设置" }));
      const toggle = screen.getByRole("switch", { name: "拿书动效" });
      expect(toggle).toBeChecked();
      fireEvent.click(toggle);
      expect(toggle).not.toBeChecked();
    }
    fireEvent.click(link);
    expect(router.push).toHaveBeenCalledTimes(1);
    expect(link).not.toHaveClass("is-lifting");
  });

  it("preserves normal link behavior for opening a textbook in another tab", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(catalog)));
    render(<LearningSchoolbag student={student} />);
    const link = await screen.findByRole("link", { name: "拿出语文课本" });
    link.addEventListener("click", event => event.preventDefault(), { once: true });
    fireEvent.click(link, { metaKey: true });
    expect(router.push).not.toHaveBeenCalled();
  });

  it("shows retry on read errors and sends expired students to unlock", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(response({ message: "连接暂时断开" }, 503)).mockResolvedValueOnce(response({}, 401)));
    render(<LearningSchoolbag student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("连接暂时断开");
    fireEvent.click(screen.getByRole("button", { name: "再试一次" }));
    await act(async () => {});
    expect(router.replace).toHaveBeenCalledWith("/unlock");
  });
});
