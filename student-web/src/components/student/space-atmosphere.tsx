"use client";

import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useSyncExternalStore } from "react";

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";
function subscribeToMotion(callback: () => void) {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(reducedMotionQuery);
  query.addEventListener?.("change", callback);
  return () => query.removeEventListener?.("change", callback);
}
function getReducedMotion() {
  return typeof window.matchMedia === "function" && window.matchMedia(reducedMotionQuery).matches;
}
const getServerReducedMotion = () => true;
const pauseKey = "mira.space.motion.paused";
const pauseEvent = "mira-space-motion-change";
let pauseFallback = false;
function getPaused() {
  try { return window.sessionStorage.getItem(pauseKey) === "true" || pauseFallback; }
  catch { return pauseFallback; }
}
function subscribeToPause(callback: () => void) {
  window.addEventListener(pauseEvent, callback);
  return () => window.removeEventListener(pauseEvent, callback);
}
function togglePaused() {
  pauseFallback = !getPaused();
  try { window.sessionStorage.setItem(pauseKey, String(pauseFallback)); } catch { /* In-memory preference still works. */ }
  window.dispatchEvent(new Event(pauseEvent));
}
const getServerPaused = () => false;
const wrap = (value: number, size: number) => ((value % size) + size) % size;

/** Decorative canvas only: course illustrations and every control remain real page content. */
export function SpaceAtmosphere({ scenic, variant = "page", showToggle = true }: { scenic: boolean; variant?: "page" | "toolbar"; showToggle?: boolean }) {
  const layerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const elapsedRef = useRef(0);
  const pointerRef = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const paused = useSyncExternalStore(subscribeToPause, getPaused, getServerPaused);
  const reducedMotion = useSyncExternalStore(subscribeToMotion, getReducedMotion, getServerReducedMotion);

  useEffect(() => {
    const layer = layerRef.current;
    const canvas = canvasRef.current;
    const shell = layer?.closest<HTMLElement>(".space-shell, [data-space-stage]");
    if (!layer || !canvas || !shell) return;
    let frame = 0;
    let width = 0;
    let height = 0;
    let lastTime = 0;
    let disposed = false;
    const canAnimate = !paused && !reducedMotion;
    const pointer = pointerRef.current;
    let context: CanvasRenderingContext2D | null = null;
    // jsdom and browsers without a canvas implementation use the static scene.
    if (typeof window.CanvasRenderingContext2D !== "undefined") {
      try { context = canvas.getContext("2d", { alpha: true }); } catch { /* Static fallback. */ }
    }
    const ctx = context;
    const seedRandom = (() => {
      let seed = 8315;
      return () => { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    })();
    const stars = Array.from({ length: variant === "toolbar" ? 32 : scenic ? 155 : 110 }, () => ({
      x: seedRandom(), y: seedRandom(), depth: seedRandom(), phase: seedRandom() * Math.PI * 2,
    }));

    function motionState() {
      if (!shell) return;
      shell.dataset.spaceMotion = reducedMotion ? "reduced" : paused ? "paused" : document.hidden ? "hidden" : "running";
    }
    function draw(time: number) {
      if (!ctx || !width || !height) return;
      ctx.clearRect(0, 0, width, height);
      const mobile = width < 701;
      const count = Math.min(stars.length, mobile ? (scenic ? 65 : 40) : stars.length);
      const gain = scenic ? 1 : 0.68;
      for (let index = 0; index < count; index++) {
        const star = stars[index];
        const depth = 0.25 + star.depth;
        const x = wrap(star.x * width - time * depth * 8 + pointer.x * depth * 0.45, width + 24) - 12;
        const y = wrap(star.y * height + time * depth * 12 + pointer.y * depth * 0.45, height + 24) - 12;
        // Dim the greeting and main course title region, even on narrow screens.
        const behindCopy = scenic && (mobile ? y > height * 0.32 : x < width * 0.46 && y > height * 0.14 && y < height * 0.74);
        const quiet = behindCopy || y < 85 ? 0.2 : 1;
        const opacity = (0.4 + star.depth * 0.45) * (0.75 + Math.sin(time * 1.1 + star.phase) * 0.25) * gain * quiet;
        const radius = 0.55 + star.depth * 1.45;
        ctx.fillStyle = `rgba(${star.depth > 0.7 ? "202,238,255" : "117,186,234"},${opacity})`;
        ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill();
        if (star.depth > 0.84 && quiet === 1) {
          ctx.strokeStyle = `rgba(140,220,255,${opacity * 0.3})`;
          ctx.lineWidth = 0.7;
          ctx.beginPath(); ctx.moveTo(x - radius * 2.6, y); ctx.lineTo(x + radius * 2.6, y);
          ctx.moveTo(x, y - radius * 2.6); ctx.lineTo(x, y + radius * 2.6); ctx.stroke();
        }
      }
      if (!scenic) return;

      // Small moving lights follow the illustration's orbit, without redrawing the planet.
      const imageHeight = Math.max(height, width * 1058 / 1487);
      const centerX = width * (mobile ? 0.7 : 0.705) + pointer.x;
      const centerY = imageHeight * 0.34 + pointer.y;
      const radiusX = width * 0.285;
      const radiusY = imageHeight * 0.115;
      function orbitPoint(angle: number) {
        const x = Math.cos(angle) * radiusX;
        const y = Math.sin(angle) * radiusY;
        return { x: centerX + x * 0.966 + y * 0.259, y: centerY - x * 0.259 + y * 0.966 };
      }
      for (let orbiter = 0; orbiter < (mobile ? 1 : 2); orbiter++) {
        const angle = time * (orbiter === 0 ? 0.42 : 0.3) + orbiter * Math.PI;
        for (let step = 0; step < 20; step++) {
          const start = orbitPoint(angle - step * 0.018);
          const end = orbitPoint(angle - (step + 1) * 0.018);
          ctx.strokeStyle = `rgba(${orbiter ? "238,252,188" : "129,225,255"},${(1 - step / 20) * 0.58})`;
          ctx.lineWidth = 1.4;
          ctx.beginPath(); ctx.moveTo(start.x, start.y); ctx.lineTo(end.x, end.y); ctx.stroke();
        }
        const head = orbitPoint(angle);
        const glow = ctx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 14);
        glow.addColorStop(0, "rgba(231,254,255,0.95)"); glow.addColorStop(0.2, "rgba(148,225,255,0.8)"); glow.addColorStop(1, "rgba(110,205,255,0)");
        ctx.fillStyle = glow; ctx.fillRect(head.x - 14, head.y - 14, 28, 28);
      }
      // One short, slow meteor every nine seconds, away from the reading area.
      const meteor = wrap(time + 1, 9);
      if (meteor < 1.8) {
        const progress = meteor / 1.8;
        const x = width * (0.73 + progress * 0.24);
        const y = height * (0.05 + progress * 0.2);
        const length = mobile ? 60 : 115;
        const alpha = Math.sin(progress * Math.PI) * 0.85;
        const trail = ctx.createLinearGradient(x - length, y - length * 0.46, x, y);
        trail.addColorStop(0, "rgba(112,207,255,0)"); trail.addColorStop(1, `rgba(222,249,255,${alpha})`);
        ctx.strokeStyle = trail; ctx.lineWidth = 1.7;
        ctx.beginPath(); ctx.moveTo(x - length, y - length * 0.46); ctx.lineTo(x, y); ctx.stroke();
      }
    }
    function tick(now: number) {
      if (disposed || !canAnimate || document.hidden) { frame = 0; return; }
      frame = requestAnimationFrame(tick);
      if (lastTime && now - lastTime < 1000 / 30) return;
      const delta = lastTime ? Math.min((now - lastTime) / 1000, 0.08) : 0;
      lastTime = now;
      elapsedRef.current += delta;
      pointer.x += (pointer.targetX - pointer.x) * 0.07;
      pointer.y += (pointer.targetY - pointer.y) * 0.07;
      if (scenic) {
        shell?.style.setProperty("--space-pointer-x", `${(pointer.x + Math.sin(elapsedRef.current * 0.24) * 3).toFixed(2)}px`);
        shell?.style.setProperty("--space-pointer-y", `${(pointer.y + Math.cos(elapsedRef.current * 0.2) * 2).toFixed(2)}px`);
      }
      draw(elapsedRef.current);
    }
    function resize() {
      if (!layer || !canvas || disposed) return;
      const box = layer.getBoundingClientRect();
      width = box.width; height = box.height;
      const ratio = Math.min(window.devicePixelRatio || 1, width < 701 ? 1.25 : 1.5);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx?.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw(elapsedRef.current);
    }
    function onPointerMove(event: PointerEvent) {
      if (!canAnimate || !scenic || event.pointerType !== "mouse" || !width) return;
      const box = layer?.getBoundingClientRect();
      if (!box) return;
      pointer.targetX = ((event.clientX - box.left) / width - 0.5) * -18;
      pointer.targetY = ((event.clientY - box.top) / height - 0.5) * -12;
    }
    function resetPointer() { pointer.targetX = 0; pointer.targetY = 0; }
    function onVisibility() {
      motionState();
      cancelAnimationFrame(frame); frame = 0; lastTime = 0;
      if (!document.hidden && canAnimate && ctx) frame = requestAnimationFrame(tick);
    }
    motionState();
    if (reducedMotion) {
      pointer.x = 0; pointer.y = 0; resetPointer();
      shell.style.setProperty("--space-pointer-x", "0px"); shell.style.setProperty("--space-pointer-y", "0px");
    } else {
      // Pausing freezes the current scene instead of snapping the artwork back.
      shell.style.setProperty("--space-pointer-x", `${(pointer.x + Math.sin(elapsedRef.current * 0.24) * 3).toFixed(2)}px`);
      shell.style.setProperty("--space-pointer-y", `${(pointer.y + Math.cos(elapsedRef.current * 0.2) * 2).toFixed(2)}px`);
    }
    resize();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;
    observer?.observe(layer);
    window.addEventListener("resize", resize, { passive: true });
    shell.addEventListener("pointermove", onPointerMove, { passive: true });
    shell.addEventListener("pointerleave", resetPointer, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    if (canAnimate && !document.hidden && ctx) frame = requestAnimationFrame(tick);
    return () => {
      disposed = true; cancelAnimationFrame(frame); observer?.disconnect();
      window.removeEventListener("resize", resize);
      shell.removeEventListener("pointermove", onPointerMove);
      shell.removeEventListener("pointerleave", resetPointer);
      document.removeEventListener("visibilitychange", onVisibility);
      delete shell.dataset.spaceMotion;
      shell.style.removeProperty("--space-pointer-x"); shell.style.removeProperty("--space-pointer-y");
    };
  }, [scenic, paused, reducedMotion, variant]);

  return <>
    <div ref={layerRef} className={`space-atmosphere ${scenic ? "is-scenic" : "is-quiet"} space-atmosphere--${variant}`} aria-hidden="true"><canvas ref={canvasRef} /></div>
    {showToggle && <SpaceMotionToggle />}
  </>;
}

/** A single shared preference, whether the control lives in the dock or toolbar. */
export function SpaceMotionToggle() {
  const paused = useSyncExternalStore(subscribeToPause, getPaused, getServerPaused);
  const reducedMotion = useSyncExternalStore(subscribeToMotion, getReducedMotion, getServerReducedMotion);
  const inactive = paused || reducedMotion;
  return (
    <button type="button" className="focus-ring space-motion-toggle" disabled={reducedMotion}
      aria-label={reducedMotion ? "背景动态已按系统设置暂停" : paused ? "继续背景动态" : "暂停背景动态"}
      aria-pressed={!inactive} onClick={togglePaused}
      title={reducedMotion ? "已遵循系统的减少动态效果设置" : paused ? "继续背景动态" : "暂停背景动态"}>
      {inactive ? <Play size={15} aria-hidden="true" /> : <Pause size={15} aria-hidden="true" />}<span>{inactive ? "动态已暂停" : "背景动态"}</span>
    </button>
  );
}
