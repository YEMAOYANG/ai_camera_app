import { afterEach, describe, expect, it, vi } from "vitest";

import { loadTextbookContents, preloadTextbookContents } from "./textbook-contents-client";

const student = { id: "student-a", gradeCode: "primary_1" };
const book = { editionId: "pep-chinese-g1", revisionId: "review-1" };
const contents = {
  ok: true,
  schemaVersion: "mira.learning.textbooks.v1",
  book: {
    ...book,
    title: "语文 一年级上册",
    publisher: "人民教育出版社",
    editionLabel: "测试目录",
    gradeCode: "primary_1",
    subject: "chinese",
    volume: "upper",
    schoolSystem: "six_year",
    coverage: { status: "complete", note: "" },
    sourceUrl: "https://basic.smartedu.cn/tchMaterial/detail?contentId=test",
    unitCount: 0,
    lessonCount: 0,
  },
  selected: true,
  selectionRevision: 1,
  currentNodeId: null,
  units: [],
};
const reply = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("textbook directory preload", () => {
  it("can retry after a preloaded request fails", async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(reply({ message: "暂时不可用" }, 503))
      .mockResolvedValueOnce(reply(contents));
    vi.stubGlobal("fetch", fetch);

    preloadTextbookContents(student, book);
    await expect(loadTextbookContents(student, book, new AbortController().signal)).rejects.toMatchObject({ status: 503 });
    preloadTextbookContents(student, book);
    await expect(loadTextbookContents(student, book, new AbortController().signal)).resolves.toMatchObject({ selected: true });
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("starts a fresh request after the preload expires", async () => {
    let now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(reply(contents)));
    vi.stubGlobal("fetch", fetch);

    preloadTextbookContents(student, book);
    now += 15_001;
    await loadTextbookContents(student, book, new AbortController().signal);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["student", { ...student, id: "student-b" }, book],
    ["grade", { ...student, gradeCode: "primary_2" }, book],
    ["edition", student, { ...book, editionId: "other-edition" }],
    ["revision", student, { ...book, revisionId: "review-2" }],
  ])("does not share a preload across a different %s", async (_label, nextStudent, nextBook) => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(reply(contents)));
    vi.stubGlobal("fetch", fetch);

    preloadTextbookContents(student, book);
    await loadTextbookContents(nextStudent, nextBook, new AbortController().signal);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
