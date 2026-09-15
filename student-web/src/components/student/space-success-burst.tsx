import type { CSSProperties } from "react";

/** One short, local result accent. No timer, frame loop, overlay, score, or reward state. */
export function SpaceSuccessBurst({ active }: { active: boolean }) {
  if (!active) return null;
  return <span className="space-success-burst" aria-hidden="true">
    {Array.from({ length: 12 }, (_, index) => {
      const angle = index * Math.PI / 6;
      const distance = index % 2 ? 55 : 66;
      return <i key={index} style={{
        "--burst-x": `${Math.cos(angle) * distance}px`,
        "--burst-y": `${Math.sin(angle) * distance}px`,
        "--burst-delay": `${index % 3 * 35}ms`,
      } as CSSProperties} />;
    })}
    <b />
  </span>;
}
