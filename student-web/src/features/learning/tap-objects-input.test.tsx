import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { learningQuestionSchema } from "@/lib/contracts/learning";
import { TapObjectsInput } from "./tap-objects-input";

const objects = [{ id: "one", shape: "circle", color: "blue" }, { id: "two", shape: "square", color: "red" }] as const;
afterEach(cleanup);

describe("count concrete objects", () => {
  it("lets children count and undo each object without numeral input", () => {
    function Counting() {
      const [value, setValue] = useState<string[]>([]);
      return <TapObjectsInput objects={[...objects]} value={value} onChange={setValue} />;
    }
    render(<Counting />);
    const first = screen.getByRole("button", { name: "物体 1" });
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(first);
    expect(first).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("locks the input during authoritative feedback", () => {
    const change = vi.fn();
    render(<TapObjectsInput objects={[...objects]} value={[]} onChange={change} disabled />);
    fireEvent.click(screen.getByRole("button", { name: "物体 1" }));
    expect(change).not.toHaveBeenCalled();
  });

  it("allows only bounded shapes and strips private answer fields", () => {
    const payload = { id: "count", type: "tap_objects", prompt: "逐个点一点", objects: [...objects], answer: ["one", "two"] };
    expect(learningQuestionSchema.parse(payload)).not.toHaveProperty("answer");
    expect(learningQuestionSchema.safeParse({ ...payload, objects: [{ id: "x", shape: "script" }] }).success).toBe(false);
  });
});
