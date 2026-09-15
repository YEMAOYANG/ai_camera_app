import { LoaderCircle, Orbit } from "lucide-react";
import { SpaceAtmosphere } from "@/components/student/space-atmosphere";

export default function Loading() {
  return (
    <main id="main-content" className="space-route-state" data-space-stage aria-busy="true">
      <SpaceAtmosphere scenic={false} />
      <div className="space-route-state-content" role="status">
        <span className="space-route-orbit" aria-hidden="true"><Orbit /></span>
        <p className="space-route-eyebrow">MIRA 学习空间</p>
        <h1>准备出发</h1>
        <p><LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />正在打开学习空间</p>
      </div>
    </main>
  );
}
