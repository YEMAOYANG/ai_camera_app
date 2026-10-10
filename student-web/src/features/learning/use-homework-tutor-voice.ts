"use client";

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

/** Supply every saved turn; audioPath is null until its current server source,
 * teaching quality, audio status and owned audio URL have all passed validation. */
export type HomeworkTutorVoiceTurn = {
  id: string;
  requestKey?: string;
  audioPath: string | null;
};

type Player = { element: HTMLAudioElement; turnId: string; path: string; scopeKey: string; intendsToPlay: boolean };
type AutomaticReply = { requestKey: string; scopeKey: string; savedTurnIds: Set<string> };

export function useHomeworkTutorVoice({ scopeKey, turns }: { scopeKey: string; turns: readonly HomeworkTutorVoiceTurn[] }) {
  const player = useRef<Player | null>(null);
  const automatic = useRef<AutomaticReply | null>(null);
  const armedKeys = useRef(new Set<string>());
  const scope = useRef(scopeKey);
  const generation = useRef(0);
  const alive = useRef(false);
  const narrationOwner = useRef({});
  const [playingTurnId, setPlayingTurnId] = useState<string | null>(null);
  const [failedTurnId, setFailedTurnId] = useState<string | null>(null);

  const stop = useCallback(() => {
    automatic.current = null;
    generation.current += 1;
    const previous = player.current;
    player.current = null;
    if (previous) {
      previous.element.onended = null;
      previous.element.onerror = null;
      previous.element.pause();
    }
    if (alive.current) setPlayingTurnId(null);
  }, []);

  const start = useCallback((turnId: string, path: string | null, resume = false) => {
    automatic.current = null;
    const allowed = !!path && turns.some(turn => turn.id === turnId && turn.audioPath === path);
    if (!allowed || document.hidden) {
      stop();
      if (alive.current && !allowed) setFailedTurnId(turnId);
      return;
    }
    const previous = player.current;
    const reuse = resume && previous?.turnId === turnId && previous.path === path && previous.scopeKey === scopeKey;
    if (!reuse) stop();
    // Coordinate with other learner narration without stopping our own player.
    window.dispatchEvent(new CustomEvent("mira:learner-narration", { detail: { owner: narrationOwner.current } }));
    const current: Player = { element: reuse ? previous.element : new Audio(path), turnId, path, scopeKey, intendsToPlay: true };
    player.current = current;
    const attempt = ++generation.current;
    const isCurrent = () => alive.current && player.current === current && generation.current === attempt;
    const failed = () => {
      if (!isCurrent()) return;
      stop();
      setFailedTurnId(turnId);
    };
    current.element.onended = () => {
      if (!isCurrent()) return;
      stop();
    };
    current.element.onerror = failed;
    setFailedTurnId(null);
    setPlayingTurnId(turnId);
    try {
      void current.element.play().then(() => {
        // An old promise must neither restart a stopped player nor stop a newer
        // resume on the same element. It never changes current UI state.
        if (!isCurrent() && (player.current?.element !== current.element || !player.current.intendsToPlay)) current.element.pause();
      }).catch(failed);
    } catch {
      failed();
    }
  }, [scopeKey, stop, turns]);

  const play = useCallback((turnId: string, path: string | null) => start(turnId, path), [start]);
  const toggle = useCallback((turnId: string, path: string | null) => {
    automatic.current = null;
    const current = player.current;
    if (current?.turnId === turnId && current.path === path && current.scopeKey === scopeKey && current.intendsToPlay) {
      generation.current += 1;
      player.current = { ...current, intendsToPlay: false };
      current.element.onended = null;
      current.element.onerror = null;
      current.element.pause();
      setPlayingTurnId(null);
      return;
    }
    start(turnId, path, true);
  }, [scopeKey, start]);

  const arm = useCallback((requestKey: string) => {
    stop();
    if (!requestKey || document.hidden || armedKeys.current.has(requestKey)) return;
    armedKeys.current.add(requestKey);
    automatic.current = { requestKey, scopeKey, savedTurnIds: new Set(turns.map(turn => turn.id)) };
    setFailedTurnId(null);
  }, [scopeKey, stop, turns]);

  useEffect(() => {
    alive.current = true;
    const otherNarration = (event: Event) => {
      if ((event as CustomEvent<{ owner?: object }>).detail?.owner !== narrationOwner.current) stop();
    };
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener("mira:learner-narration", otherNarration);
    document.addEventListener("visibilitychange", hide);
    return () => {
      alive.current = false;
      stop();
      window.removeEventListener("mira:learner-narration", otherNarration);
      document.removeEventListener("visibilitychange", hide);
    };
  }, [stop]);

  const reconcile = useEffectEvent(() => {
    if (scope.current !== scopeKey) {
      stop();
      scope.current = scopeKey;
      armedKeys.current.clear();
      setFailedTurnId(null);
      return;
    }
    const current = player.current;
    if (current && !turns.some(turn => turn.id === current.turnId && turn.audioPath === current.path)) stop();
    const pending = automatic.current;
    if (!pending || pending.scopeKey !== scopeKey) return;
    if (document.hidden) { stop(); return; }
    const reply = turns.find(turn => turn.requestKey === pending.requestKey && !pending.savedTurnIds.has(turn.id));
    if (!reply?.audioPath) return;
    // Consume before calling play: source updates, duplicate GETs and browser
    // autoplay rejection can never repeat this automatic attempt.
    automatic.current = null;
    start(reply.id, reply.audioPath);
  });
  useEffect(() => { reconcile(); }, [scopeKey, turns]);

  return { arm, stop, play, toggle, playingTurnId, failedTurnId };
}
