"use client";

import { SlideCanvas, type SlideEffects } from "@openmaic/renderer";
import type { Slide } from "@openmaic/dsl";

import { assetReferenceUrl, isSafeAssetReference } from "@/features/classroom/openmaic-canvas";

export function OpenMaicSlideCanvas({ slide, focusTarget }: { slide: Slide; focusTarget?: string }) {
  const effects: SlideEffects | undefined = focusTarget
    ? { spotlight: { elementId: focusTarget } }
    : undefined;
  return (
    <SlideCanvas
      slide={slide}
      effects={effects}
      className="size-full"
      videoInteractive={false}
      renderImage={(element, source, fallback) => {
        const reference = typeof source === "string" ? source : element.src;
        if (!isSafeAssetReference(reference)) return null;
        if (reference === element.src && reference.startsWith("data:image/")) return fallback;
        // The renderer supplies authenticated, variable-size lesson assets; Next Image cannot know their dimensions here.
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={assetReferenceUrl(reference)} alt="课堂插图" className="size-full object-contain" />;
      }}
      renderVideo={() => null}
    />
  );
}
