import { ArrowRight, Telescope } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SpaceAtmosphere } from "@/components/student/space-atmosphere";

export default function NotFound() {
  return (
    <main id="main-content" className="space-route-state" data-space-stage>
      <SpaceAtmosphere scenic={false} />
      <div className="space-route-state-content">
        <span className="space-route-orbit" aria-hidden="true"><Telescope /></span>
        <p className="space-route-eyebrow">MIRA 学习空间 · 404</p>
        <h1>没有找到这个页面</h1>
        <p>回到你的学习空间，继续下一段探索。</p>
        <div className="space-route-actions"><Button asChild><Link href="/today">回到今天<ArrowRight className="size-5" aria-hidden="true" /></Link></Button></div>
      </div>
    </main>
  );
}
