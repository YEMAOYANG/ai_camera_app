import { describe, expect, it } from "vitest";
import { NextResponse } from "next/server";
import { BackendApiError } from "./errors";
import { studentErrorCopy } from "./student-error-copy";
import { studentRouteError } from "./route-response";

describe("student-facing service error wording", () => {
  it.each([
    ["腾讯云批改结果未确认，不会重复提交", "作业检查结果未确认，不会重复提交"],
    ["Qwen3.5-Plus识别超时，无法确认是否计费", "老师识别超时，无法确认是否计费"],
    ["DeepSeek-v4.1-flash这次讲解的回执尚未确认", "老师这次讲解的回执尚未确认"],
    ["AI老师的声音暂时无法播放", "老师的声音暂时无法播放"],
    ["OpenMAIC课堂暂时没有准备好", "课堂暂时没有准备好"],
  ])("retains the concrete cause and receipt meaning in %s", (message, expected) => {
    expect(studentErrorCopy(message)).toBe(expected);
  });
  it("preserves error identity and unknown status in the API response", async () => {
    const response: NextResponse = studentRouteError(new BackendApiError(409, "homework_provider_unknown", "腾讯云处理结果未确认，原图已经保存"));
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ ok: false, error: "homework_provider_unknown", message: "作业检查处理结果未确认，原图已经保存" });
  });
  it("leaves an ordinary error unchanged", () => {
    expect(studentErrorCopy("原题已更新，请回到原作业重新打开")).toBe("原题已更新，请回到原作业重新打开");
  });
});
