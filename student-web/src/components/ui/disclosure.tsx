"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Disclosure({ title, children, className, onOpenChange }: {
  title: ReactNode; children: ReactNode; className?: string; onOpenChange?(open: boolean): void;
}) {
  const [open, setOpen] = useState(false);
  return <Collapsible.Root className={cn("mira-disclosure", className)} open={open} onOpenChange={next => { setOpen(next); onOpenChange?.(next); }}>
    <Collapsible.Trigger className="mira-disclosure-trigger">{title}<ChevronDown size={16} aria-hidden="true" /></Collapsible.Trigger>
    <Collapsible.Content forceMount hidden={!open} className="mira-disclosure-content">{children}</Collapsible.Content>
  </Collapsible.Root>;
}
