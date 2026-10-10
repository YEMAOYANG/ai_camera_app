import { describe, expect, it } from "vitest";

import fixture from "@/test/fixtures/homework-service.json";
import { homeworkDetailSchema, homeworkImagePath, homeworkItemSchema, homeworkPageSchema } from "./homework";
import { homeworkTutorItemSchema } from "./homework-tutor";

const submissionId = fixture.studentDetail.submission.id;
const pageId = `hwp_${"a".repeat(32)}`;
const assetUrl = `/api/v2/student/learning/homework/${submissionId}/pages/${pageId}/image`;
const page = { id: pageId, order: 0, rotation: 0, crop: null, width: 1280, height: 1920, status: "recognized", error: null, assetUrl };

describe("student homework original-photo contract", () => {
  it("keeps saved submissions without photo context compatible", () => {
    const submission = { ...fixture.studentDetail.submission };
    const withoutPages: Record<string, unknown> = { ...submission };
    delete withoutPages.pages;
    expect(homeworkDetailSchema.parse({ ok: true, submission: withoutPages }).submission.pages).toEqual([]);
    expect(homeworkDetailSchema.parse(fixture.studentDetail).submission.items[0].reviewContext).toBeUndefined();
  });

  it("preserves private page and normalized wrong-answer context without grading keys", () => {
    const context = { pageId, region: { x: 0.1, y: 0.2, width: 0.5, height: 0.2 }, originalAnswer: "4", originalOrdinal: 3, expectedAnswer: "5" };
    const payload = { ok: true, submission: { ...fixture.studentDetail.submission, pages: [{ ...page, storageKey: "private/file" }], items: [{ ...fixture.studentDetail.submission.items[0], reviewContext: context }] } };
    const parsed = homeworkDetailSchema.parse(payload);
    expect(parsed.submission.pages[0]).toEqual(page);
    expect(parsed.submission.items[0].reviewContext).toEqual({ pageId, region: context.region, originalAnswer: "4", originalOrdinal: 3 });
    expect(parsed.submission.items[0]).not.toHaveProperty("expectedAnswer");
  });

  it("allows missing handwriting and absent exact location", () => {
    const item = homeworkItemSchema.parse({ ...fixture.studentDetail.submission.items[0], reviewContext: { pageId, region: null, originalOrdinal: 1 } });
    expect(item.reviewContext?.region).toBeNull();
    expect(item.reviewContext?.originalAnswer).toBeUndefined();
  });

  it("preserves printed subquestion identity and source uncertainty for both practice and AI tutor views", () => {
    const context = { pageId, region: null, originalOrdinal: 8, sourceQuestionLabel: "5（1）", originalAnswer: "4 - □ = 3", answerState: "blank", recognitionNeedsConfirmation: true, recognitionConfirmed: false };
    expect(homeworkItemSchema.parse({ ...fixture.studentDetail.submission.items[0], reviewContext: context }).reviewContext).toEqual(context);
    expect(homeworkTutorItemSchema.parse({ id: fixture.studentDetail.submission.items[0].id, revision: 1, prompt: "看图填算式", status: "pending", tutorAvailable: true, reviewContext: context }).reviewContext).toEqual(context);
    expect(homeworkItemSchema.safeParse({ ...fixture.studentDetail.submission.items[0], reviewContext: { ...context, answerState: "guessed" } }).success).toBe(false);
  });

  it.each([
    { x: -0.1, y: 0, width: 0.2, height: 0.3 },
    { x: 0.9, y: 0, width: 0.2, height: 0.3 },
    { x: 0, y: 0.9, width: 0.2, height: 0.3 },
    { x: 0, y: 0, width: 0, height: 0.3 },
    { x: 0, y: 0, width: 0.2, height: 4 },
  ])("rejects photo regions outside the normalized image: %o", (crop) => {
    expect(homeworkPageSchema.safeParse({ ...page, crop }).success).toBe(false);
    expect(homeworkItemSchema.safeParse({ ...fixture.studentDetail.submission.items[0], reviewContext: { pageId, region: crop, originalOrdinal: 1 } }).success).toBe(false);
  });

  it("accepts only the exact current submission/page backend path", () => {
    expect(homeworkImagePath(assetUrl, submissionId, pageId)).toBe(`/api/learning/homework/${submissionId}/pages/${pageId}/image`);
  });

  it.each([
    undefined,
    `${assetUrl}?childId=other`,
    `${assetUrl}/`,
    `${assetUrl}#target`,
    `https://example.test${assetUrl}`,
    assetUrl.replace(submissionId, `hw_${"b".repeat(32)}`),
    assetUrl.replace(pageId, `hwp_${"b".repeat(32)}`),
    assetUrl.replace("/api/v2/student/", "/api/"),
    assetUrl.replace("/image", "/image/../image"),
  ])("rejects untrusted photo URL %s", (url) => {
    expect(homeworkImagePath(url, submissionId, pageId)).toBeNull();
  });

  it("rejects invalid identifiers even when the URL matches them", () => {
    expect(homeworkImagePath(`/api/v2/student/learning/homework/other/pages/${pageId}/image`, "other", pageId)).toBeNull();
    expect(homeworkImagePath(`/api/v2/student/learning/homework/${submissionId}/pages/other/image`, submissionId, "other")).toBeNull();
  });
});
