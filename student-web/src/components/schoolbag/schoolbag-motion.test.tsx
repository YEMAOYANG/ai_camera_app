import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SchoolbagMotionProvider, SchoolbagStage, useSchoolbagMotion, useSchoolbagBook } from "./schoolbag-motion";
import { UnlockForm } from "@/features/auth/unlock-form";
import type { SchoolSubject } from "./motion-timeline";

const state = vi.hoisted(() => ({
  path: "/unlock", fail: () => {},
  router: { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() },
  engine: { setPose: vi.fn(), frame: vi.fn(), hover: vi.fn(), pick: vi.fn(), dispose: vi.fn() },
  create: vi.fn(),
}));
vi.mock("next/navigation", () => ({ usePathname: () => state.path, useRouter: () => state.router }));
vi.mock("./schoolbag-renderer", () => ({ createSchoolbagRenderer: state.create }));

function Actions({ home = false }: { home?: boolean }) {
  const motion = useSchoolbagMotion();
  return <main id="main-content"><h1>{home ? "我的书包" : "解锁"}</h1>
    <SchoolbagStage pose={home ? "ready" : "closed"} label="书包" />
    <button onClick={() => motion.enterLearning()}>已通过认证</button>
    <button onClick={() => motion.openBook("chinese", "/learning/textbooks?editionId=confirmed&revisionId=immutable")}>取出语文</button>
    <UnlockForm />
  </main>;
}
function Harness({ home = false }: { home?: boolean }) { return <SchoolbagMotionProvider><Actions home={home} /></SchoolbagMotionProvider>; }
function DirectDirectory({ subject = "math" }: { subject?: SchoolSubject }) {
  useSchoolbagBook(subject);
  const { returnHome } = useSchoolbagMotion();
  return <main id="main-content"><h1>数学课本</h1><button onClick={returnHome}>回到书包</button></main>;
}
async function boot(home = false) {
  const view = render(<Harness home={home} />);
  await act(async () => { await vi.dynamicImportSettled(); });
  expect(document.querySelector(".bag-scene-host")).toHaveAttribute("data-ready", "true");
  return view;
}

