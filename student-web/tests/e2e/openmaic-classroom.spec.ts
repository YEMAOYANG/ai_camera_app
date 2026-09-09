import { expect, test, type Page } from "@playwright/test";

import { formalRuntimeLaunchFixture } from "../../src/test/fixtures/openmaic-runtime";

const runtimeOrigin = (process.env.OPENMAIC_FULL_RUNTIME_PUBLIC_URL || "http://127.0.0.1:3101")
  .replace(/\/$/, "");

async function mockStudentAndLesson(page: Page) {
  await page.route("**/api/auth/me", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        student: {
          id: "student-e2e",
          childId: "child-e2e",
          displayName: "乐乐",
          gradeCode: "primary_1",
        },
        device: { id: "device-e2e", label: "课堂测试设备" },
      }),
    });
  });
  await page.route("**/api/learning/sessions", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        resumed: false,
        session: {
          id: "session-e2e",
          taskId: "task-e2e",
          courseId: "course-sample-math",
          courseVersion: "1",
          status: "in_progress",
          currentQuestionIndex: 0,
          totalQuestions: 0,
          correctCount: 0,
          attemptedCount: 0,
          hintCount: 0,
          currentQuestion: null,
          startedAt: 1,
        },
        lesson: {
          courseId: "course-sample-math",
          version: "1",
          gradeCode: "primary_1",
          title: "20以内数感互动课堂",
          subject: "math",
          subjectLabel: "数学",
          objective: "比较20以内数的大小并理解数的组成与顺序",
          intro: "",
          estimatedMinutes: 10,
          questionCount: 0,
          sessionKind: "lesson",
          outcomeMode: "scored_deterministic",
        },
      }),
    });
  });
}

test("trusted OpenMAIC route keeps branded navigation and delegates microphone only to its runtime", async ({ page }) => {
  await mockStudentAndLesson(page);
  await page.route("**/api/learning/sessions/session-e2e/openmaic-launch", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...formalRuntimeLaunchFixture,
        launchUrl: `${runtimeOrigin}/mira/launch?ticket=e2e-one-time-ticket`,
        expiresAt: Date.now() + 60_000,
      }),
    });
  });
  await page.route(`${runtimeOrigin}/**`, async (route) => {
    await route.fulfill({
      contentType: "text/html",
      body: "<!doctype html><html><body><main data-testid='official-runtime'>Official OpenMAIC classroom</main></body></html>",
    });
  });

  const response = await page.goto("/lesson/task-e2e/classroom");
  expect(response?.headers()["permissions-policy"]).toBe(
    `camera=(), microphone=(self "${runtimeOrigin}"), geolocation=()`,
  );

  const frame = page.getByTitle("20以内数感互动课堂完整互动课堂");
  await expect(frame).toHaveAttribute("allow", "microphone; autoplay; fullscreen");
  await expect(page.frameLocator("iframe").getByTestId("official-runtime")).toBeVisible();
  const toolbar = page.getByRole("navigation", { name: "课堂导航" });
  await expect(toolbar).toBeVisible();
  await expect(page.getByRole("link", { name: "返回课程列表" })).toHaveAttribute("href", "/learning");
  await expect(page.getByText("暖瞳课堂")).toBeVisible();
  await expect(page.locator(".full-openmaic-authority")).toHaveCount(0);

  const viewport = page.viewportSize();
  const toolbarBox = await toolbar.boundingBox();
  const box = await frame.boundingBox();
  expect(toolbarBox).not.toBeNull();
  expect(box).not.toBeNull();
  expect(box?.x).toBe(0);
  expect(box?.y).toBeCloseTo(toolbarBox?.height ?? 0, 0);
  expect(box?.width).toBe(viewport?.width);
  expect(box?.height).toBeCloseTo((viewport?.height ?? 0) - (toolbarBox?.height ?? 0), 0);

  await page.setViewportSize({ width: 375, height: 667 });
  const mobileBackBox = await page.getByRole("link", { name: "返回课程列表" }).boundingBox();
  const mobileToolbarBox = await toolbar.boundingBox();
  const mobileFrameBox = await frame.boundingBox();
  expect(mobileBackBox).not.toBeNull();
  expect(mobileToolbarBox).not.toBeNull();
  expect(mobileFrameBox).not.toBeNull();
  expect(mobileBackBox?.height).toBeGreaterThanOrEqual(48);
  expect((mobileBackBox?.x ?? -1) + (mobileBackBox?.width ?? 0)).toBeLessThanOrEqual(375);
  expect(mobileFrameBox?.y).toBeCloseTo(mobileToolbarBox?.height ?? 0, 0);
  expect(mobileFrameBox?.height).toBeCloseTo(667 - (mobileToolbarBox?.height ?? 0), 0);
});

test("runtime failure remains explicit and never mounts a Mira lesson fallback", async ({ page }) => {
  await mockStudentAndLesson(page);
  await page.route("**/api/learning/sessions/session-e2e/openmaic-launch", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        ok: false,
        error: "openmaic_runtime_provider_unavailable",
        message: "课堂语音服务尚未就绪，请稍后重新检查。",
      }),
    });
  });

  await page.goto("/lesson/task-e2e/classroom");
  await expect(page.getByRole("heading", { name: "完整互动课堂暂时打不开" })).toBeVisible();
  await expect(page.getByText("课堂语音服务尚未就绪，请稍后重新检查。")).toBeVisible();
  await expect(page.locator("iframe")).toHaveCount(0);
  await expect(page.locator(".classroom-page")).toHaveCount(0);
  await expect(page.getByText("今天要学会")).toHaveCount(0);
});
