import Image from "next/image";
import { cn } from "@/lib/utils";
export function SpaceCourseArt({ subject, className, priority = false }: { subject: string; className?: string; priority?: boolean }) {
  const kind = subject.toLowerCase();
  const name = kind === "chinese" ? "subject-chinese" : kind === "english" ? "subject-english" : "subject-math-lab";
  return <div className={cn("space-course-art", `space-course-art--${kind}`, className)} aria-hidden="true"><Image src={`/images/space/${name}.png`} alt="" fill sizes="(max-width: 700px) 90vw, 35vw" priority={priority} /></div>;
}