beforeEach(() => {
  vi.clearAllMocks(); state.path = "/unlock"; localStorage.clear();
  vi.useFakeTimers();
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => window.setTimeout(() => cb(performance.now()), 16));
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  state.create.mockImplementation(async (_canvas, fail) => { state.fail = fail; return state.engine; });
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("schoolbag navigation choreography", () => {
  it.each(["math", "science"] as const)("closes and returns %s after a direct directory load without an earlier homepage", async subject => {
    state.path = "/learning/textbooks";
    render(<SchoolbagMotionProvider><DirectDirectory subject={subject} /></SchoolbagMotionProvider>);
    await act(async () => { await vi.dynamicImportSettled(); });
    expect(state.create).toHaveBeenCalledOnce();
    expect(document.querySelector(".bag-scene-host")).toHaveStyle({ opacity: 0 });
    fireEvent.click(screen.getByText("回到书包"));
    act(() => vi.advanceTimersByTime(1500));
    expect(state.engine.frame).toHaveBeenCalledWith("return", expect.any(Number), subject);
    expect(state.router.push).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(650));
    expect(state.router.push).toHaveBeenCalledExactlyOnceWith("/learning");
  });

  it("keeps direct directory return usable when its prewarmed renderer fails", async () => {
    state.path = "/learning/textbooks";
    state.create.mockRejectedValueOnce(new Error("Graphics unavailable"));
    render(<SchoolbagMotionProvider><DirectDirectory /></SchoolbagMotionProvider>);
    await act(async () => { await vi.dynamicImportSettled(); });
    fireEvent.click(screen.getByText("回到书包"));
    expect(state.router.push).toHaveBeenCalledExactlyOnceWith("/learning");
    expect(screen.queryByRole("button", { name: /跳过动画/ })).not.toBeInTheDocument();
  });

  it("keeps the bag closed after a rejected PIN and animates only after the server accepts it", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ message: "PIN不正确" }), { status: 403 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetch); await boot();
    fireEvent.change(screen.getByLabelText("4位学习PIN"), { target: { value: "1111" } });
    await act(async () => fireEvent.submit(screen.getByLabelText("4位学习PIN").closest("form")!));
    expect(screen.getByText("PIN不正确")).toBeInTheDocument();
    expect(state.engine.frame).not.toHaveBeenCalled(); expect(state.router.replace).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("4位学习PIN"), { target: { value: "0924" } });
    await act(async () => fireEvent.submit(screen.getByLabelText("4位学习PIN").closest("form")!));
    act(() => vi.advanceTimersByTime(1800));
    expect(state.engine.frame).toHaveBeenCalledWith("pack", expect.any(Number), undefined);
    expect(state.router.replace).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(800));
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith("/learning");
    expect(state.router.refresh).toHaveBeenCalledOnce();
  });

  it("hands the same renderer to the homepage and releases the transition", async () => {
    const view = await boot(); fireEvent.click(screen.getByText("已通过认证"));
    act(() => vi.advanceTimersByTime(2500));
    state.path = "/learning"; view.rerender(<Harness home />);
    act(() => vi.advanceTimersByTime(500));
    expect(state.create).toHaveBeenCalledOnce();
    expect(state.engine.setPose).toHaveBeenLastCalledWith("ready");
    expect(screen.queryByRole("button", { name: /跳过动画/ })).not.toBeInTheDocument();
    expect(document.querySelector<HTMLElement>(".schoolbag-route")?.inert).toBe(false);
  });

  it("finishes a skipped extraction once and keeps the exact confirmed directory URL", async () => {
    state.path = "/learning"; await boot(true);
    fireEvent.click(screen.getByText("取出语文")); fireEvent.click(screen.getByText("取出语文"));
    act(() => vi.advanceTimersByTime(350));
    expect(state.router.push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /跳过动画/ }));
    act(() => vi.advanceTimersByTime(6000));
    expect(state.router.push).toHaveBeenCalledExactlyOnceWith("/learning/textbooks?editionId=confirmed&revisionId=immutable");
    expect(document.querySelector<HTMLElement>(".schoolbag-route")?.inert).toBe(false);
  });

  it("does not wait for animation with reduced motion", async () => {
    localStorage.setItem("mira.schoolbag.reduced-motion", "1"); await boot();
    fireEvent.click(screen.getByText("已通过认证"));
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith("/learning");
    expect(state.engine.frame).not.toHaveBeenCalled();
  });

  it("continues navigation after losing the graphics context", async () => {
    await boot(); fireEvent.click(screen.getByText("已通过认证"));
    act(() => { state.fail(); vi.advanceTimersByTime(6000); });
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith("/learning");
    expect(document.querySelector(".bag-scene-host")).toHaveAttribute("data-ready", "false");
  });

  it("routes immediately if the model or WebGL cannot initialize", async () => {
    state.create.mockRejectedValueOnce(new Error("WebGL unavailable"));
    render(<Harness />); await act(async () => { await vi.dynamicImportSettled(); });
    fireEvent.click(screen.getByText("已通过认证"));
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith("/learning");
    expect(screen.queryByRole("button", { name: /跳过动画/ })).not.toBeInTheDocument();
  });

  it("finishes safely when the tab is hidden instead of waiting for paused animation frames", async () => {
    await boot(); fireEvent.click(screen.getByText("已通过认证"));
    vi.spyOn(document, "hidden", "get").mockReturnValue(true);
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    act(() => vi.advanceTimersByTime(6000));
    expect(state.router.replace).toHaveBeenCalledExactlyOnceWith("/learning");
    expect(document.body.style.overflow).not.toBe("hidden");
  });

  it("does not replay a queued navigation after an unrelated route change", async () => {
    const view = await boot(); fireEvent.click(screen.getByText("已通过认证"));
    state.path = "/pair"; view.rerender(<Harness />);
    act(() => vi.advanceTimersByTime(6000));
    expect(state.router.replace).not.toHaveBeenCalled();
    expect(document.querySelector<HTMLElement>(".schoolbag-route")?.inert).toBe(false);
  });

  it("cancels delayed navigation and GPU work when the host unmounts", async () => {
    const view = await boot(); fireEvent.click(screen.getByText("已通过认证")); view.unmount();
    act(() => vi.advanceTimersByTime(6000));
    expect(state.router.replace).not.toHaveBeenCalled(); expect(state.engine.dispose).toHaveBeenCalledOnce();
  });
});
