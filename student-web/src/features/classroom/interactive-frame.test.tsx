import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InteractiveFrame } from "@/features/classroom/interactive-frame";
import { miraWidgetProtocol } from "@/features/classroom/interactive-protocol";

describe("InteractiveFrame sandbox", () => {
  it("uses a network-free unique-origin sandbox and validates source, protocol and scene", () => {
    const onMessage = vi.fn();
    render(<InteractiveFrame sceneId="scene-game" title="拖拽实验" templateId="match_pairs.v1" onMessage={onMessage} />);
    const iframe = screen.getByTitle("拖拽实验") as HTMLIFrameElement;
    expect(iframe.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe.getAttribute("sandbox")).not.toContain("allow-same-origin");
    expect(iframe.srcdoc).toContain("connect-src 'none'");
    expect(iframe.srcdoc).toContain("object-src 'none'");
    expect(iframe.srcdoc).toContain("[hidden]{display:none!important}");

    act(() => window.dispatchEvent(new MessageEvent("message", {
      source: window,
      data: { protocol: miraWidgetProtocol, sceneId: "scene-game", kind: "complete", payload: { completed: true } },
    })));
    act(() => window.dispatchEvent(new MessageEvent("message", {
      source: iframe.contentWindow,
      data: { protocol: miraWidgetProtocol, sceneId: "wrong-scene", kind: "complete", payload: { completed: true } },
    })));
    expect(onMessage).not.toHaveBeenCalled();

    act(() => window.dispatchEvent(new MessageEvent("message", {
      source: iframe.contentWindow,
      data: { protocol: miraWidgetProtocol, sceneId: "scene-game", kind: "complete", payload: { completed: true } },
    })));
    expect(onMessage).toHaveBeenCalledTimes(1);
  });
});
