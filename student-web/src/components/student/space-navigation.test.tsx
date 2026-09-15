import { cleanup, render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SpaceNavigation, SpaceNavigationProvider, usePersistentSpaceNavigation } from "./space-navigation";

const route = vi.hoisted(() => ({ pathname: "/today" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));
vi.mock("next/link", () => ({
  default: (props: AnchorHTMLAttributes<HTMLAnchorElement>) => <a {...props} />,
  useLinkStatus: () => ({ pending: false }),
}));
vi.mock("@/components/student/space-atmosphere", () => ({
  SpaceMotionToggle: () => <button>背景动态</button>,
}));

function ProviderState() {
  return <span data-testid="provider-state">{String(usePersistentSpaceNavigation())}</span>;
}

describe("persistent student navigation", () => {
  afterEach(cleanup);

  it("retains the navigation, links and selection nodes across student page changes", () => {
    route.pathname = "/today";
    const view = render(<SpaceNavigationProvider><ProviderState /></SpaceNavigationProvider>);
    const navigation = screen.getByRole("navigation", { name: "学生导航" });
    const selection = navigation.querySelector(".space-rail-selection");
    const todayLink = screen.getByRole("link", { name: "今天" });
    expect(navigation.parentElement).toHaveClass("space-navigation-host");
    expect(view.container.firstElementChild).toBe(navigation.parentElement);
    expect(screen.getByTestId("provider-state")).toHaveTextContent("true");

    for (const [pathname, label, index] of [
      ["/learning", "课程", "1"],
      ["/learning/course-1", "课程", "1"],
      ["/learning/practice", "练习", "2"],
      ["/today", "今天", "0"],
    ]) {
      route.pathname = pathname;
      view.rerender(<SpaceNavigationProvider><ProviderState /></SpaceNavigationProvider>);
      expect(screen.getByRole("navigation", { name: "学生导航" })).toBe(navigation);
      expect(screen.getByRole("link", { name: "今天" })).toBe(todayLink);
      expect(navigation.querySelector(".space-rail-selection")).toBe(selection);
      expect(navigation.querySelectorAll(".space-rail-selection")).toHaveLength(1);
      expect(navigation.style.getPropertyValue("--space-nav-index")).toBe(index);
      expect(screen.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
      expect(navigation.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
    }
  });

  it("keeps auth, classroom and unrelated routes outside the navigation", () => {
    route.pathname = "/pair";
    const view = render(<SpaceNavigationProvider><ProviderState /></SpaceNavigationProvider>);
    for (const pathname of ["/pair", "/unlock", "/lesson/task-1/classroom", "/lesson/task-1", "/learning-other", "/today/extra"]) {
      route.pathname = pathname;
      view.rerender(<SpaceNavigationProvider><ProviderState /></SpaceNavigationProvider>);
      expect(screen.queryByRole("navigation", { name: "学生导航" })).not.toBeInTheDocument();
      expect(screen.getByTestId("provider-state")).toHaveTextContent("true");
    }
  });

  it("supports a standalone shell without claiming a persistent provider", () => {
    render(<><ProviderState /><SpaceNavigation active="learning" /></>);
    expect(screen.getByTestId("provider-state")).toHaveTextContent("false");
    expect(screen.getByRole("link", { name: "课程" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "练习" })).toHaveAttribute("href", "/learning/practice");
    expect(screen.getByRole("button", { name: "背景动态" })).toBeEnabled();
  });
});
