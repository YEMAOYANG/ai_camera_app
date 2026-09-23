"use client";

import type { LearningQuestion } from "@/lib/contracts/learning";

const colors = { red: "#cf684d", blue: "#3982ad", yellow: "#d8a123", green: "#398967" };

/** Count concrete objects without requiring numeral recognition first. */
export function TapObjectsInput({ objects, value, onChange, disabled = false }: {
  objects: NonNullable<LearningQuestion["objects"]>;
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
}) {
  return <div role="group" aria-label="逐个点一点，每个物体只数一次" className="flex flex-wrap gap-4 py-4">
    {objects.map((object, index) => {
      const selected = value.includes(object.id);
      return <button type="button" key={object.id} aria-label={`物体 ${index + 1}`} aria-pressed={selected}
        disabled={disabled} className={`focus-ring flex size-20 items-center justify-center rounded-2xl border-2 ${selected ? "border-[var(--mira-brand)] bg-[var(--mira-brand-wash)]" : "border-[var(--mira-border)] bg-white"}`}
        onClick={() => onChange(selected ? value.filter(id => id !== object.id) : [...value, object.id])}>
        <svg viewBox="0 0 48 48" width="44" height="44" aria-hidden="true" fill={colors[object.color]}>
          {object.shape === "square" ? <rect x="6" y="6" width="36" height="36" rx="4" />
            : object.shape === "triangle" ? <path d="M24 4 46 43H2Z" /> : <circle cx="24" cy="24" r="20" />}
          {selected && <path d="m14 24 7 7 14-16" fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" />}
        </svg>
      </button>;
    })}
  </div>;
}
