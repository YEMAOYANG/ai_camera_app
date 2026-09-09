"use client";

import { AlertCircle, LoaderCircle } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo } from "react";

import { parseOpenMaicCanvas, slideFromSafeBlocks } from "@/features/classroom/openmaic-canvas";
import type { ClassroomScene } from "@/lib/contracts/lesson-package";

const OpenMaicSlideCanvas = dynamic(
  () => import("@/features/classroom/openmaic-slide-canvas").then((module) => module.OpenMaicSlideCanvas),
  {
    ssr: false,
    loading: () => <div className="grid size-full place-items-center"><LoaderCircle className="size-8 animate-spin text-[var(--mira-brand)]" /></div>,
  },
);

export function SlideScene({ scene, focusTarget }: { scene: Extract<ClassroomScene, { type: "slide" }>; focusTarget?: string }) {
  const result = useMemo(() => {
    try {
      return { slide: scene.canvas === undefined ? slideFromSafeBlocks(scene.id, scene.title, scene.blocks) : parseOpenMaicCanvas(scene.canvas) };
    } catch (error) {
      return { error: error instanceof Error ? error.message : "课件格式暂时无法播放" };
    }
  }, [scene]);

  if (!result.slide) {
    return <div className="grid size-full min-h-[320px] place-items-center bg-[var(--mira-sun-soft)] p-8 text-center"><div><AlertCircle className="mx-auto size-10 text-[var(--mira-warning)]" /><p className="mt-3 text-xl font-black">这一页课件暂时打不开</p><p className="mt-2 text-[var(--mira-muted)]">{result.error}</p></div></div>;
  }
  return <OpenMaicSlideCanvas slide={result.slide} focusTarget={focusTarget} />;
}

