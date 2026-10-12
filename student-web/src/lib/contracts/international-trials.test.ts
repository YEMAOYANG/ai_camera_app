import { describe, expect, it } from "vitest";
import manifest from "../../../../backend/content/international_textbook_trials.v1.json";
import { internationalTrialsSchema } from "./international-trials";

const response = () => ({ ok: true, ...structuredClone(manifest), generation: { status: "blocked_source", canGenerate: false, publishedCourseKey: null } });

describe("international textbook source boundary", () => {
  it("keeps the requested mixed grades and uncertain English edition from the reviewed manifest", () => {
    const result = internationalTrialsSchema.parse(response());
    expect(result.textbooks.map(book => [book.subject, book.gradeCode, book.semester])).toEqual([
      ["chinese", "primary_5", "lower"], ["english", "primary_6", "upper"],
    ]);
    expect(result.textbooks[1].matchedTitle).toBeNull();
    expect(result.textbooks[1].candidates).toHaveLength(3);
    expect(result.generation.canGenerate).toBe(false);
  });

  it.each(["javascript:alert(1)", "http://example.com/", "https://user:password@example.com/", "https://example.com:444/"])("rejects an unsafe evidence link: %s", url => {
    const value = response();
    value.textbooks[0].evidence[0].url = url;
    expect(internationalTrialsSchema.safeParse(value).success).toBe(false);
  });

  it("rejects invented publication, altered grade identity, duplicate editions and private extras", () => {
    expect(internationalTrialsSchema.safeParse({ ...response(), generation: { status: "published", canGenerate: true, publishedCourseKey: "invented" } }).success).toBe(false);
    const wrongGrade = response();
    wrongGrade.textbooks[1].gradeCode = "primary_5";
    expect(internationalTrialsSchema.safeParse(wrongGrade).success).toBe(false);
    const duplicate = response();
    duplicate.textbooks = [duplicate.textbooks[0], duplicate.textbooks[0]];
    expect(internationalTrialsSchema.safeParse(duplicate).success).toBe(false);
    expect(internationalTrialsSchema.safeParse({ ...response(), providerKey: "private-value" }).success).toBe(false);
  });
});
