"use client";

import { Backpack } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { MOTION_DURATION, mix, motionProgress, phase, type BagAction, type BagPose, type SchoolSubject } from "./motion-timeline";
import type { SchoolbagRenderer } from "./schoolbag-renderer";

const PREFERENCE = "mira.schoolbag.reduced-motion";
function reducedSnapshot() {
  try { return window.localStorage.getItem(PREFERENCE) === "1" || Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches); }
  catch { return Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches); }
}
function subscribeMotion(callback: () => void) {
  window.addEventListener("schoolbag-motion-change", callback); window.addEventListener("storage", callback);
  const media = window.matchMedia?.("(prefers-reduced-motion: reduce)"); media?.addEventListener?.("change", callback);
  return () => { window.removeEventListener("schoolbag-motion-change", callback); window.removeEventListener("storage", callback); media?.removeEventListener?.("change", callback); };
}
const serverSnapshot = () => false;
export function useSchoolbagMotionPreference() {
  const reduced = useSyncExternalStore(subscribeMotion, reducedSnapshot, serverSnapshot);
  const toggle = () => { try { window.localStorage.setItem(PREFERENCE, reduced ? "0" : "1"); } catch { /* Private mode: system preference still works. */ } window.dispatchEvent(new Event("schoolbag-motion-change")); };
  return { reduced, toggle };
}

type Rect = { left: number; top: number; width: number; height: number };
type Stage = { element: HTMLDivElement; pose: BagPose };
type Journey = { action: BagAction; subject?: SchoolSubject; href: string; replace: boolean; origin: string; navigated: boolean; from: Rect; id: number };
type MotionContext = {
  ready: boolean; busy: boolean;
  mountStage(element: HTMLDivElement, pose: BagPose): () => void;
  registerBook(subject: SchoolSubject): () => void;
  hover(subject: SchoolSubject | null): void;
  pick(x: number, y: number): SchoolSubject | null;
  enterLearning(): void;
  openBook(subject: SchoolSubject, href: string): void;
  returnHome(): void;
};
const Context = createContext<MotionContext | null>(null);

// Outside this provider (isolated UI tests or a non-3D host), routing stays usable.
export function useSchoolbagMotion() {
  const context = useContext(Context), router = useRouter();
  return context ?? {
    ready: false, busy: false,
    mountStage: () => () => {}, registerBook: () => () => {}, hover: () => {}, pick: () => null,
    enterLearning: () => { router.replace("/learning"); router.refresh(); },
    openBook: (_subject: SchoolSubject, href: string) => router.push(href),
    returnHome: () => router.push("/learning"),
  } satisfies MotionContext;
}

// A verified directory can be opened directly or refreshed, without visiting home.
// Prewarm its scene so every home entry point can close the correct subject book.
export function useSchoolbagBook(subject?: SchoolSubject) {
  const registerBook = useContext(Context)?.registerBook;
  useEffect(() => { if (subject && registerBook) return registerBook(subject); }, [subject, registerBook]);
}

function readRect(element: HTMLElement): Rect {
  const { left, top, width, height } = element.getBoundingClientRect(); return { left, top, width, height };
}
function centerRect(): Rect {
  const width = Math.min(window.innerWidth, 1100), height = window.innerHeight;
  return { left: (window.innerWidth - width) / 2, top: (window.innerHeight - height) / 2, width, height };
}

