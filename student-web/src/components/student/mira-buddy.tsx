import { cn } from "@/lib/utils";

type BuddyMood = "hello" | "reading" | "thinking" | "celebrate";

export function MiraBuddy({
  mood = "hello",
  className,
  label = "Mira 学习伙伴",
}: {
  mood?: BuddyMood;
  className?: string;
  label?: string;
}) {
  const celebrating = mood === "celebrate";
  const thinking = mood === "thinking";
  return (
    <div className={cn("mira-buddy relative aspect-square", className)} role="img" aria-label={label}>
      <svg viewBox="0 0 220 220" className="size-full overflow-visible" aria-hidden="true">
        <path
          d="M48 158c-15 8-25 23-25 40M172 158c15 8 25 23 25 40"
          fill="none"
          stroke="var(--mira-buddy-line)"
          strokeLinecap="round"
          strokeWidth="12"
        />
        <path
          d="M74 52c-8-19 6-32 21-20 7-22 32-22 39 0 16-12 29 2 21 20"
          fill="var(--mira-buddy-antenna)"
          stroke="var(--mira-buddy-line)"
          strokeLinejoin="round"
          strokeWidth="6"
        />
        <rect x="35" y="46" width="150" height="139" rx="62" fill="var(--mira-buddy-body)" stroke="var(--mira-buddy-line)" strokeWidth="7" />
        <ellipse cx="75" cy="121" rx="16" ry="10" fill="var(--mira-buddy-cheek)" opacity=".72" />
        <ellipse cx="145" cy="121" rx="16" ry="10" fill="var(--mira-buddy-cheek)" opacity=".72" />
        {mood === "reading" ? (
          <>
            <path d="M68 98c6 7 14 7 20 0M132 98c6 7 14 7 20 0" fill="none" stroke="var(--mira-buddy-line)" strokeLinecap="round" strokeWidth="7" />
            <path d="M91 125c12 8 26 8 38 0" fill="none" stroke="var(--mira-buddy-line)" strokeLinecap="round" strokeWidth="6" />
            <path d="M55 149c19-7 37-3 55 9 18-12 36-16 55-9v46c-20-6-38-2-55 9-17-11-35-15-55-9z" fill="var(--mira-buddy-book)" stroke="var(--mira-buddy-line)" strokeLinejoin="round" strokeWidth="5" />
            <path d="M110 158v46" stroke="var(--mira-buddy-line)" strokeWidth="4" />
          </>
        ) : (
          <>
            <ellipse cx="82" cy="99" rx="8" ry={celebrating ? 5 : 11} fill="var(--mira-buddy-line)" />
            <ellipse cx="138" cy="99" rx="8" ry={celebrating ? 5 : 11} fill="var(--mira-buddy-line)" />
            {thinking ? (
              <path d="M96 130c8-5 20-5 28 0" fill="none" stroke="var(--mira-buddy-line)" strokeLinecap="round" strokeWidth="6" />
            ) : (
              <path d="M91 124c10 18 28 18 38 0" fill="var(--mira-buddy-mouth)" stroke="var(--mira-buddy-line)" strokeLinecap="round" strokeLinejoin="round" strokeWidth="6" />
            )}
          </>
        )}
        {celebrating ? (
          <>
            <path d="M25 62l-10-12m19 2 2-15m150 25 10-12m-19 2-2-15" fill="none" stroke="var(--mira-sun)" strokeLinecap="round" strokeWidth="6" />
            <path d="M45 157 18 177M175 157l27 20" fill="none" stroke="var(--mira-buddy-line)" strokeLinecap="round" strokeWidth="12" />
          </>
        ) : null}
      </svg>
      <span className="mira-buddy-star absolute right-[8%] top-[8%] grid size-[27%] place-items-center rounded-full bg-white shadow-sm" aria-hidden="true">
        <svg viewBox="0 0 40 40" className="size-[70%] text-[var(--mira-ai)]">
          <path d="M20 2l4.2 11.4L36 16l-9.5 7.4L28 36l-8-6.7L12 36l1.5-12.6L4 16l11.8-2.6z" fill="currentColor" />
        </svg>
      </span>
    </div>
  );
}
