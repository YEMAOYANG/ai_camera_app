import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TeacherPicker } from "./teacher-picker";
import { learningTeacherProfiles, teacherForSubject, teacherStyleDescription } from "./teacher-registry";
import { getLearningTeachers, setLearningTeacher } from "./learning-client";

vi.mock("./learning-client", () => ({ getLearningTeachers: vi.fn(), setLearningTeacher: vi.fn() }));

beforeEach(() => {
  vi.mocked(getLearningTeachers).mockImplementation(async (subject) => ({
    ok: true, registryVersion: "mira.teacher-registry.v3",
    items: learningTeacherProfiles.filter((p) => !subject || p.subject === subject), selected: null,
  }));
  vi.mocked(setLearningTeacher).mockClear();
});

describe("formal teacher library", () => {
  it("selects science explicitly and saves the existing version rather than a browser preference", async () => {
    const teacher = teacherForSubject(null, "science");
    vi.mocked(setLearningTeacher).mockResolvedValue({ ok: true, subject: "science", childId: "child",
      teacher, updatedAt: 1 });
    render(<TeacherPicker />);
    fireEvent.click(screen.getByRole("button", { name: "科学" }));
    const choice = await screen.findByRole("radio", { name: /小科老师/ });
    expect(screen.getByAltText("小科老师头像")).toHaveAttribute("src", expect.stringContaining("ke-science-v1.png"));
    fireEvent.click(choice);
    await waitFor(() => expect(setLearningTeacher).toHaveBeenCalledWith("science", "mira_science_inquiry", 1));
    await waitFor(() => expect(choice).toHaveAttribute("aria-checked", "true"));
  });

  it("provides four distinct portraits while unknown selected IDs retain subject matching", () => {
    expect(learningTeacherProfiles.map((p) => p.version)).toEqual([2, 2, 2, 1]);
    expect(new Set(learningTeacherProfiles.map((p) => p.avatarPath)).size).toBe(4);
    expect(teacherForSubject("mira_chinese_gentle", "science").id).toBe("mira_science_inquiry");
    expect(teacherStyleDescription(teacherForSubject(null, "science"))).toContain("观察");
  });
});
