import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TextbooksPage from "./page";

vi.mock("next/navigation", () => ({ redirect: (path: string) => { throw new Error(`redirect:${path}`); } }));
vi.mock("@/features/auth/student-session-gate", () => ({ StudentSessionGate: ({ textbookLocation }: { textbookLocation: unknown }) => <div data-testid="location">{JSON.stringify(textbookLocation)}</div> }));
afterEach(cleanup);

describe("textbook directory route", () => {
  it.each([{}, { subject: "chinese" }, { editionId: "book-1", revisionId: "review-1" }])("keeps list and exact directory URLs reachable: %j", async query => {
    render(await TextbooksPage({ searchParams: Promise.resolve(query) }));
    expect(JSON.parse(screen.getByTestId("location").textContent!)).toEqual(query);
  });
  it.each([{ editionId: "book-1" }, { revisionId: "review-1" }, { editionId: "../bad", revisionId: "review-1" }, { subject: "unknown" }, { subject: ["chinese", "math"] }])("rejects invalid or partial directory identifiers: %j", async query => {
    await expect(TextbooksPage({ searchParams: Promise.resolve(query) })).rejects.toThrow("redirect:/learning");
  });
});
