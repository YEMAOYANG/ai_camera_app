import { describe, expect, it } from "vitest";

import { metadata } from "@/app/lesson/[taskId]/classroom/page";

describe("full classroom page metadata", () => {
  it("uses student-facing Mira branding", () => {
    expect(metadata.title).toBe("Mira 互动课堂");
    expect(JSON.stringify(metadata)).not.toMatch(/open\s*maic/i);
  });
});
