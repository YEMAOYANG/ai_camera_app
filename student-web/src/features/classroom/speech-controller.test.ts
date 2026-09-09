import { afterEach, describe, expect, it, vi } from "vitest";

import { createClassroomAudioController, learningAssetUrl } from "@/features/classroom/speech-controller";

describe("classroom audio controller", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("resolves only protected same-origin learning asset refs", () => {
    expect(learningAssetUrl("asset:standard-a")).toBe("/api/learning/assets/standard-a");
    expect(learningAssetUrl("https://example.com/a.mp3")).toBeNull();
    expect(learningAssetUrl("asset:../secret")).toBeNull();
  });

  it("plays package audio before any browser speech fallback", async () => {
    class FakeAudio extends EventTarget {
      src = "";
      preload = "";
      duration = 2;
      currentTime = 0;
      paused = true;
      play() {
        this.paused = false;
        queueMicrotask(() => {
          this.currentTime = 2;
          this.paused = true;
          this.dispatchEvent(new Event("ended"));
        });
        return Promise.resolve();
      }
      pause() { this.paused = true; }
      load() { /* media reset */ }
      removeAttribute() { this.src = ""; }
    }
    vi.stubGlobal("Audio", FakeAudio);
    const sources: string[] = [];
    const result = await createClassroomAudioController().playNarration({
      text: "标准发音",
      audioAssetRef: "asset:standard-a",
      allowBrowserFallback: false,
      onSource: (source) => sources.push(source),
    }, new AbortController().signal);
    expect(result).toEqual({ played: true, source: "package_audio" });
    expect(sources).toEqual(["package_audio"]);
  });
});