export function SchoolbagMotionProvider({ children }: { children: ReactNode }) {
  const router = useRouter(), pathname = usePathname() ?? "", { reduced } = useSchoolbagMotionPreference();
  const [enabled, setEnabled] = useState(false), [ready, setReady] = useState(false), [busy, setBusy] = useState(false);
  const [actionLabel, setActionLabel] = useState("打开课本，一起探索");
  const host = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null), route = useRef<HTMLDivElement>(null);
  const curtain = useRef<HTMLDivElement>(null), paper = useRef<HTMLDivElement>(null), skip = useRef<HTMLButtonElement>(null);
  const stage = useRef<Stage | null>(null), engine = useRef<SchoolbagRenderer | null>(null), journey = useRef<Journey | null>(null);
  const raf = useRef(0), fallback = useRef<ReturnType<typeof setTimeout> | null>(null), currentPath = useRef(pathname), lastSubject = useRef<SchoolSubject | null>(null);
  const focusOrigin = useRef<HTMLElement | null>(null), sequence = useRef(0);
  const directoryBook = useRef<SchoolSubject | null>(null);
  useLayoutEffect(() => { currentPath.current = pathname; }, [pathname]);

  const position = useCallback((rect: Rect) => {
    if (host.current) Object.assign(host.current.style, { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` });
  }, []);
  const attach = useCallback(() => {
    if (!stage.current || journey.current) return;
    if (host.current) host.current.style.opacity = "1";
    position(readRect(stage.current.element)); engine.current?.setPose(stage.current.pose);
  }, [position]);
  const finish = useCallback((focus = true) => {
    cancelAnimationFrame(raf.current); if (fallback.current) clearTimeout(fallback.current);
    fallback.current = null; journey.current = null; setBusy(false);
    if (route.current) route.current.inert = false;
    if (curtain.current) curtain.current.style.opacity = "0";
    if (paper.current) paper.current.style.opacity = "0";
    attach();
    if (!stage.current) {
      if (host.current) host.current.style.opacity = "0";
      if (!directoryBook.current) setEnabled(false);
    }
    if (focus) requestAnimationFrame(() => {
      const heading = document.querySelector<HTMLElement>("#main-content h1");
      if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
      else if (focusOrigin.current?.isConnected) focusOrigin.current.focus({ preventScroll: true });
    });
  }, [attach]);
  const navigate = useCallback(() => {
    const tx = journey.current; if (!tx || tx.navigated) return;
    tx.navigated = true;
    if (fallback.current) clearTimeout(fallback.current);
    if (tx.replace) { router.replace(tx.href); router.refresh(); } else router.push(tx.href);
    // Route loading, a hidden tab, or a renderer failure cannot trap the child.
    fallback.current = setTimeout(() => finish(), 2200);
  }, [finish, router]);
  const skipAnimation = useCallback(() => { navigate(); finish(); }, [finish, navigate]);

  const mountStage = useCallback((element: HTMLDivElement, pose: BagPose) => {
    stage.current = { element, pose }; if (!engine.current) setReady(false); setEnabled(true);
    if (host.current) host.current.style.opacity = "1";
    attach();
    const resize = new ResizeObserver(attach); resize.observe(element);
    window.addEventListener("resize", attach); window.addEventListener("scroll", attach, { passive: true });
    return () => {
      resize.disconnect(); window.removeEventListener("resize", attach); window.removeEventListener("scroll", attach);
      if (stage.current?.element === element) stage.current = null;
      // A route hand-off can mount another stage in the same frame.
      queueMicrotask(() => { if (!stage.current && !journey.current && !directoryBook.current) setEnabled(false); });
    };
  }, [attach]);

  const registerBook = useCallback((subject: SchoolSubject) => {
    directoryBook.current = subject; lastSubject.current = subject; setEnabled(true);
    return () => {
      if (directoryBook.current === subject) directoryBook.current = null;
      queueMicrotask(() => { if (!stage.current && !journey.current && !directoryBook.current) setEnabled(false); });
    };
  }, []);

  useEffect(() => {
    if (!enabled || !canvas.current) return;
    let disposed = false; const target = canvas.current;
    const fail = () => {
      if (!disposed) { engine.current?.dispose(); engine.current = null; setReady(false); if (journey.current) skipAnimation(); }
    };
    import("./schoolbag-renderer").then(module => module.createSchoolbagRenderer(target, fail)).then(created => {
      if (disposed) { created.dispose(); return; }
      engine.current = created; setReady(true); attach();
    }).catch(fail);
    return () => { disposed = true; engine.current?.dispose(); engine.current = null; };
  }, [enabled, attach, skipAnimation]);

  const start = useCallback((action: BagAction, href: string, subject?: SchoolSubject) => {
    if (journey.current) return;
    if (reducedSnapshot() || !engine.current || (!stage.current && action !== "return") || !ready) {
      if (action === "pack") { router.replace(href); router.refresh(); } else router.push(href);
      return;
    }
    const from = stage.current ? readRect(stage.current.element) : centerRect(), id = ++sequence.current;
    journey.current = { action, href, subject, replace: action === "pack", origin: currentPath.current, navigated: false, from, id };
    if (subject) lastSubject.current = subject;
    focusOrigin.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setActionLabel(action === "pack" ? "课本来啦，一起装进书包" : action === "return" ? "合上课本，放回书包" : "打开课本，一起探索");
    if (host.current) host.current.style.opacity = "1";
    setBusy(true); if (route.current) route.current.inert = true;
    requestAnimationFrame(() => skip.current?.focus({ preventScroll: true }));
    const began = performance.now();
    const frame = (now: number) => {
      if (journey.current?.id !== id) return;
      const elapsed = now - began, t = motionProgress(action, elapsed), target = centerRect();
      const move = phase(t.progress, 0, .32);
      position({ left: mix(from.left, target.left, move), top: mix(from.top, target.top, move), width: mix(from.width, target.width, move), height: mix(from.height, target.height, move) });
      if (curtain.current) curtain.current.style.opacity = String(phase(t.progress, 0, .19));
      if (paper.current) paper.current.style.opacity = String(t.paper);
      try { engine.current?.frame(action, elapsed, subject); } catch { skipAnimation(); return; }
      if (elapsed < MOTION_DURATION[action]) raf.current = requestAnimationFrame(frame); else navigate();
    };
    raf.current = requestAnimationFrame(frame);
    // rAF pauses in background tabs; never leave an authenticated session waiting.
    fallback.current = setTimeout(skipAnimation, MOTION_DURATION[action] + 900);
  }, [navigate, position, ready, router, skipAnimation]);

  useEffect(() => {
    const tx = journey.current; if (!tx) return;
    const destination = tx.href.split("?")[0];
    if (pathname === tx.origin && pathname !== destination) return;
    if (!tx.navigated || pathname !== destination) { finish(false); return; }
    if (fallback.current) clearTimeout(fallback.current);
    const began = performance.now(), from = host.current ? readRect(host.current) : centerRect();
    const land = (now: number) => {
      if (journey.current?.id !== tx.id) return;
      const p = phase(now - began, 0, 430);
      if (stage.current) {
        const target = readRect(stage.current.element);
        position({ left: mix(from.left, target.left, p), top: mix(from.top, target.top, p), width: mix(from.width, target.width, p), height: mix(from.height, target.height, p) });
        engine.current?.setPose(stage.current.pose, mix(1, 1.3, p));
      }
      if (curtain.current) curtain.current.style.opacity = String(1 - p);
      if (paper.current) paper.current.style.opacity = String(tx.action === "open" ? 1 - p : 0);
      if (host.current && !stage.current) host.current.style.opacity = String(1 - p);
      if (p < 1) raf.current = requestAnimationFrame(land); else { if (host.current) host.current.style.opacity = "1"; finish(); }
    };
    raf.current = requestAnimationFrame(land);
  }, [pathname, finish, position]);

  useEffect(() => {
    const hide = () => { if (document.hidden && journey.current) skipAnimation(); };
    document.addEventListener("visibilitychange", hide);
    return () => { document.removeEventListener("visibilitychange", hide); cancelAnimationFrame(raf.current); if (fallback.current) clearTimeout(fallback.current); };
  }, [skipAnimation]);
  useEffect(() => {
    if (!busy) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = overflow; };
  }, [busy]);
  useEffect(() => { if (reduced && journey.current) { const timer = setTimeout(skipAnimation, 0); return () => clearTimeout(timer); } }, [reduced, skipAnimation]);

  const value = useMemo<MotionContext>(() => ({
    ready, busy, mountStage, registerBook,
    hover: subject => { if (!journey.current && !reducedSnapshot()) engine.current?.hover(subject); },
    pick: (x, y) => engine.current?.pick(x, y) ?? null,
    enterLearning: () => start("pack", "/learning"),
    openBook: (subject, href) => start("open", href, subject),
    returnHome: () => lastSubject.current ? start("return", "/learning", lastSubject.current) : router.push("/learning"),
  }), [ready, busy, mountStage, registerBook, router, start]);
  return <Context.Provider value={value}>
    <div ref={route} className="schoolbag-route">{children}</div>
    <div ref={curtain} className={`bag-cinema-curtain ${busy ? "is-active" : ""}`} aria-hidden="true" />
    {enabled && <div ref={host} style={{ opacity: 0 }} className={`bag-scene-host ${busy ? "is-cinema" : ""}`} data-ready={ready} aria-hidden="true"><canvas ref={canvas} /></div>}
    <div ref={paper} className={`bag-paper-transition ${busy ? "is-active" : ""}`} aria-hidden="true" />
    {busy && <div className="bag-cinema-controls"><p role="status">{actionLabel}</p><button ref={skip} type="button" onClick={skipAnimation}>跳过动画 <span aria-hidden="true">→</span></button></div>}
  </Context.Provider>;
}

export function SchoolbagStage({ pose, onSelect, label }: { pose: BagPose; onSelect?: (subject: SchoolSubject) => void; label: string }) {
  const element = useRef<HTMLDivElement>(null), { mountStage, ready, pick, hover, busy } = useSchoolbagMotion();
  useLayoutEffect(() => { if (element.current) return mountStage(element.current, pose); }, [mountStage, pose]);
  return <div ref={element} className={`bag-scene-slot bag-scene-slot--${pose}`} data-scene-ready={ready} role="img" aria-label={label}
    onPointerMove={event => { if (pose === "ready" && !busy) { const subject = pick(event.clientX, event.clientY); hover(subject); event.currentTarget.style.cursor = subject ? "pointer" : "default"; } }}
    onPointerLeave={() => hover(null)} onClick={event => { if (!busy && onSelect) { const subject = pick(event.clientX, event.clientY); if (subject) onSelect(subject); } }}>
    <div className="bag-scene-fallback" aria-hidden="true"><Backpack strokeWidth={1} /><span>{pose === "closed" ? "你的小书包" : "课本准备好了"}</span></div>
  </div>;
}
