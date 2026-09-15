import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SpaceAtmosphere } from "./space-atmosphere";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("keeps the student's pause choice when the system motion preference changes", () => {
  let reduced = false;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", () => ({
    get matches() { return reduced; },
    addEventListener: (_event: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_event: string, listener: () => void) => listeners.delete(listener),
  }));
  const view = render(<div className="space-shell"><SpaceAtmosphere scenic /></div>);
  const shell = view.container.firstElementChild!;
  expect(shell).toHaveAttribute("data-space-motion", "running");
  fireEvent.click(screen.getByRole("button", { name: "暂停背景动态" }));
  expect(shell).toHaveAttribute("data-space-motion", "paused");

  act(() => { reduced = true; listeners.forEach(listener => listener()); });
  expect(screen.getByRole("button", { name: "背景动态已按系统设置暂停" })).toBeDisabled();
  expect(shell).toHaveAttribute("data-space-motion", "reduced");
  act(() => { reduced = false; listeners.forEach(listener => listener()); });
  expect(shell).toHaveAttribute("data-space-motion", "paused");
  fireEvent.click(screen.getByRole("button", { name: "继续背景动态" }));
  expect(shell).toHaveAttribute("data-space-motion", "running");
  view.unmount();
  expect(listeners.size).toBe(0);
  expect(shell).not.toHaveAttribute("data-space-motion");
});

it("preserves pause when navigating from a course page into an auth or classroom shell", () => {
  const first = render(<div className="space-shell"><SpaceAtmosphere scenic={false} /></div>);
  fireEvent.click(screen.getByRole("button", { name: "暂停背景动态" }));
  first.unmount();
  const second = render(<main data-space-stage><SpaceAtmosphere scenic={false} variant="toolbar" /></main>);
  expect(second.container.firstElementChild).toHaveAttribute("data-space-motion", "paused");
  expect(screen.getByRole("button", { name: "继续背景动态" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "继续背景动态" }));
  expect(second.container.firstElementChild).toHaveAttribute("data-space-motion", "running");
});
