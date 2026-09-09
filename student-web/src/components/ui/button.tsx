import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "focus-ring inline-flex min-h-12 items-center justify-center gap-2 rounded-[var(--mira-radius-button)] px-5 text-[17px] font-bold transition-[transform,box-shadow,background-color,color] duration-200 disabled:cursor-not-allowed disabled:bg-[var(--mira-disabled)] disabled:text-[var(--mira-subtle)] active:scale-[.975]",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--mira-brand-deep)] text-white shadow-[var(--mira-shadow-action)] hover:bg-[var(--mira-brand)]",
        secondary:
          "border border-[var(--mira-border)] bg-white text-[var(--mira-ink)] hover:border-[var(--mira-brand)] hover:bg-[var(--mira-brand-wash)]",
        quiet: "text-[var(--mira-muted)] hover:bg-white/70 hover:text-[var(--mira-ink)]",
      },
      size: {
        default: "h-14",
        compact: "h-12 min-h-12 text-[15px]",
        icon: "size-12 min-h-12 px-0",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
