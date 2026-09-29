"use client";

import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";

export function SelectField({ value, onValueChange, label, options }: {
  value: string; onValueChange(value: string): void; label: string;
  options: { value: string; label: string }[];
}) {
  return <Select.Root value={value} onValueChange={onValueChange}>
    <Select.Trigger className="mira-select-trigger" aria-label={label}><Select.Value /><Select.Icon><ChevronDown size={17} aria-hidden="true" /></Select.Icon></Select.Trigger>
    <Select.Portal>
      <Select.Content className="mira-ui-surface mira-select-content" position="popper" sideOffset={6} collisionPadding={12}>
        <Select.ScrollUpButton className="mira-select-scroll"><ChevronUp size={16} /></Select.ScrollUpButton>
        <Select.Viewport className="mira-select-viewport">{options.map(option => <Select.Item className="mira-select-item" key={option.value} value={option.value}>
          <Select.ItemText>{option.label}</Select.ItemText><Select.ItemIndicator><Check size={17} aria-hidden="true" /></Select.ItemIndicator>
        </Select.Item>)}</Select.Viewport>
        <Select.ScrollDownButton className="mira-select-scroll"><ChevronDown size={16} /></Select.ScrollDownButton>
      </Select.Content>
    </Select.Portal>
  </Select.Root>;
}
