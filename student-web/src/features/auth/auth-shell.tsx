import { MiraMark } from "@/components/student/mira-mark";

export function AuthShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mira-doodle-grid relative min-h-screen overflow-hidden px-4 py-5 sm:px-7 sm:py-7 lg:px-10">
      <div className="pointer-events-none absolute -left-20 top-32 size-56 rounded-full bg-[var(--mira-sky)]/65 blur-3xl" aria-hidden="true" />
      <div className="pointer-events-none absolute -right-16 bottom-10 size-64 rounded-full bg-[var(--mira-mint)]/55 blur-3xl" aria-hidden="true" />
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between">
        <MiraMark />
        <span className="hidden rounded-full border border-white bg-white/65 px-4 py-2 text-sm font-semibold text-[var(--mira-muted)] shadow-sm backdrop-blur sm:inline-flex">
          家长授权 · 学生专属
        </span>
      </header>
      <main id="main-content" className="relative mx-auto grid min-h-[calc(100vh-104px)] w-full max-w-6xl items-center py-8 lg:grid-cols-[1.05fr_.95fr] lg:gap-20">
        {children}
      </main>
    </div>
  );
}
