"use client";

import * as Switch from "@radix-ui/react-switch";

export function SwitchField({ checked, onCheckedChange, label }: { checked: boolean; onCheckedChange(checked: boolean): void; label: string }) {
  return <label className="mira-switch-field"><Switch.Root className="mira-switch" checked={checked} onCheckedChange={onCheckedChange} aria-label={label}><Switch.Thumb className="mira-switch-thumb" /></Switch.Root><span>{label}</span></label>;
}
