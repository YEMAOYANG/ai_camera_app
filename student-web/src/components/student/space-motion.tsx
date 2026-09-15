"use client";
// Adapted from React Bits Tilted Card and Click Spark by David Haz.
// Upstream URLs and license are retained in THIRD_PARTY_NOTICES.md.
import { motion, useMotionValue, useReducedMotion, useSpring } from "motion/react";
import { useEffect, useRef, type PointerEvent, type ReactNode } from "react";
export function SpaceTilt({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  const x = useMotionValue(0); const y = useMotionValue(0);
  const rotateX = useSpring(x, { damping: 30, stiffness: 140 });
  const rotateY = useSpring(y, { damping: 30, stiffness: 140 });
  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduce || event.pointerType !== "mouse") return;
    const box = event.currentTarget.getBoundingClientRect();
    const bounded = (value: number) => Math.max(-1, Math.min(1, value));
    x.set(-bounded((event.clientY - box.top - box.height / 2) / (box.height / 2)) * 7);
    y.set(bounded((event.clientX - box.left - box.width / 2) / (box.width / 2)) * 7);
  }
  return <div className={className} style={{ perspective: 1100 }} onPointerMove={move} onPointerLeave={() => { x.set(0); y.set(0); }}><motion.div className="space-tilt-surface" style={reduce ? undefined : { rotateX, rotateY }}>{children}</motion.div></div>;
}
export function SpaceClickSpark({ children, className }: { children: ReactNode; className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frame = useRef(0);
  const reduce = useReducedMotion();
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  function spark(event: PointerEvent<HTMLDivElement>) {
    if (reduce || event.button !== 0 || !(event.target as HTMLElement).closest("button")) return;
    const canvas = canvasRef.current; if (!canvas) return;
    const context = canvas.getContext("2d"); if (!context) return;
    cancelAnimationFrame(frame.current);
    const box = canvas.getBoundingClientRect(); const ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = box.width * ratio; canvas.height = box.height * ratio; context.scale(ratio, ratio);
    const x = event.clientX - box.left; const y = event.clientY - box.top; const start = performance.now();
    function draw(now: number) {
      if (!context) return;
      const t = Math.min((now - start) / 450, 1); const eased = t * (2 - t);
      context.clearRect(0, 0, box.width, box.height);
      if (t >= 1 || document.hidden) return;
      context.strokeStyle = `rgba(218,255,126,${1 - t})`; context.lineWidth = 1.5;
      for (let i = 0; i < 8; i++) { const a = i * Math.PI / 4; const distance = 8 + 24 * eased; const length = 7 * (1 - eased); context.beginPath(); context.moveTo(x + Math.cos(a) * distance, y + Math.sin(a) * distance); context.lineTo(x + Math.cos(a) * (distance + length), y + Math.sin(a) * (distance + length)); context.stroke(); }
      frame.current = requestAnimationFrame(draw);
    }
    frame.current = requestAnimationFrame(draw);
  }
  return <div className={`space-click-spark ${className || ""}`} onPointerDown={spark}>{children}<canvas ref={canvasRef} className="space-click-spark__canvas" aria-hidden="true" /></div>;
}
