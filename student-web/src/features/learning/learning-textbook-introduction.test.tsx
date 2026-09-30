import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LearningTextbookIntroduction } from "./learning-textbook-introduction";
import { LearningTextbooks } from "./learning-textbooks";
import { textbookContentsSchema } from "@/lib/contracts/textbooks";

const { router } = vi.hoisted(() => ({ router: { replace: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/components/student/space-shell", () => ({
  SpaceShell: ({ children }: { children: ReactNode }) => <main>{children}</main>,
  SpacePageHeading: ({ title }: { title: string }) => <header><h1>{title}</h1></header>,
}));
vi.mock("@/components/student/space-course-art", () => ({ SpaceCourseArt: () => null }));
const manifest = JSON.parse(readFileSync(resolve(process.cwd(), "../backend/content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json"), "utf8"));
const pack = JSON.parse(readFileSync(resolve(process.cwd(), "../backend/content/textbooks/intro-media-v1/published.json"), "utf8"));
const withMedia = (value: { introductionId: string }) => ({ ...value, contentSha256: pack.guides[value.introductionId].sourceContentSha256, presentation: pack.guides[value.introductionId] });
const detail = textbookContentsSchema.parse({ ok: true, schemaVersion: "mira.learning.textbooks.v1", book: {
  ...manifest, sourceUrl: manifest.source.url, unitCount: 9, lessonCount: 45,
}, selected: true, selectionRevision: 1, currentNodeId: null, introduction: withMedia(manifest.introduction),
units: manifest.units.map((unit: { introduction: { introductionId: string }; lessons: object[] }) => ({
  ...unit, introduction: withMedia(unit.introduction), lessons: unit.lessons.map(lesson => ({ ...lesson, objectives: [], status: "reviewing", course: null })),
})) });
const student = { id: "test-student", childId: "test-child", displayName: "小读者", gradeCode: "primary_1" };
const reply = (value: unknown) => new Response(JSON.stringify(value));
let clips: RecordedAudio[];
let firstPlay: Promise<void> | undefined;
class RecordedAudio {
  src: string;
  paused = true;
  currentTime = 0;
  duration = 20;
  onplaying: (() => void) | null = null;
  onwaiting: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeupdate: (() => void) | null = null;
  constructor(src: string) { this.src = src; clips.push(this); }
  play = vi.fn(() => { this.paused = false; this.onplaying?.(); const result = firstPlay ?? Promise.resolve(); firstPlay = undefined; return result; });
  pause = vi.fn(() => { this.paused = true; });
  load = vi.fn();
  removeAttribute = vi.fn();
}
beforeEach(() => { clips = []; firstPlay = undefined; vi.stubGlobal("Audio", RecordedAudio); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("shared picture and audio textbook guides", () => {
  it("plays the pre-produced voice only on a gesture and supports pause, resume and progress", () => {
    const speech = { speak: vi.fn() }; vi.stubGlobal("speechSynthesis", speech);
    render(<LearningTextbookIntroduction student={student} contents={detail} introduction={detail.introduction!} />);
    expect(clips).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "点图听讲" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "听故事" })).toHaveLength(1);
    expect(screen.getByRole("img", { name: "挥挥手，交朋友" })).toBeVisible();
    expect(screen.getByText(/我是米拉老师/)).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "字幕" }));
    expect(screen.getByText(/我是米拉老师/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "字幕" }));
    expect(screen.getByText(/我是米拉老师/)).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "听故事" }));
    expect(clips[0].src).toBe(detail.introduction!.presentation!.scenes[0].audio.src);
    act(() => { clips[0].currentTime = 8; clips[0].ontimeupdate?.(); });
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    expect(clips[0].paused).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "继续听" }));
    expect(clips).toHaveLength(1);
    expect(clips[0].currentTime).toBe(8);
    expect(speech.speak).not.toHaveBeenCalled();
  });

  it("chooses pictures, hears their feedback and returns to the exact unit without generation or grading", () => {
    const fetch = vi.fn(); vi.stubGlobal("fetch", fetch);
    const unit = detail.units[1];
    const { unmount } = render(<LearningTextbookIntroduction student={student} contents={detail} introduction={unit.introduction!} unitId={unit.unitId} />);
    fireEvent.click(screen.getByRole("button", { name: "下一幅" }));
    fireEvent.click(screen.getByRole("button", { name: /看天空/ }));
    expect(clips.at(-1)!.src).toBe(unit.introduction!.presentation!.choices[0].audio.src);
    fireEvent.click(screen.getByRole("button", { name: /找自己/ }));
    expect(clips.at(-2)!.paused).toBe(true);
    expect(clips.at(-1)!.src).toBe(unit.introduction!.presentation!.choices[1].audio.src);
    fireEvent.click(screen.getByRole("button", { name: "上一幅" }));
    fireEvent.click(screen.getByRole("button", { name: "下一幅" }));
    expect(screen.getByRole("button", { name: /找自己/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "下一幅" }));
    fireEvent.click(screen.getByRole("button", { name: "我来试一试" }));
    expect(screen.getByRole("button", { name: "我试过啦" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "下一幅" }));
    fireEvent.click(screen.getByRole("button", { name: "准备好啦" }));
    expect(screen.getByRole("link", { name: /去看教材/ })).toHaveAttribute("href", expect.stringContaining("unitId=unit-1-literacy"));
    expect(screen.queryByText(/已掌握|已通关|100分/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "再玩一次" }));
    unmount();
    expect(clips.every(clip => clip.paused)).toBe(true);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("ignores late audio failures after a scene switch or a pause", async () => {
    let reject!: (error: Error) => void;
    firstPlay = new Promise<void>((_, fail) => { reject = fail; });
    render(<LearningTextbookIntroduction student={student} contents={detail} introduction={detail.introduction!} />);
    fireEvent.click(screen.getByRole("button", { name: "听故事" }));
    const oldEnd = clips[0].onended;
    fireEvent.click(screen.getByRole("button", { name: "下一幅" }));
    await act(async () => { reject(new Error("old aborted request")); oldEnd?.(); });
    expect(screen.getByRole("button", { name: "暂停" })).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    firstPlay = new Promise<void>((_, fail) => { reject = fail; });
    fireEvent.click(screen.getByRole("button", { name: "下一幅" }));
    fireEvent.click(screen.getByRole("button", { name: "暂停" }));
    await act(async () => { reject(new Error("pause abort")); });
    expect(screen.getByRole("button", { name: "继续听" })).toBeVisible();
  });

  it("retries the same saved audio on an error without a device-voice fallback", () => {
    render(<LearningTextbookIntroduction student={student} contents={detail} introduction={detail.introduction!} />);
    fireEvent.click(screen.getByRole("button", { name: "听故事" }));
    act(() => clips[0].onerror?.());
    expect(screen.getByRole("status")).toHaveTextContent("声音暂时没连上");
    fireEvent.click(screen.getByRole("button", { name: "重试播放" }));
    expect(clips).toHaveLength(2);
    expect(clips[1].src).toBe(clips[0].src);
  });

  it("keeps unpublished media unavailable and rejects mismatched grades or source identities", () => {
    const intro = { ...detail.introduction!, presentation: undefined };
    render(<LearningTextbookIntroduction student={student} contents={detail} introduction={intro} />);
    expect(screen.getByText("图画和配音正在准备")).toBeVisible();
    expect(clips).toHaveLength(0);
    const wrongGrade = structuredClone(detail); wrongGrade.book.gradeCode = "primary_6";
    expect(textbookContentsSchema.safeParse(wrongGrade).success).toBe(false);
    const wrongSource = structuredClone(detail); wrongSource.introduction!.contentSha256 = "0".repeat(64);
    expect(textbookContentsSchema.safeParse(wrongSource).success).toBe(false);
    const foreignAudio = structuredClone(detail); foreignAudio.introduction!.presentation!.scenes[0].audio.src = "https://example.com/voice.mp3";
    expect(textbookContentsSchema.safeParse(foreignAudio).success).toBe(false);
  });

  it("displays all nine sections and switches units without generating or changing parent choices", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(reply({ ok: true, schemaVersion: "mira.learning.textbooks.v1", gradeCode: "primary_1", schoolYearStartYear: 2026, semester: "upper", books: [{ ...detail.book, selected: true, selectionRevision: 1, currentNodeId: null }] }))
      .mockResolvedValueOnce(reply(detail));
    vi.stubGlobal("fetch", fetch);
    render(<LearningTextbooks student={student} />);
    expect(await screen.findByRole("button", { name: "完整目录" })).toBeVisible();
    expect(screen.getByRole("region", { name: "走进这门学科" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "完整目录" }));
    expect(within(screen.getByRole("navigation", { name: "教材单元" })).getAllByRole("button")).toHaveLength(9);
    expect(await screen.findByRole("heading", { name: "我是中国人" })).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("navigation", { name: "教材单元" })).getByRole("button", { name: /第八单元/ }));
    expect(screen.getByRole("heading", { name: "语文园地八" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "故事里，藏着好问题" })).toBeVisible();
    expect(screen.getByRole("link", { name: "开始探索" })).toHaveAttribute("href", expect.stringContaining("/intro/story-questions"));
    expect(screen.getByText("9 个板块 · 45 个课次")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "图片学习" }));
    const pictures = within(screen.getByRole("region", { name: "图片选课" }));
    expect(pictures.getByRole("link")).toHaveAttribute("href", expect.stringContaining("/intro/story-questions"));
    fireEvent.click(screen.getByRole("button", { name: "换个单元" }));
    const pictureUnits = within(screen.getByRole("region", { name: "图片单元" }));
    expect(pictureUnits.getAllByRole("button", { pressed: false })).toHaveLength(8);
    expect(pictureUnits.getByRole("button", { name: /第八单元/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "回到课程" }));
    expect(screen.getByRole("heading", { name: "第八单元 · 阅读" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "开始上课" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
