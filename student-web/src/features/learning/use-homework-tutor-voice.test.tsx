import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type HomeworkTutorVoiceTurn, useHomeworkTutorVoice } from "./use-homework-tutor-voice";

type FakePlayer = {
  play: ReturnType<typeof vi.fn<() => Promise<void>>>;
  pause: ReturnType<typeof vi.fn>;
  onended: (() => void) | null;
  onerror: (() => void) | null;
};
const old: HomeworkTutorVoiceTurn = { id: "old", requestKey: "old-key", audioPath: "/api/old/audio" };
const reply: HomeworkTutorVoiceTurn = { id: "new", requestKey: "current-key", audioPath: "/api/new/audio" };
const props = (turns: HomeworkTutorVoiceTurn[] = [old], scopeKey = "paper:item:1") => ({ scopeKey, turns });

describe("homework teacher voice follows the current child's question", () => {
  let players: FakePlayer[];
  let hidden: boolean;
  let playResult: () => Promise<void>;
  beforeEach(() => {
    players = []; hidden = false; playResult = () => Promise.resolve();
    vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
    vi.stubGlobal("Audio", vi.fn(function () {
      const player: FakePlayer = { play: vi.fn(() => playResult()), pause: vi.fn(), onended: null, onerror: null };
      players.push(player); return player;
    }));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("never plays cached turns on mount, refresh or remount", () => {
    const first = renderHook(useHomeworkTutorVoice, { initialProps: props([old, reply]) });
    first.rerender(props([{ ...old }, { ...reply }])); first.unmount();
    renderHook(useHomeworkTutorVoice, { initialProps: props([old, reply]) });
    expect(players).toHaveLength(0);
  });

  it("plays only the newly returned matching request key, once", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key"));
    rerender(props([old, { ...reply, requestKey: "unrelated-key" }]));
    expect(players).toHaveLength(0);
    rerender(props([old, reply]));
    await act(async () => {});
    expect(players).toHaveLength(1); expect(players[0].play).toHaveBeenCalledTimes(1);
    expect(result.current.playingTurnId).toBe(reply.id);
    rerender(props([old, { ...reply }]));
    act(() => players[0].onended?.());
    rerender(props([old, { ...reply }]));
    expect(players).toHaveLength(1); expect(result.current.playingTurnId).toBeNull();
  });

  it("waits for the matching audio to become ready, including a receipt found by GET", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key"));
    rerender(props([old, { ...reply, audioPath: null }]));
    expect(players).toHaveLength(0);
    rerender(props([old, reply])); await act(async () => {});
    expect(players[0].play).toHaveBeenCalledTimes(1);
  });

  it("does not arm an existing saved turn even if its request key matches", () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props([reply]) });
    act(() => result.current.arm("current-key")); rerender(props([{ ...reply }]));
    expect(players).toHaveLength(0);
  });

  it("cancels a pending automatic reply on hide and never catches up on focus", () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key"));
    act(() => { hidden = true; document.dispatchEvent(new Event("visibilitychange")); });
    rerender(props([old, reply]));
    act(() => { hidden = false; document.dispatchEvent(new Event("visibilitychange")); });
    rerender(props([old, { ...reply }]));
    expect(players).toHaveLength(0);
    act(() => result.current.arm("current-key")); rerender(props([old, reply]));
    expect(players).toHaveLength(0);
  });

  it("does not repeatedly retry NotAllowedError and keeps explicit manual playback available", async () => {
    playResult = () => Promise.reject(new DOMException("Needs a gesture", "NotAllowedError"));
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key")); rerender(props([old, reply])); await act(async () => {});
    expect(result.current.failedTurnId).toBe(reply.id); expect(result.current.playingTurnId).toBeNull();
    rerender(props([old, { ...reply }])); act(() => result.current.arm("current-key"));
    expect(players).toHaveLength(1);
    playResult = () => Promise.resolve();
    await act(async () => result.current.toggle(reply.id, reply.audioPath));
    expect(players).toHaveLength(2); expect(result.current.playingTurnId).toBe(reply.id); expect(result.current.failedTurnId).toBeNull();
  });

  it("stops immediately when the server withdraws the audio source", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props([old, reply]) });
    await act(async () => result.current.play(reply.id, reply.audioPath));
    rerender(props([old, { ...reply, audioPath: null }]));
    expect(players[0].pause).toHaveBeenCalledTimes(1); expect(result.current.playingTurnId).toBeNull();
    act(() => result.current.play(reply.id, reply.audioPath));
    expect(players).toHaveLength(1);
    rerender(props([old, reply])); expect(players).toHaveLength(1);
  });

  it("switches manual replies without overlap, pauses, resumes and replays from a new player", async () => {
    const { result } = renderHook(useHomeworkTutorVoice, { initialProps: props([old, reply]) });
    await act(async () => result.current.toggle(old.id, old.audioPath));
    await act(async () => result.current.toggle(reply.id, reply.audioPath));
    expect(players[0].pause).toHaveBeenCalledTimes(1); expect(result.current.playingTurnId).toBe(reply.id);
    act(() => result.current.toggle(reply.id, reply.audioPath));
    expect(players[1].pause).toHaveBeenCalledTimes(1); expect(result.current.playingTurnId).toBeNull();
    await act(async () => result.current.toggle(reply.id, reply.audioPath));
    expect(players).toHaveLength(2); expect(players[1].play).toHaveBeenCalledTimes(2);
    await act(async () => result.current.play(reply.id, reply.audioPath));
    expect(players[1].pause).toHaveBeenCalledTimes(2); expect(players).toHaveLength(3);
  });

  it("manual playback cancels a pending automatic reply", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key"));
    await act(async () => result.current.play(old.id, old.audioPath));
    rerender(props([old, reply]));
    expect(players).toHaveLength(1); expect(result.current.playingTurnId).toBe(old.id);
  });

  it("stop cancels pending playback for recording or a rejected send", () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key")); act(() => result.current.stop());
    rerender(props([old, reply])); expect(players).toHaveLength(0);
  });

  it("a new request stops current narration and cannot play a late reply to the earlier request", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props([old]) });
    await act(async () => result.current.play(old.id, old.audioPath));
    act(() => result.current.arm("earlier-key")); act(() => result.current.arm("current-key"));
    expect(players[0].pause).toHaveBeenCalledTimes(1);
    rerender(props([old, { ...reply, requestKey: "earlier-key" }])); expect(players).toHaveLength(1);
    rerender(props([old, reply])); await act(async () => {}); expect(players).toHaveLength(2);
  });

  it("changing question scope stops narration and cancels pending autoplay", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    await act(async () => result.current.play(old.id, old.audioPath));
    rerender(props([old], "paper:other-item:1"));
    expect(players[0].pause).toHaveBeenCalledTimes(1); expect(result.current.playingTurnId).toBeNull();
    act(() => result.current.arm("current-key"));
    rerender(props([old, reply], "paper:other-item:2")); expect(players).toHaveLength(1);
  });

  it("ignores an old rejected play promise after a newer reply starts", async () => {
    let reject!: (error: Error) => void;
    playResult = () => new Promise((_, fail) => { reject = fail; });
    const { result } = renderHook(useHomeworkTutorVoice, { initialProps: props([old, reply]) });
    act(() => result.current.play(old.id, old.audioPath));
    playResult = () => Promise.resolve();
    await act(async () => result.current.play(reply.id, reply.audioPath));
    await act(async () => reject(new Error("old error")));
    expect(result.current.playingTurnId).toBe(reply.id); expect(result.current.failedTurnId).toBeNull(); expect(players[1].pause).not.toHaveBeenCalled();
  });

  it("an earlier play promise cannot pause a newer resume of the same audio element", async () => {
    let resolve!: () => void;
    playResult = () => new Promise(done => { resolve = done; });
    const { result } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.toggle(old.id, old.audioPath));
    act(() => result.current.toggle(old.id, old.audioPath));
    playResult = () => Promise.resolve();
    await act(async () => result.current.toggle(old.id, old.audioPath));
    await act(async () => resolve());
    expect(players).toHaveLength(1); expect(players[0].pause).toHaveBeenCalledTimes(1);
    expect(result.current.playingTurnId).toBe(old.id);
  });

  it("hides a playing reply immediately and does not resume it on focus", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.arm("current-key")); rerender(props([old, reply])); await act(async () => {});
    act(() => { hidden = true; document.dispatchEvent(new Event("visibilitychange")); });
    expect(players[0].pause).toHaveBeenCalledTimes(1); expect(result.current.playingTurnId).toBeNull();
    act(() => { hidden = false; document.dispatchEvent(new Event("visibilitychange")); });
    rerender(props([old, { ...reply }])); expect(players[0].play).toHaveBeenCalledTimes(1);
  });

  it("ignores an old resolved play promise after unmount and leaves no listeners", async () => {
    let resolve!: () => void;
    playResult = () => new Promise(done => { resolve = done; });
    const { result, unmount } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    act(() => result.current.play(old.id, old.audioPath)); unmount();
    expect(players[0].pause).toHaveBeenCalledTimes(1); expect(players[0].onended).toBeNull(); expect(players[0].onerror).toBeNull();
    await act(async () => resolve());
    expect(players[0].pause).toHaveBeenCalledTimes(2);
    act(() => window.dispatchEvent(new Event("mira:learner-narration")));
    expect(players[0].pause).toHaveBeenCalledTimes(2);
  });

  it("other narration stops this audio and cancels pending automatic playback", async () => {
    const { result, rerender } = renderHook(useHomeworkTutorVoice, { initialProps: props() });
    await act(async () => result.current.play(old.id, old.audioPath));
    act(() => window.dispatchEvent(new Event("mira:learner-narration")));
    expect(players[0].pause).toHaveBeenCalledTimes(1);
    act(() => result.current.arm("current-key"));
    act(() => window.dispatchEvent(new Event("mira:learner-narration")));
    rerender(props([old, reply])); expect(players).toHaveLength(1);
  });
});
