"use client";

import { BookOpen, House, PencilLine } from "lucide-react";
import Link, { useLinkStatus } from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, type CSSProperties, type ReactNode } from "react";

import { SpaceMotionToggle } from "@/components/student/space-atmosphere";
import { cn } from "@/lib/utils";

type SpaceNavigationActive = "today" | "learning" | "practice";

const PersistentSpaceNavigationContext = createContext(false);
const destinations = [
  { key: "today", href: "/today", label: "今天", icon: House },
  { key: "learning", href: "/learning", label: "课程", icon: BookOpen },
  { key: "practice", href: "/learning/practice", label: "练习", icon: PencilLine },
] as const;

export function SpaceNavigationProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const active: SpaceNavigationActive | null = pathname === "/today" ? "today"
    : pathname === "/learning/practice" ? "practice"
      : pathname === "/learning" || pathname?.startsWith("/learning/") ? "learning" : null;

  return (
    <PersistentSpaceNavigationContext.Provider value={true}>
      {active && <div className="space-navigation-host"><SpaceNavigation active={active} /></div>}
      {children}
    </PersistentSpaceNavigationContext.Provider>
  );
}

export function usePersistentSpaceNavigation() {
  return useContext(PersistentSpaceNavigationContext);
}

export function SpaceNavigation({ active }: { active: SpaceNavigationActive }) {
  const index = active === "today" ? 0 : active === "learning" ? 1 : 2;
  return (
    <nav className="space-rail" aria-label="学生导航" style={{ "--space-nav-index": index } as CSSProperties}>
      <div className="space-rail-destinations">
        <span className="space-rail-selection" aria-hidden="true" />
        {destinations.map(({ key, href, label, icon: Icon }) => (
          <Link key={key} href={href} className="focus-ring space-rail-link" aria-current={active === key ? "page" : undefined}>
            <span className="space-rail-icon"><Icon size={21} strokeWidth={1.65} aria-hidden="true" /></span>
            <span className="space-rail-label">{label}</span>
            <NavPending />
          </Link>
        ))}
      </div>
      <div className="space-rail-utility"><SpaceMotionToggle /></div>
    </nav>
  );
}

function NavPending() {
  const { pending } = useLinkStatus();
  return <span className={cn("space-rail-pending", pending && "is-pending")} aria-hidden="true" />;
}
