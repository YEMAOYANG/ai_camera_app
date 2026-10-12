import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import manifest from "../../../../backend/content/international_textbook_trials.v1.json";
import { LearningInternationalTrials } from "./learning-international-trials";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/components/student/schoolbag-shell", () => ({ SchoolbagShell: ({ children }: { children: ReactNode }) => <main>{children}</main> }));
const student = { id: "student-a", childId: "child-a", displayName: "小读者", gradeCode: "primary_1" };
const payload = { ok: true, ...manifest, generation: { status: "blocked_source", canGenerate: false, publishedCourseKey: null } };
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

beforeEach(() => vi.clearAllMocks());
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("international textbook test entry", () => {
  it("keeps both requested grades visible and distinguishes book metadata from unpublished courseware", async () => {
    let finish!: (value: Response) => void;
    const fetch = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
    vi.stubGlobal("fetch", fetch);
    render(<LearningInternationalTrials student={student} />);
    expect(screen.getByRole("status")).toHaveTextContent("正在核对教材与课件状态");
    finish(response(payload));
    expect(await screen.findByText("尚未生成课件。")).toBeVisible();
    expect(screen.getByText("五年级 · 下学期")).toBeVisible();
    expect(screen.getByText("六年级 · 上学期")).toBeVisible();
    const chinese = screen.getByRole("article", { name: manifest.textbooks[0].requestedTitle });
    const english = screen.getByRole("article", { name: manifest.textbooks[1].requestedTitle });
    expect(within(chinese).getByText("已核对官方书目")).toBeVisible();
    expect(within(english).getByText("版本待确认")).toBeVisible();
    expect(within(english).getByText("相关书目，尚未确定对应版本")).toBeVisible();
    for (const book of manifest.textbooks) {
      for (const material of book.requiredMaterials) expect(screen.getByText(material)).toBeVisible();
      for (const source of book.evidence) expect(screen.getByRole("link", { name: source.label })).toHaveAttribute("href", source.url);
    }
    expect(screen.getByRole("link", { name: "回到书包" })).toHaveAttribute("href", "/learning");
    expect(screen.queryByRole("button", { name: /生成|上传|开始学习/ })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledExactlyOnceWith("/api/learning/international-trials", expect.objectContaining({ cache: "no-store" }));
  });

  it("uses a safe retry state and displays an empty manifest without fabricating lessons", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(response({ message: "/private/source/token=secret" }, 502))
      .mockResolvedValueOnce(response({ ...payload, textbooks: [] }));
    vi.stubGlobal("fetch", fetch);
    render(<LearningInternationalTrials student={student} />);
    expect(await screen.findByRole("alert")).not.toHaveTextContent("secret");
    fireEvent.click(screen.getByRole("button", { name: "再试一次" }));
    expect(await screen.findByText("暂无待测试的教材")).toBeVisible();
    expect(screen.queryAllByRole("article")).toHaveLength(0);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("returns expired sessions to unlock without exposing the trial payload", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(payload, 401)));
    render(<LearningInternationalTrials student={student} />);
    await act(async () => {});
    expect(router.replace).toHaveBeenCalledWith("/unlock");
    expect(screen.queryAllByRole("article")).toHaveLength(0);
  });

  it("rejects an unsupported ready-to-generate claim instead of offering a course action", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...payload, generation: { status: "ready", canGenerate: true, publishedCourseKey: "invented" } })));
    render(<LearningInternationalTrials student={student} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("教材测试暂时没有加载成功");
    expect(screen.queryAllByRole("article")).toHaveLength(0);
  });
});
