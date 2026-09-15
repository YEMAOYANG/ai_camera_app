"use client";

import { ArrowRight, RotateCcw, Satellite } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { SpaceAtmosphere } from "@/components/student/space-atmosphere";

export default function ErrorPage({ retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main id="main-content" className="space-route-state" data-space-stage>
      <SpaceAtmosphere scenic={false} />
      <div className="space-route-state-content" role="alert">
        <span className="space-route-orbit is-warning" aria-hidden="true"><Satellite /></span>
        <p className="space-route-eyebrow">MIRA 学习空间</p>
        <h1>暂时没有连接上</h1>
        <p>再试一次，或先回到今天的课程。</p>
        <div className="space-route-actions">
          <Button onClick={retry}><RotateCcw className="size-5" aria-hidden="true" />再试一次</Button>
          <Button variant="secondary" asChild><Link href="/today">回到今天<ArrowRight className="size-5" aria-hidden="true" /></Link></Button>
        </div>
      </div>
    </main>
  );
}
